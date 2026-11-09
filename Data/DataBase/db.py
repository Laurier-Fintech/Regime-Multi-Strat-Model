"""
Opening the two DuckDB files, plus the write helpers.

Who uses what:
  - Everyone READS market data through access.py (never through this file).
  - Data/DataSources writes market data with the write_* helpers below.
  - ModelHome / Portfolio / Backtesting write trading records with
    connect_trading() + append_rows().

DuckDB rule: one program can open a file for writing, OR many programs can
open it read-only, never both at once. So market_data.duckdb is opened
read-only by default.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = REPO_ROOT / "Config" / "configs.yaml"
SETUP_DIR = Path(__file__).resolve().parent / "setup_run_once"

MARKET_SCHEMA_VERSION = 1
TRADING_SCHEMA_VERSION = 1


# -----------------------------------------------------------------------------
# Paths and connections
# -----------------------------------------------------------------------------

def _db_config() -> dict:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)["database"]


def market_db_path() -> Path:
    return REPO_ROOT / _db_config()["market_data"]


def trading_db_path() -> Path:
    return REPO_ROOT / _db_config()["trading"]


def _missing_file_message(path: Path) -> str:
    return (
        f"Database file not found: {path}\n"
        "  - First time? Run:  python Data/DataBase/setup_run_once/create_databases.py\n"
        "  - Want the filled market data? Copy market_data.duckdb from OneDrive into "
        f"{path.parent} (never open it straight from OneDrive)."
    )


def connect_market(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """Open market_data.duckdb. Read-only unless you are Data/DataSources."""
    path = market_db_path()
    if not path.exists():
        raise FileNotFoundError(_missing_file_message(path))
    return duckdb.connect(str(path), read_only=read_only)


def connect_trading(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open trading.duckdb. Writable by default (ModelHome / Portfolio / Backtesting)."""
    path = trading_db_path()
    if not path.exists():
        raise FileNotFoundError(_missing_file_message(path))
    return duckdb.connect(str(path), read_only=read_only)


# -----------------------------------------------------------------------------
# Trading-record writes
# -----------------------------------------------------------------------------

def append_rows(con: duckdb.DuckDBPyConnection, table: str, df: pd.DataFrame) -> int:
    """
    Append a DataFrame to a trading.duckdb table, matching columns by name.
    Columns you leave out get the table default (or NULL). Returns rows added.
    """
    if df.empty:
        return 0
    con.register("_rows", df)
    try:
        con.execute(f"INSERT INTO {table} BY NAME SELECT * FROM _rows")
    finally:
        con.unregister("_rows")
    return len(df)


# -----------------------------------------------------------------------------
# Market-data writes (Data/DataSources only)
# -----------------------------------------------------------------------------

def _to_date_col(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s).dt.date


def add_business_days(dates: pd.Series, lag: int | pd.Series) -> pd.Series:
    """obs_date + lag business days (Mon-Fri; holidays added once Common/calendar exists)."""
    d = np.array(pd.to_datetime(dates).values, dtype="datetime64[D]")
    out = np.busday_offset(d, np.asarray(lag, dtype=int), roll="forward")
    return pd.Series(pd.to_datetime(out).date, index=dates.index)


