"""
features.py : builds model inputs from the clean data already in the database.

Runs as the last step of refresh.py (or alone: refresh.py --only features).
Nothing is downloaded here.

What it writes:
  meta.features    the catalogue below (one row per feature, kept in sync)
  features.series  daily values, long format: feature_id, obs_date, value, known_at

The as-of rule still holds:
  known_at of a feature on a day = the LATEST known_at among the inputs used
  that day. E.g. curve_slope uses FRED (known next business day), so it is
  known next business day too.

No scaling or z-scoring here: that is fitted inside the model on past data
only (ModelHome). Names are ours; change them here and they change everywhere.

To add a feature: write a function returning (value, known_at) and add one
line to FEATURES.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

import numpy as np
import pandas as pd

from Data.DataBase.db import write_features
from Data.DataSources._common import run_each

TRADING_DAYS = 252


# -----------------------------------------------------------------------------
# Loading inputs (latest version of every value, from the clean views)
# -----------------------------------------------------------------------------

class Inputs:
    """Loads each input once per run. Every getter returns (value, known_at), both wide."""

    def __init__(self, con):
        self.con = con
        self._cache: dict[tuple, tuple[pd.DataFrame, pd.DataFrame]] = {}

    def _load(self, view: str, field: str, ids: tuple[str, ...]) -> tuple[pd.DataFrame, pd.DataFrame]:
        key = (view, field, ids)
        if key not in self._cache:
            df = self.con.execute(
                f"""
                WITH x AS MATERIALIZED (
                    SELECT series_id, obs_date, {field} AS v, known_at
                    FROM {view} WHERE series_id IN (SELECT unnest(?))
                )
                SELECT * FROM x
                QUALIFY row_number() OVER (PARTITION BY series_id, obs_date ORDER BY known_at DESC) = 1
                """,
                [list(ids)],
            ).df()
            value = df.pivot(index="obs_date", columns="series_id", values="v").reindex(columns=list(ids))
            known = df.pivot(index="obs_date", columns="series_id", values="known_at").reindex(columns=list(ids))
            value.index = pd.DatetimeIndex(value.index)
            known.index = pd.DatetimeIndex(known.index)
            known = known.apply(pd.to_datetime)
            self._cache[key] = (value.astype(float), known)
        return self._cache[key]

    def series(self, *ids: str):
        return self._load("clean.series", "value", ids)

    def returns(self, *ids: str):
        return self._load("clean.prices", "total_return", ids)


# -----------------------------------------------------------------------------
# Feature definitions. Each returns (value: Series, known_at: Series) by date.
# -----------------------------------------------------------------------------

Result = tuple[pd.Series, pd.Series]


def _both(v: pd.DataFrame, k: pd.DataFrame, out: pd.Series) -> Result:
    """Keep dates where every input exists; known_at = latest input known_at."""
    ok = v.notna().all(axis=1) & out.notna()
    return out[ok], k[ok].max(axis=1)


def curve_slope(x: Inputs) -> Result:
    v, k = x.series("ust_10y", "ust_2y")
    return _both(v, k, v["ust_10y"] - v["ust_2y"])


def _credit(x: Inputs) -> Result:
    """Bloomberg hy_oas (basis points) where we have it, else the FRED copy (percent). Output in percent."""
    bb_v, bb_k = x.series("hy_oas")
    fr_v, fr_k = x.series("hy_oas_fred")
    v = (bb_v["hy_oas"] / 100.0).combine_first(fr_v["hy_oas_fred"])
    k = bb_k["hy_oas"].where(bb_v["hy_oas"].notna()).combine_first(fr_k["hy_oas_fred"])
    ok = v.notna()
    return v[ok], k[ok]


def credit_spread(x: Inputs) -> Result:
    return _credit(x)


def credit_spread_chg_20d(x: Inputs) -> Result:
    v, k = _credit(x)
    out = v - v.shift(20)  # 20 observations back; known_at of day t covers the window
    ok = out.notna()
    return out[ok], k[ok]


def log_vix(x: Inputs) -> Result:
    v, k = x.series("vix")
    out = np.log(v["vix"].where(v["vix"] > 0))
    return _both(v, k, out)


def vix_term(x: Inputs) -> Result:
    v, k = x.series("vix", "vix3m")
    return _both(v, k, v["vix"] / v["vix3m"])


def trend(series_id: str) -> Callable[[Inputs], Result]:
    """12-month (252 trading days) total return, dividends included."""
    def f(x: Inputs) -> Result:
        r, k = x.returns(series_id)
        out = (1 + r[series_id]).rolling(TRADING_DAYS, min_periods=TRADING_DAYS).apply(np.prod, raw=True) - 1
        return _both(r, k, out)
    return f


def realised_vol(series_id: str, days: int) -> Callable[[Inputs], Result]:
    """Annualised realised vol over `days` trading days: sqrt(252 * mean(r^2))."""
    def f(x: Inputs) -> Result:
        r, k = x.returns(series_id)
        out = np.sqrt(TRADING_DAYS * (r[series_id] ** 2).rolling(days, min_periods=days).mean())
        return _both(r, k, out)
    return f


# feature_id: (function, description, inputs, units)
FEATURES: dict[str, tuple[Callable[[Inputs], Result], str, str, str]] = {
    "curve_slope": (curve_slope, "10y minus 2y Treasury yield", "ust_10y, ust_2y", "percentage points"),
    "credit_spread": (credit_spread, "High-yield OAS: Bloomberg full history, FRED copy where missing",
                      "hy_oas, hy_oas_fred", "percent"),
    "credit_spread_chg_20d": (credit_spread_chg_20d, "20-day change in credit_spread",
                              "hy_oas, hy_oas_fred", "percentage points"),
    "log_vix": (log_vix, "Natural log of VIX", "vix", "log index points"),
    "vix_term": (vix_term, "VIX / VIX3M (above 1 = inverted, stress)", "vix, vix3m", "ratio"),
}
for _sid in ("spy", "tlt", "gld", "dbc"):
    FEATURES[f"trend_{_sid}"] = (trend(_sid), f"12-month total return of {_sid.upper()}", _sid, "decimal return")
for _sid in ("spy", "qqq"):
    for _d in (1, 5, 22):
        FEATURES[f"rv_{_sid}_{_d}d"] = (realised_vol(_sid, _d),
                                         f"{_d}-day realised vol of {_sid.upper()}, annualised (HAR input)",
                                         _sid, "annualised decimal")


# -----------------------------------------------------------------------------
# Run
# -----------------------------------------------------------------------------

def sync_catalogue(con) -> None:
    """Make meta.features match FEATURES (adds, updates; never deletes stored values)."""
    rows = [(fid, desc, inputs, units, None) for fid, (_f, desc, inputs, units) in FEATURES.items()]
    con.executemany("INSERT OR REPLACE INTO meta.features VALUES (?, ?, ?, ?, ?)", rows)


def refresh(con, refresh_id: str, fetched_at: datetime):
    sync_catalogue(con)
    x = Inputs(con)

    def one(feature_id: str, _code: str) -> int:
        value, known = FEATURES[feature_id][0](x)
        df = pd.DataFrame({"feature_id": feature_id, "obs_date": value.index,
                           "value": value.values, "known_at": known.values})
        return write_features(con, df, fetched_at)

    return run_each(con, refresh_id, "features", [(f, f) for f in FEATURES], one)
