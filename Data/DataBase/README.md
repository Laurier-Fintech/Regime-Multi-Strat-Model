# Data / DataBase

## What this folder is for
This is where all data is stored, using **DuckDB**, a fast single-file database that's good for analysing time series. It also holds the **one module that every other part of the system uses to read data**. That way there's a single place to enforce the "only what was known at the time" rule.

Think of it as the pantry shelves, plus a librarian who checks the date on every request.

## Proposed layout (schema not final)
Two database files, for two different jobs:

| File | Holds | Who writes to it |
|---|---|---|
| `market_data.duckdb` | **`raw`** schema: data exactly as downloaded. **`features`** schema: cleaned series and model inputs. | [DataSources](../DataSources/) only |
| `trading.duckdb` | The record of what we did: positions, orders, fills, cash, daily NAV, regime probabilities used each day, and backtest run results. | [Portfolio](../../Portfolio/), [Backtesting](../../Backtesting/), [ModelHome](../../ModelHome/) |

**Why two files?**
- DuckDB lets only **one program write at a time**. If the daily data refresh and the live trader shared one file, one could block the other.
- Market data can be rebuilt from scratch at any time. The trading record can't, because it's the history of what actually happened. Keeping them apart protects it.

## Files that will live here (planned)
| File | What it does | Complexity |
|---|---|---|
| `schema.sql` | Table definitions. Every table includes the date the value refers to **and** the date it became known (`known_at`). | Low |
| `db.py` | Opens connections to the two files and creates tables if they're missing. | Low |
| `access.py` | **The only way the rest of the system reads data.** Every function takes an `as_of` date and only returns rows with `known_at <= as_of`. | Medium |
| `*.duckdb` | The database files themselves. **Not committed to Git** (too large, and they can be rebuilt). | — |

## What it talks to
- **Gets from:** [DataSources](../DataSources/) (market data), and [Portfolio](../../Portfolio/) and [Backtesting](../../Backtesting/) (trading records).
- **Hands to:** every other folder, always through `access.py`.

## Complexity: Medium
The database itself is simple. Designing tables so look-ahead is impossible by construction takes careful thought.

## Watch-outs
1. **Nobody queries the tables directly.** Always go through `access.py`, so the as-of rule can't be skipped by accident.
2. **Keep raw data untouched.** If cleaning has a bug, you want to be able to re-run it on the original data.
3. **Never commit `.duckdb` files.** The repo is public.

## Read first
White paper §4.1 (data hygiene) and §9 (data revisions).