def publish_lags(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    rows = con.execute("SELECT series_id, publish_lag_days FROM meta.series").fetchall()
    return dict(rows)


def _write_versioned(
    con: duckdb.DuckDBPyConnection,
    table: str,
    df: pd.DataFrame,
    keys: list[str],
    values: list[str],
    fetched_at: datetime,
    revisions: bool,
    extra: tuple[str, ...] = (),
    stamp_col: str = "fetched_at",
) -> int:
    """
    Core write rule (never overwrite):
      - key not in the table yet         -> insert with known_at = df.known_default
      - key exists, values unchanged     -> skip
      - key exists, values changed       -> if revisions: insert a NEW row with
                                            known_at = max(known_default, fetch day)
                                            else: skip (prices are never revised)
    df must hold the keys, values and a 'known_default' column. 'extra' columns
    are written as-is but not compared (e.g. text ids). stamp_col is the
    table's run-time column (fetched_at, or computed_at for features).
    Returns the number of rows written.
    """
    if df.empty:
        return 0

    df = df.copy()
    df["fetched_at"] = fetched_at
    con.register("_incoming", df)
    try:
        key_list = ", ".join(keys)
        join = " AND ".join(f"i.{k} = l.{k}" for k in keys)
        changed = " OR ".join(
            f"(i.{v} IS DISTINCT FROM l.{v} AND NOT (i.{v} IS NOT NULL AND l.{v} IS NOT NULL "
            f"AND abs(i.{v} - l.{v}) <= 1e-9 * greatest(1, abs(l.{v}))))"
            for v in values
        )
        cols = ", ".join(f"i.{c}" for c in keys + values + list(extra))
        where = "l._exists IS NULL"
        if revisions:
            where += f" OR ({changed})"

        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE _to_write AS
            WITH l AS (
                SELECT {key_list}, {", ".join(values)}, TRUE AS _exists
                FROM {table}
                QUALIFY row_number() OVER (PARTITION BY {key_list} ORDER BY known_at DESC) = 1
            )
            SELECT {cols},
                   CASE WHEN l._exists IS NULL THEN CAST(i.known_default AS DATE)
                        ELSE greatest(CAST(i.known_default AS DATE), CAST(i.fetched_at AS DATE))
                   END AS known_at,
                   CAST(i.fetched_at AS TIMESTAMP) AS {stamp_col}
            FROM _incoming i
            LEFT JOIN l ON {join}
            WHERE {where}
        """)
        n = con.execute("SELECT count(*) FROM _to_write").fetchone()[0]
        if n:
            # OR REPLACE only matters if a value is revised twice on the same day.
            con.execute(f"INSERT OR REPLACE INTO {table} BY NAME SELECT * FROM _to_write")
        con.execute("DROP TABLE _to_write")
    finally:
        con.unregister("_incoming")
    return int(n)


def write_series(con, df: pd.DataFrame, fetched_at: datetime) -> int:
    """df columns: series_id, obs_date, value. Writes raw.series."""
    df = df[["series_id", "obs_date", "value"]].copy()
    df["obs_date"] = _to_date_col(df["obs_date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce").astype(float)
    df = df.dropna(subset=["value"])
    lags = publish_lags(con)
    df["known_default"] = add_business_days(df["obs_date"], df["series_id"].map(lags))
    return _write_versioned(con, "raw.series", df, ["series_id", "obs_date"], ["value"],
                            fetched_at, revisions=True)


def write_prices(con, df: pd.DataFrame, fetched_at: datetime) -> int:
    """df columns: series_id, obs_date, open, high, low, close, adj_close, volume. Writes raw.prices (new dates only)."""
    cols = ["open", "high", "low", "close", "adj_close", "volume"]
    df = df[["series_id", "obs_date"] + cols].copy()
    df["obs_date"] = _to_date_col(df["obs_date"])
    df[cols] = df[cols].astype(float)
    lags = publish_lags(con)
    df["known_default"] = add_business_days(df["obs_date"], df["series_id"].map(lags))
    return _write_versioned(con, "raw.prices", df, ["series_id", "obs_date"], cols,
                            fetched_at, revisions=False)


def write_corporate_actions(con, df: pd.DataFrame, fetched_at: datetime) -> int:
    """df columns: series_id, ex_date, dividend, split_ratio. Writes raw.corporate_actions (new dates only)."""
    df = df[["series_id", "ex_date", "dividend", "split_ratio"]].copy()
    df["ex_date"] = _to_date_col(df["ex_date"])
    df[["dividend", "split_ratio"]] = df[["dividend", "split_ratio"]].astype(float)
    df["known_default"] = df["ex_date"]
    return _write_versioned(con, "raw.corporate_actions", df, ["series_id", "ex_date"],
                            ["dividend", "split_ratio"], fetched_at, revisions=False)


def write_option_iv(con, df: pd.DataFrame, fetched_at: datetime, lag_days: int = 0) -> int:
    """df columns: underlying, obs_date, tenor_days, moneyness_type, moneyness, iv, source."""
    keys = ["underlying", "obs_date", "tenor_days", "moneyness_type", "moneyness", "source"]
    df = df[keys + ["iv"]].copy()
    df["obs_date"] = _to_date_col(df["obs_date"])
    df["iv"] = pd.to_numeric(df["iv"], errors="coerce").astype(float)
    df = df.dropna(subset=["iv"])
    df["known_default"] = add_business_days(df["obs_date"], lag_days)
    return _write_versioned(con, "raw.option_iv", df, keys, ["iv"], fetched_at, revisions=True)


def write_option_quotes(con, df: pd.DataFrame, fetched_at: datetime, lag_days: int = 0) -> int:
    """df columns: the keys below plus any of the raw.option_quotes value columns."""
    keys = ["underlying", "obs_date", "expiry", "strike", "call_put", "source"]
    value_cols = ["bid", "ask", "last", "volume", "open_interest", "iv",
                  "delta", "gamma", "vega", "theta", "underlying_price"]
    df = df.copy()
    for c in value_cols:
        if c not in df:
            df[c] = np.nan
    if "contract_id" not in df:
        df["contract_id"] = None
    df = df[keys + ["contract_id"] + value_cols]
    df["obs_date"] = _to_date_col(df["obs_date"])
    df["expiry"] = _to_date_col(df["expiry"])
    df[value_cols] = df[value_cols].astype(float)
    df["known_default"] = add_business_days(df["obs_date"], lag_days)
    return _write_versioned(con, "raw.option_quotes", df, keys, value_cols, fetched_at,
                            revisions=True, extra=("contract_id",))


def write_features(con, df: pd.DataFrame, computed_at: datetime) -> int:
    """
    df columns: feature_id, obs_date, value, known_at. Writes features.series.
    known_at comes from the inputs (the latest known_at among them), not from
    a publish lag. Unchanged values are skipped; changed ones are added as new
    rows, like a revision.
    """
    df = df[["feature_id", "obs_date", "value", "known_at"]].copy()
    df["obs_date"] = _to_date_col(df["obs_date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce").astype(float)
    df = df[np.isfinite(df["value"])]
    df["known_default"] = _to_date_col(df.pop("known_at"))
    return _write_versioned(con, "features.series", df, ["feature_id", "obs_date"], ["value"],
                            computed_at, revisions=True, stamp_col="computed_at")


def log_refresh(con, refresh_id: str, source: str, series_id: str,
                started_at: datetime, rows_written: int, status: str,
                message: str | None = None) -> None:
    con.execute(
        "INSERT INTO meta.refresh_log VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [refresh_id, source, series_id, started_at, datetime.now(), rows_written, status, message],
    )


def today_local() -> date:
    return datetime.now().date()
