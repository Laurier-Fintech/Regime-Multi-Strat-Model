"""
yfinance daily bars for ETFs and indices (SPY, QQQ, TQQQ, ..., ^GSPC, ^NDX, ^MOVE),
plus their dividends and splits.

Stored exactly as yfinance returns them (prices split-adjusted as of the
download). clean.prices turns them back into the prices that actually traded.
Only NEW dates are added on later runs. yfinance is unofficial and
rate-limited: download once here, never from a backtest.
"""

from __future__ import annotations

import time
from datetime import datetime

import pandas as pd
import yfinance as yf

from Data.DataBase.db import write_corporate_actions, write_prices
from Data.DataSources._common import active_series, drop_today, os_ca_bundle, run_each


_session = None


def _get_session():
    """One shared HTTP session that trusts the OS certificate store."""
    global _session
    if _session is None:
        from curl_cffi import requests as curl_requests
        _session = curl_requests.Session(impersonate="chrome", verify=os_ca_bundle())
    return _session


def fetch(source_code: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Full history -> (bars, corporate_actions)."""
    h = yf.Ticker(source_code, session=_get_session()).history(
        period="max", auto_adjust=False, actions=True, raise_errors=True)
    if h.empty:
        raise RuntimeError(f"yfinance returned no data for {source_code}")
    h.index = pd.DatetimeIndex(h.index).tz_localize(None).normalize()
    bars = pd.DataFrame({
        "obs_date": h.index,
        "open": h["Open"].values,
        "high": h["High"].values,
        "low": h["Low"].values,
        "close": h["Close"].values,
        "adj_close": h["Adj Close"].values,
        "volume": h["Volume"].values,
    })
    div = h["Dividends"] if "Dividends" in h else pd.Series(0.0, index=h.index)
    spl = h["Stock Splits"] if "Stock Splits" in h else pd.Series(0.0, index=h.index)
    acts = pd.DataFrame({"ex_date": h.index, "dividend": div.values, "split_ratio": spl.values})
    acts = acts[(acts["dividend"] > 0) | (acts["split_ratio"] > 0)]
    acts.loc[acts["dividend"] <= 0, "dividend"] = None
    acts.loc[acts["split_ratio"] <= 0, "split_ratio"] = None
    return bars, acts


def refresh(con, refresh_id: str, fetched_at: datetime):
    def one(series_id: str, code: str) -> int:
        bars, acts = fetch(code)
        bars = drop_today(bars)
        acts = drop_today(acts, "ex_date")
        bars["series_id"] = series_id
        acts["series_id"] = series_id
        n = write_prices(con, bars, fetched_at)
        n += write_corporate_actions(con, acts, fetched_at)
        time.sleep(1.0)
        return n

    return run_each(con, refresh_id, "yfinance", active_series(con, "yfinance"), one)
