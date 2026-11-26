"""
CBOE free daily index files (VIX, VIX3M, VIX9D, VVIX, VXN, SKEW, OVX, GVZ, PUT).

Each file is the full history. Some have DATE,OPEN,HIGH,LOW,CLOSE; others
have DATE,<NAME>. We store the daily close in raw.series, or in raw.prices
(close as every bar field) when meta.series says storage = 'prices', so an
index like PUT can be "held" in a backtest.
"""

from __future__ import annotations

import io
import time
from datetime import datetime

import pandas as pd
import requests

from Data.DataBase.db import write_prices, write_series
from Data.DataSources._common import active_series, drop_today, run_each

URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{code}_History.csv"
HEADERS = {"User-Agent": "Mozilla/5.0 (LTG Quant research data loader)"}


def fetch(source_code: str) -> pd.DataFrame:
    """Full history of one CBOE index -> DataFrame(obs_date, value)."""
    r = requests.get(URL.format(code=source_code), headers=HEADERS, timeout=60)
    r.raise_for_status()
    raw = pd.read_csv(io.StringIO(r.text))
    raw.columns = [c.strip().upper() for c in raw.columns]
    value_col = "CLOSE" if "CLOSE" in raw.columns else raw.columns[1]
    df = pd.DataFrame({
        "obs_date": pd.to_datetime(raw["DATE"], format="%m/%d/%Y"),
        "value": pd.to_numeric(raw[value_col], errors="coerce"),
    })
    return df.dropna(subset=["value"])


def refresh(con, refresh_id: str, fetched_at: datetime):
    storage = dict(con.execute("SELECT series_id, storage FROM meta.series WHERE source = 'cboe'").fetchall())

    def one(series_id: str, code: str) -> int:
        df = drop_today(fetch(code))
        df["series_id"] = series_id
        time.sleep(0.5)
        if storage[series_id] == "prices":
            # an index has no bar or volume: the close stands in for every field
            for col in ["open", "high", "low", "close", "adj_close"]:
                df[col] = df["value"]
            df["volume"] = 0.0
            return write_prices(con, df, fetched_at)
        return write_series(con, df, fetched_at)

    return run_each(con, refresh_id, "cboe", active_series(con, "cboe"), one)
