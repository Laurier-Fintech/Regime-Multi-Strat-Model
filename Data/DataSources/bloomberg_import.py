"""
Loads CSVs exported by hand from the Bloomberg terminal (Prism lab).

Bloomberg can't be queried from code here. Export to CSV, save into the
git-ignored folder below, then run refresh.py. NEVER commit these files:
Bloomberg's licence forbids redistribution and the repo is public.

    Data/DataSources/bloomberg_exports/
        series/<series_id>.csv        e.g. series/hy_oas.csv
            columns: date, value      (first two columns are used; header row required)
        option_iv/<underlying>.csv    e.g. option_iv/spx.csv
            columns: date, tenor_days, moneyness_type, moneyness, iv  (iv as decimal, 0.20)
                  or ... , iv_pct                                       (iv as percent, 20.0)
            moneyness_type is 'pct_spot' (100 = ATM) or 'delta' (25, 50 ...)

Re-importing the same file is safe: unchanged rows are skipped.
The exact export layout will be confirmed once we see a real Prism export.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from Data.DataBase.db import log_refresh, write_option_iv, write_series

EXPORT_DIR = Path(__file__).resolve().parent / "bloomberg_exports"


def has_files() -> bool:
    return any(EXPORT_DIR.glob("*/*.csv"))


def _read_series(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path)
    df = pd.DataFrame({
        "obs_date": pd.to_datetime(raw.iloc[:, 0]),
        "value": pd.to_numeric(raw.iloc[:, 1], errors="coerce"),
    })
    return df.dropna()


def _read_option_iv(path: Path, underlying: str) -> pd.DataFrame:
    raw = pd.read_csv(path)
    raw.columns = [c.strip().lower() for c in raw.columns]
    if "iv" not in raw and "iv_pct" in raw:
        raw["iv"] = pd.to_numeric(raw["iv_pct"], errors="coerce") / 100.0
    need = {"date", "tenor_days", "moneyness_type", "moneyness", "iv"}
    if missing := need - set(raw.columns):
        raise ValueError(f"{path.name} is missing columns {sorted(missing)}")
    return pd.DataFrame({
        "underlying": underlying,
        "obs_date": pd.to_datetime(raw["date"]),
        "tenor_days": raw["tenor_days"].astype(int),
        "moneyness_type": raw["moneyness_type"].str.strip(),
        "moneyness": raw["moneyness"].astype(float),
        "iv": raw["iv"],
        "source": "bloomberg",
    })


def refresh(con, refresh_id: str, fetched_at: datetime):
    known = {r[0] for r in con.execute(
        "SELECT series_id FROM meta.series WHERE source = 'bloomberg'").fetchall()}
    all_ids = {r[0] for r in con.execute("SELECT series_id FROM meta.series").fetchall()}
    results = []

    def _do(series_id: str, fn) -> None:
        started = datetime.now()
        try:
            n, status, msg = fn(), "ok", None
        except Exception as e:
            n, status, msg = 0, "error", f"{type(e).__name__}: {e}"
        log_refresh(con, refresh_id, "bloomberg", series_id, started, n, status, msg)
        print(f"  bloomberg {series_id:<15} {status:<6} {n:>7} rows" + (f"  {msg}" if msg else ""))
        results.append((series_id, n, status, msg))

    def _series_file(path: Path) -> int:
        if path.stem not in known:
            raise KeyError(f"'{path.stem}' is not a bloomberg series in meta.series (file {path.name})")
        return write_series(con, _read_series(path).assign(series_id=path.stem), fetched_at)

    def _iv_file(path: Path) -> int:
        if path.stem not in all_ids:
            raise KeyError(f"underlying '{path.stem}' is not in meta.series (file {path.name})")
        return write_option_iv(con, _read_option_iv(path, path.stem), fetched_at, lag_days=0)

    for path in sorted((EXPORT_DIR / "series").glob("*.csv")):
        _do(path.stem, lambda p=path: _series_file(p))
    for path in sorted((EXPORT_DIR / "option_iv").glob("*.csv")):
        _do(f"iv:{path.stem}", lambda p=path: _iv_file(p))

    return results
