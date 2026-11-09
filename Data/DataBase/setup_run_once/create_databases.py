"""
=====================  ONE-TIME SCRIPT  =====================

Creates the two EMPTY database files from the .sql schemas in this folder:
    Data/DataBase/market_data.duckdb
    Data/DataBase/trading.duckdb

Run from the repo root:
    python Data/DataBase/setup_run_once/create_databases.py

Safe by design: a file that already exists is NEVER touched (skipped).
So if you copied a filled market_data.duckdb from OneDrive, running this
only creates the missing trading.duckdb.

To start completely fresh you must delete the .duckdb file yourself first.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root

import duckdb  # noqa: E402

from Data.DataBase.db import (  # noqa: E402
    MARKET_SCHEMA_VERSION,
    SETUP_DIR,
    TRADING_SCHEMA_VERSION,
    market_db_path,
    trading_db_path,
)


def _create(path: Path, schema_file: str, version_table: str, db_name: str, version: int) -> None:
    if path.exists():
        print(f"SKIPPED  {path.name} already exists (not touched).")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    sql = (SETUP_DIR / schema_file).read_text(encoding="utf-8")
    con = duckdb.connect(str(path))
    try:
        con.execute("BEGIN")
        con.execute(sql)
        con.execute(
            f"INSERT INTO {version_table} VALUES (?, ?, ?, ?)",
            [db_name, version, duckdb.__version__, datetime.now()],
        )
        con.execute("COMMIT")
    except Exception:
        con.close()
        path.unlink(missing_ok=True)  # don't leave a half-built file behind
        raise
    con.close()
    print(f"CREATED  {path}  (schema v{version}, duckdb {duckdb.__version__})")


def main() -> None:
    _create(market_db_path(), "schema_market.sql", "meta.schema_version", "market_data", MARKET_SCHEMA_VERSION)
    _create(trading_db_path(), "schema_trading.sql", "schema_version", "trading", TRADING_SCHEMA_VERSION)
    print("\nNext: fill market data with  python Data/DataSources/refresh.py")


if __name__ == "__main__":
    main()
