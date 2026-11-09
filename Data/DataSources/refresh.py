"""
=====================  ENTRY POINT: FILL / UPDATE MARKET DATA  =====================

Downloads everything and writes it into Data/DataBase/market_data.duckdb.
This is the ONLY program that writes market data.

Run from the repo root:
    python Data/DataSources/refresh.py                  # all sources
    python Data/DataSources/refresh.py --only cboe fred # just some
    python Data/DataSources/refresh.py --only features  # rebuild features only

Before running: close anything else that has market_data.duckdb open
(notebooks, backtests). DuckDB allows one writer OR many readers, not both.

Safe to re-run any time: unchanged rows are skipped, new dates are added,
and real revisions are stored as new rows (never overwritten).
Every run is recorded in meta.refresh_log.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root

import truststore  # noqa: E402

truststore.inject_into_ssl()  # use the OS certificate store (fixes SSL errors on school/Windows machines)

from Data.DataBase.db import connect_market  # noqa: E402
from Data.DataSources import (  # noqa: E402
    bloomberg_import,
    cboe_source,
    features,
    fred_source,
    yfinance_source,
)

SOURCES = {
    "fred": fred_source.refresh,
    "cboe": cboe_source.refresh,
    "yfinance": yfinance_source.refresh,
    "bloomberg": bloomberg_import.refresh,
    "features": features.refresh,   # last: built from the data loaded above
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Fill / update market_data.duckdb")
    p.add_argument("--only", nargs="+", choices=list(SOURCES), help="run only these sources")
    args = p.parse_args(argv)

    chosen = args.only or list(SOURCES)
    refresh_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    fetched_at = datetime.now()

    try:
        con = connect_market(read_only=False)
    except Exception as e:
        print(f"Could not open market_data.duckdb for writing:\n{e}\n"
              "Is it open somewhere else (notebook, backtest)? Close that and retry.")
        return 1

    errors = 0
    try:
        print(f"Refresh {refresh_id}")
        for name in chosen:
            if name == "bloomberg" and not bloomberg_import.has_files():
                print("  bloomberg: no export files in Data/DataSources/bloomberg_exports/, skipped")
                continue
            print(f"[{name}]")
            try:
                results = SOURCES[name](con, refresh_id, fetched_at)
                errors += sum(1 for r in results if r[2] == "error")
            except Exception as e:  # e.g. missing API key: skip the source, keep going
                print(f"  {name} FAILED: {type(e).__name__}: {e}")
                errors += 1
        con.execute("CHECKPOINT")
    finally:
        con.close()

    print(f"\nDone. {errors} error(s). Details: meta.refresh_log where refresh_id = '{refresh_id}'")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
