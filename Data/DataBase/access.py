"""
access.py : THE ONLY WAY THE REST OF THE SYSTEM READS DATA.

    from Data.DataBase.access import get_series, get_prices

The as-of rule (no look-ahead):
  Every read REQUIRES as_of (keyword-only, no default). You get back only
  values with known_at <= as_of, and for each date the newest such version.
  `end` defaults to as_of and can never go past it.

Names are our own series_ids (lowercase), see list_series().

Wide reads (get_series, get_prices, get_features) return a DataFrame:
    index   = date (DatetimeIndex named 'date')
    columns = one per id, in the order you asked
Missing values stay NaN unless you pass ffill_limit (max days to carry a
value forward).

Run your code from the repo root (python -m ModelHome.something) so that
`Data` is importable.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable

import duckdb
import pandas as pd

from Data.DataBase.db import connect_market, connect_trading

PRICE_FIELDS = ("open", "high", "low", "close", "volume", "adj_close", "total_return", "dividend")

_con: duckdb.DuckDBPyConnection | None = None


# -----------------------------------------------------------------------------
# Connection (read-only, shared)
# -----------------------------------------------------------------------------

def _market() -> duckdb.DuckDBPyConnection:
    global _con
    if _con is None:
        _con = connect_market(read_only=True)
    return _con


def close() -> None:
    """Release the read-only connection (needed before refresh.py can write)."""
    global _con
    if _con is not None:
        _con.close()
        _con = None


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _to_date(x, name: str) -> date:
    if x is None:
        raise ValueError(f"{name} is required")
    return pd.Timestamp(x).date()


def _window(start, end, as_of) -> tuple[date, date, date]:
    as_of_d = _to_date(as_of, "as_of")
    start_d = _to_date(start, "start")
    end_d = as_of_d if end is None else min(_to_date(end, "end"), as_of_d)
    return start_d, end_d, as_of_d


def _ids(ids: str | Iterable[str]) -> list[str]:
    return [ids] if isinstance(ids, str) else list(ids)


def _check_ids(ids: list[str], storage: str | None, table: str = "meta.series", key: str = "series_id") -> None:
    where = f" WHERE storage = '{storage}'" if storage else ""
    known = {r[0] for r in _market().execute(f"SELECT {key} FROM {table}{where}").fetchall()}
    unknown = [i for i in ids if i not in known]
    if unknown:
        hint = f" with storage='{storage}'" if storage else ""
        raise KeyError(f"Unknown id(s) {unknown}: not in {table}{hint}. See list_series() / list_features().")


def _wide(df: pd.DataFrame, id_col: str, value_col: str, ids: list[str], ffill_limit: int | None) -> pd.DataFrame:
    if df.empty:
        out = pd.DataFrame(columns=ids, dtype=float)
    else:
        out = df.pivot(index="obs_date", columns=id_col, values=value_col).reindex(columns=ids)
    out.index = pd.DatetimeIndex(out.index, name="date")
    out.columns.name = None
    if ffill_limit:
        out = out.ffill(limit=ffill_limit)
    return out


def _latest_known(select_sql: str, partition: str, order: str, params: list) -> pd.DataFrame:
    """
    The as-of core: from rows already filtered to known_at <= as_of, keep the
    newest version per `partition`. The MATERIALIZED CTE works around a
    DuckDB 1.5 optimizer bug (window on top of the clean.prices view).
    """
    return _market().execute(
        f"""
        WITH x AS MATERIALIZED ({select_sql})
        SELECT * EXCLUDE (known_at) FROM x
        QUALIFY row_number() OVER (PARTITION BY {partition} ORDER BY known_at DESC) = 1
        ORDER BY {order}
        """,
        params,
    ).df()


def _as_of_query(view: str, id_col: str, cols: str, ids: list[str], start, end, as_of) -> pd.DataFrame:
    return _latest_known(
        f"""
        SELECT {id_col}, obs_date, {cols}, known_at
        FROM {view}
        WHERE {id_col} IN (SELECT unnest(?))
          AND obs_date BETWEEN ? AND ?
          AND known_at <= ?
        """,
        f"{id_col}, obs_date", "obs_date", [ids, start, end, as_of],
    )


# -----------------------------------------------------------------------------
# Market data reads
# -----------------------------------------------------------------------------

def get_series(series_ids, start, end=None, *, as_of, ffill_limit: int | None = None) -> pd.DataFrame:
    """Single-value series (FRED, CBOE, Bloomberg), e.g. ["ust_10y", "vix"]."""
    ids = _ids(series_ids)
    _check_ids(ids, "series")
    s, e, a = _window(start, end, as_of)
    df = _as_of_query("clean.series", "series_id", "value", ids, s, e, a)
    return _wide(df, "series_id", "value", ids, ffill_limit)


def get_prices(series_ids, start, end=None, *, as_of, field: str = "close",
               ffill_limit: int | None = None) -> pd.DataFrame:
    """
    Daily prices, e.g. ["spy", "tqqq"].
    field:
      open/high/low/close/volume  as actually traded that day (use for levels, strikes)
      total_return                daily return incl. dividends (use for returns)
      dividend                    cash dividend per share paid on that ex-date
      adj_close                   yfinance adjusted close (ratios only; the LEVEL uses later info)
    """
    if field not in PRICE_FIELDS:
        raise ValueError(f"field must be one of {PRICE_FIELDS}")
    ids = _ids(series_ids)
    _check_ids(ids, "prices")
    s, e, a = _window(start, end, as_of)
    df = _as_of_query("clean.prices", "series_id", field, ids, s, e, a)
    return _wide(df, "series_id", field, ids, ffill_limit)


def get_features(feature_ids, start, end=None, *, as_of, ffill_limit: int | None = None) -> pd.DataFrame:
    """Model inputs built by features.py, e.g. ["curve_slope"]."""
    ids = _ids(feature_ids)
    _check_ids(ids, None, table="meta.features", key="feature_id")
    s, e, a = _window(start, end, as_of)
    df = _as_of_query("features.series", "feature_id", "value", ids, s, e, a)
    return _wide(df, "feature_id", "value", ids, ffill_limit)


def get_dividends(series_ids, start, end=None, *, as_of) -> pd.DataFrame:
    """Dividends per share as actually paid. Long format: series_id, ex_date, dividend."""
    ids = _ids(series_ids)
    _check_ids(ids, "prices")
    s, e, a = _window(start, end, as_of)
    return _latest_known(
        """
        SELECT series_id, ex_date, dividend, known_at
        FROM clean.corporate_actions
        WHERE series_id IN (SELECT unnest(?)) AND dividend > 0
          AND ex_date BETWEEN ? AND ? AND known_at <= ?
        """,
        "series_id, ex_date", "ex_date, series_id", [ids, s, e, a],
    )


def get_option_iv(underlyings, start, end=None, *, as_of, tenor_days: Iterable[int] | None = None,
                  moneyness_type: str | None = None, source: str | None = None) -> pd.DataFrame:
    """
    Implied vol grid. Long format:
      obs_date, underlying, tenor_days, moneyness_type, moneyness, iv, source
    Empty until option data is loaded.
    """
    ids = _ids(underlyings)
    s, e, a = _window(start, end, as_of)
    sql = """
        SELECT obs_date, underlying, tenor_days, moneyness_type, moneyness, iv, source, known_at
        FROM clean.option_iv
        WHERE underlying IN (SELECT unnest(?)) AND obs_date BETWEEN ? AND ? AND known_at <= ?
    """
    params: list = [ids, s, e, a]
    if tenor_days is not None:
        sql += " AND tenor_days IN (SELECT unnest(?))"
        params.append(list(tenor_days))
    if moneyness_type is not None:
        sql += " AND moneyness_type = ?"
        params.append(moneyness_type)
    if source is not None:
        sql += " AND source = ?"
        params.append(source)
    return _latest_known(
        sql, "underlying, obs_date, tenor_days, moneyness_type, moneyness, source",
        "obs_date, underlying, tenor_days, moneyness", params,
    )


def get_option_chain(underlying: str, *, as_of, obs_date=None, expiry_from=None, expiry_to=None,
                     source: str | None = None) -> pd.DataFrame:
    """
    All option contracts for one underlying on one day (obs_date defaults to as_of).
    Long format, one row per contract, with bid/ask/mid/iv/greeks.
    Empty until option data is loaded.
    """
    a = _to_date(as_of, "as_of")
    d = a if obs_date is None else _to_date(obs_date, "obs_date")
    if d > a:
        raise ValueError("obs_date cannot be after as_of")
    sql = """
        SELECT *
        FROM clean.option_quotes
        WHERE underlying = ? AND obs_date = ? AND known_at <= ?
    """
    params: list = [underlying, d, a]
    if expiry_from is not None:
        sql += " AND expiry >= ?"
        params.append(_to_date(expiry_from, "expiry_from"))
    if expiry_to is not None:
        sql += " AND expiry <= ?"
        params.append(_to_date(expiry_to, "expiry_to"))
    if source is not None:
        sql += " AND source = ?"
        params.append(source)
    return _latest_known(sql, "expiry, strike, call_put, source", "expiry, call_put, strike", params)


# -----------------------------------------------------------------------------
# Catalogues
# -----------------------------------------------------------------------------

def list_series() -> pd.DataFrame:
    """The meta.series catalogue, with first/last date currently held."""
    return _market().execute(
        """
        WITH held AS (
            SELECT series_id, min(obs_date) AS first_date, max(obs_date) AS last_date FROM raw.series GROUP BY 1
            UNION ALL
            SELECT series_id, min(obs_date), max(obs_date) FROM raw.prices GROUP BY 1
        )
        SELECT m.*, h.first_date, h.last_date
        FROM meta.series m LEFT JOIN held h USING (series_id)
        ORDER BY m.storage, m.source, m.series_id
        """
    ).df()


def list_features() -> pd.DataFrame:
    return _market().execute("SELECT * FROM meta.features ORDER BY feature_id").df()


# -----------------------------------------------------------------------------
# Trading record reads (for Reporting / analysis after a run)
# -----------------------------------------------------------------------------

TRADING_TABLES = ("runs", "instruments", "regime_probs", "allocations", "target_positions",
                  "risk_events", "positions", "orders", "fills", "cash_ledger", "nav")


def get_trading_records(table: str, run_id: str | None = None) -> pd.DataFrame:
    """
    Read one trading.duckdb table, optionally for one run. Opens the file
    read-only and closes it again, so it fails while a run is writing.
    """
    if table not in TRADING_TABLES:
        raise ValueError(f"table must be one of {TRADING_TABLES}")
    con = connect_trading(read_only=True)
    try:
        if run_id is None or table == "instruments":
            return con.execute(f"SELECT * FROM {table}").df()
        return con.execute(f"SELECT * FROM {table} WHERE run_id = ?", [run_id]).df()
    finally:
        con.close()


__all__ = [
    "get_series", "get_prices", "get_features", "get_dividends",
    "get_option_iv", "get_option_chain",
    "list_series", "list_features", "get_trading_records", "close",
]
