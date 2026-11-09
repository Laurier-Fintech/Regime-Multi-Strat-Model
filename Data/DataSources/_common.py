"""Small helpers shared by the source modules."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

import pandas as pd

from Data.DataBase.db import log_refresh, today_local


def os_ca_bundle() -> str:
    """
    Path to a PEM file with certifi's certificates PLUS the operating system's
    (on Windows). Needed by libraries like yfinance's curl_cffi that don't use
    the OS store, on machines where antivirus / school networks re-sign HTTPS.
    """
    import ssl
    import tempfile
    from pathlib import Path

    import certifi

    pem = Path(certifi.where()).read_text(encoding="ascii")
    if hasattr(ssl, "enum_certificates"):  # Windows only
        extra = []
        for store in ("ROOT", "CA"):
            for cert, enc, _trust in ssl.enum_certificates(store):
                if enc == "x509_asn":
                    extra.append(ssl.DER_cert_to_PEM_cert(cert))
        pem += "\n" + "".join(extra)
    out = Path(tempfile.gettempdir()) / "ltg_ca_bundle.pem"
    out.write_text(pem, encoding="ascii")
    return str(out)


def active_series(con, source: str) -> list[tuple[str, str]]:
    """[(series_id, source_code), ...] for active series of one source."""
    return con.execute(
        "SELECT series_id, source_code FROM meta.series WHERE source = ? AND is_active ORDER BY series_id",
        [source],
    ).fetchall()


def drop_today(df: pd.DataFrame, date_col: str = "obs_date") -> pd.DataFrame:
    """Drop today's row: during market hours it is a partial, not a close."""
    return df[pd.to_datetime(df[date_col]).dt.date < today_local()]


def run_each(con, refresh_id: str, source: str, items: list[tuple[str, str]],
             one: Callable[[str, str], int]) -> list[tuple[str, int, str, str | None]]:
    """
    Call one(series_id, source_code) -> rows_written for each item, log every
    result to meta.refresh_log, and keep going if one series fails.
    """
    results = []
    for series_id, code in items:
        started = datetime.now()
        try:
            n = one(series_id, code)
            status, msg = "ok", None
        except Exception as e:  # one bad series must not stop the others
            n, status, msg = 0, "error", f"{type(e).__name__}: {e}"
        log_refresh(con, refresh_id, source, series_id, started, n, status, msg)
        print(f"  {source:<9} {series_id:<22} {status:<6} {n:>7} rows" + (f"  {msg}" if msg else ""))
        results.append((series_id, n, status, msg))
    return results
