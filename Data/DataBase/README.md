# Data / DataBase

## What this folder is for
This is where all data is stored, using **DuckDB**, a fast single-file database that's good for analysing time series. It also holds the **one module that every other part of the system uses to read data**. That way there's a single place to enforce the "only what was known at the time" rule.

Think of it as the pantry shelves, plus a librarian who checks the date on every request.

## Two database files, for two different jobs
| File | Holds | Who writes to it |
|---|---|---|
| `market_data.duckdb` | Data from the outside world. **`raw`** schema: exactly as downloaded. **`clean`** schema: aligned to the trading calendar. **`features`** schema: model inputs. **`meta`** schema: the catalogue of every series. | [DataSources](../DataSources/) only |
| `trading.duckdb` | The record of what we did: runs, regime probabilities, allocations, positions, orders, fills, cash and daily NAV. | [ModelHome](../../ModelHome/), [Portfolio](../../Portfolio/), [Backtesting](../../Backtesting/) |

**Why two files?**
- DuckDB lets **one program open a file for writing, or many programs open it read-only, but not both at once.** With one file, a backtest writing results would lock everyone else out of the market data. Split, the backtest writes only to `trading.duckdb` while everyone reads `market_data.duckdb`.
- Market data can be rebuilt from scratch at any time. The trading record can't, because it's the history of what actually happened. Keeping them apart protects it.
- **Rule:** run `refresh.py` on its own. Everything else opens `market_data.duckdb` read-only.

## Tables
Every market-data table uses the same two dates: `obs_date` (the day the value is about) and `known_at` (the first day we could have known it: `obs_date` plus the series' `publish_lag_days` in business days). The full definitions are in [setup_run_once/schema_market.sql](setup_run_once/schema_market.sql) and [setup_run_once/schema_trading.sql](setup_run_once/schema_trading.sql).

ER diagrams: [diagrams/er_market_data.png](diagrams/er_market_data.png) and [diagrams/er_trading.png](diagrams/er_trading.png). Tables are stacked in one column, and each line runs from the exact column that points to the exact column it points to.

**`market_data.duckdb`**
| Table | What's in it |
|---|---|
| `meta.series` | **The catalogue.** One row per series: our name (`series_id`, lowercase, e.g. `ust_10y`, `spy`), source, the provider's code, units, `publish_lag_days`, who uses it. Written in the SQL file. `refresh.py` downloads whatever is listed here. |
| `meta.features` | Catalogue of model inputs. Written by `features.py` on each refresh, from its `FEATURES` list. |
| `meta.refresh_log` | One row per series per refresh run: rows written, ok/error, message. |
| `raw.series` | Single-value series (FRED, CBOE closes, Bloomberg). Long format: series_id, obs_date, value, known_at, fetched_at. |
| `raw.prices` | yfinance daily bars **as downloaded** (split-adjusted as of the download), plus adj_close. Only new dates are ever added. |
| `raw.corporate_actions` | Dividends and splits from yfinance. |
| `raw.option_iv` | Implied vol by tenor and moneyness (Bloomberg export shape). Empty for now. |
| `raw.option_quotes` | One row per option contract per day (OptionMetrics / IBKR shape). Empty for now. |
| `features.series` | Model inputs built by `features.py` from the clean data. `known_at` = latest `known_at` of the inputs. |
| `clean.*` | **Views, not copies.** `clean.series` drops missing values. `clean.prices` gives the prices **as actually traded** (splits undone) and a `total_return` that includes dividends. `clean.option_*` add a mid price. |

A revised value is added as a **new row** with a later `known_at`; nothing is ever overwritten. Prices are never revised, so only new dates are added for them.

**`trading.duckdb`**: every record table starts with `run_id`, so backtest runs never overwrite each other. Sleeve names: `vol`, `equity`, `spread`, `reserve`.
| Table | Holds |
|---|---|
| `runs` | run_id, mode (backtest / paper / live), git commit, settings used, dates, status |
| `instruments` | Contract master: symbol, type, expiry, strike, call/put, multiplier, IBKR id (not per run) |
| `regime_probs` | run_id, as_of, state, probability |
| `allocations` | run_id, as_of, sleeve, target_weight, capital |
| `target_positions` | What each sleeve wanted, and what risk approved |
| `risk_events` | Cuts, vetoes and circuit-breaker actions |
| `positions`, `orders`, `fills` | Holdings, orders and fills, tagged by sleeve (fills flag model-priced options) |
| `cash_ledger` | Every cash movement |
| `nav` | Daily NAV per sleeve and `total` |

## Files
| File | What it does |
|---|---|
| [setup_run_once/](setup_run_once/) | **ONE-TIME.** `create_databases.py` + the two schema files. Run once per computer. |
| `db.py` | Opens the two files (market data read-only by default) and holds the write helpers: `write_*` for DataSources, `append_rows` for trading records. |
| `access.py` | **The only way the rest of the system reads data.** |
| `*.duckdb` | The database files. **Never committed to Git.** |

## How to read data (`access.py`)
`as_of` is **required and keyword-only**. You only get values with `known_at <= as_of`, newest version per date. `end` defaults to `as_of` and can't go past it. Wide reads return a DataFrame with a date index and one column per id. Gaps stay NaN unless you pass `ffill_limit`.
```python
get_series(series_ids, start, end=None, *, as_of, ffill_limit=None)                  # ["ust_10y", "vix"]
get_prices(series_ids, start, end=None, *, as_of, field="close", ffill_limit=None)   # ["spy", "tqqq"]
#   field: open | high | low | close | volume  (as traded, use for levels and strikes)
#          total_return                        (use for returns; includes dividends)
#          dividend | adj_close                (adj_close: ratios only, its level uses later info)
get_features(feature_ids, start, end=None, *, as_of, ffill_limit=None)
get_dividends(series_ids, start, end=None, *, as_of)                                 # long format
get_option_iv(underlyings, start, end=None, *, as_of, tenor_days=None, moneyness_type=None, source=None)
get_option_chain(underlying, *, as_of, obs_date=None, expiry_from=None, expiry_to=None, source=None)
list_series(), list_features()
get_trading_records(table, run_id=None)       # reads trading.duckdb (for Reporting)
close()                                       # release the read connection
```
Write trading records with `db.connect_trading()` + `db.append_rows(con, "regime_probs", df)`.

## What it talks to
- **Gets from:** [DataSources](../DataSources/) (market data), and [ModelHome](../../ModelHome/), [Portfolio](../../Portfolio/) and [Backtesting](../../Backtesting/) (trading records).
- **Hands to:** every other folder, always through `access.py`.

## Complexity: Medium
The database itself is simple. Designing tables so look-ahead is impossible by construction takes careful thought.

## Watch-outs
1. **Nobody queries the tables directly.** Always go through `access.py`, so the as-of rule can't be skipped by accident.
2. **Keep raw data untouched.** If cleaning has a bug, you want to be able to re-run it on the original data.
3. **Never commit `.duckdb` files or Bloomberg exports.** The repo is public. Check that `*.duckdb` is active (not commented out) in `.gitignore`.
4. **Test the as-of rule.** Run the same read with `as_of` set to an earlier date and confirm that nothing after that date appears and nothing before it changes.

## Read first
White paper §4.1 (data hygiene) and §9 (data revisions).
