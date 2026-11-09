"""
CBOE free daily index files (VIX, VIX3M, VIX9D, VVIX, VXN, SKEW, OVX, GVZ).

Each file is the full history. Some have DATE,OPEN,HIGH,LOW,CLOSE; others
have DATE,<NAME>. We store the daily close in raw.series.
"""

from __future__ import annotations

import io
import time
from datetime import datetime

import pandas as pd
import requests

from Data.DataBase.db import write_series
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
    def one(series_id: str, code: str) -> int:
        df = drop_today(fetch(code))
        df["series_id"] = series_id
        time.sleep(0.5)
        return write_series(con, df, fetched_at)

    return run_each(con, refresh_id, "cboe", active_series(con, "cboe"), one)
