# ⚠️ ONE-TIME SETUP: run once, then leave alone

Everything in this folder exists only to **create the two empty database files**. You run it once per computer. Nothing else in the system imports from here.

| File | What it is |
|---|---|
| `create_databases.py` | **The script you run.** Builds the empty `market_data.duckdb` and `trading.duckdb` in `Data/DataBase/`. |
| `schema_market.sql` | Table definitions for market data, plus the catalogue of every series (`meta.series`). |
| `schema_trading.sql` | Table definitions for our trading record. |

## How to run
From the repo root:
```
python Data/DataBase/setup_run_once/create_databases.py
```

## It can't wipe your data
If a `.duckdb` file already exists, the script **skips it and doesn't touch it**. If you copied the filled `market_data.duckdb` from OneDrive first, running this creates only the missing `trading.duckdb`.

To really start over, delete the `.duckdb` file yourself and run the script again.

## Changing the schema later
Editing the `.sql` files only changes databases created **after** the edit. Existing filled files don't change. Talk to Armaan before changing a table, so we can update everyone's file the same way.
