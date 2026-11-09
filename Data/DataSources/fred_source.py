"""
FRED downloads (Treasury yields, T-bill, credit spreads, WTI, USD/CAD).

Needs a free FRED API key in Config/.env:  FRED_API_KEY=...
  https://fred.stlouisfed.org/docs/api/api_key.html

Downloads full history every time; the writer only stores new dates and
genuine revisions (as new rows), so re-running is safe.
"""

from __future__ import annotations

import os
import time
from datetime import datetime

import pandas as pd
import requests
from dotenv import load_dotenv

from Data.DataBase.db import REPO_ROOT, write_series
from Data.DataSources._common import active_series, drop_today, run_each

API_URL = "https://api.stlouisfed.org/fred/series/observations"


def _api_key() -> str:
    load_dotenv(REPO_ROOT / "Config" / ".env")
    key = os.getenv("FRED_API_KEY", "").strip()
    if not key:
        raise RuntimeError("FRED_API_KEY is empty. Put your free key in Config/.env (see Config/.env.example).")
    return key


def fetch(source_code: str, api_key: str) -> pd.DataFrame:
    """Full history of one FRED series -> DataFrame(obs_date, value). Missing ('.') dropped."""
    try:
        r = requests.get(
            API_URL,
            params={"series_id": source_code, "api_key": api_key, "file_type": "json"},
            timeout=60,
        )
        r.raise_for_status()
        obs = r.json()["observations"]
    except Exception as e:
        # Error text includes the URL with the key; never let it reach logs or the database.
        raise RuntimeError(str(e).replace(api_key, "<FRED_API_KEY>")) from None
    df = pd.DataFrame(obs, columns=["date", "value"]).rename(columns={"date": "obs_date"})
    df["value"] = pd.to_numeric(df["value"], errors="coerce")  # '.' -> NaN
    return df.dropna(subset=["value"])


def refresh(con, refresh_id: str, fetched_at: datetime):
    api_key = _api_key()

    def one(series_id: str, code: str) -> int:
        df = drop_today(fetch(code, api_key))
        df["series_id"] = series_id
        time.sleep(0.5)  # stay well under FRED's rate limit
        return write_series(con, df, fetched_at)

    return run_each(con, refresh_id, "fred", active_series(con, "fred"), one)
