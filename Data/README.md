# Data

## What this folder is for
This is where every number the system uses comes from. Raw data is downloaded from outside sources, cleaned, turned into useful measures ("features"), and stored in a database. **No other part of the system goes to the internet for data.** Everything else reads from the database.

Think of it as the kitchen's pantry. Groceries come in from the suppliers (`DataSources`) and get washed and labelled. Then they're put on the shelves (`DataBase`). The cooks (the rest of the system) only ever take from the shelves.

## Sub-folders
| Folder | What it does |
|---|---|
| [DataSources/](DataSources/) | Connects to FRED, CBOE, yfinance and Bloomberg exports (IBKR later). Downloads, cleans and builds features. |
| [DataBase/](DataBase/) | The two DuckDB files that hold market data and our trading record, plus `access.py`, the one module everyone uses to read from them. The one-time setup lives in [DataBase/setup_run_once/](DataBase/setup_run_once/). |

## How to use it (start here)
All commands run from the **repo root**.

**0. Install (once):** `python -m pip install -r requirements.txt` (Python 3.14; versions are pinned so everyone's database files are compatible).

**1. Create the empty databases (ONE-TIME):**
```
python Data/DataBase/setup_run_once/create_databases.py
```
Creates `market_data.duckdb` and `trading.duckdb` in `Data/DataBase/`. It never touches a file that already exists.

**2. Fill / update market data (Armaan, or anyone building their own copy):**
```
python Data/DataSources/refresh.py
```
Needs `FRED_API_KEY` in `Config/.env`. Safe to re-run at any time.

**3. Everyone else: just read.**
```python
from Data.DataBase.access import get_series, get_prices

rates = get_series(["ust_10y", "ust_2y"], start="2010-01-01", as_of="2020-03-13")
spy   = get_prices("spy", start="2010-01-01", as_of="2020-03-13", field="total_return")
```
`list_series()` shows every series name. Never open the `.duckdb` files directly.

**Getting the filled database (Fridays):** copy `market_data.duckdb` from the OneDrive folder into your local `Data/DataBase/`, replacing yours. **Never open it straight from OneDrive.** Close Python and notebooks first. Your `trading.duckdb` stays local; if you don't have one, run step 1.

## How data flows
```
Outside sources ──► DataSources (download → clean → build features) ──► DataBase ──► access.py ──► everything else
```

## What it talks to
- **Gets from:** the outside world (FRED, CBOE, yfinance, Bloomberg export files; IBKR once we go live).
- **Hands to:** [ModelHome](../ModelHome/) (regime inputs), [Sleeves](../Sleeves/) (prices, volatility, option data), [RiskManagement](../RiskManagement/) (VIX for the circuit breaker), [Backtesting](../Backtesting/) and [Reporting](../Reporting/). Always through `DataBase/access.py`.

## The one rule that matters most
**The system may only see data that was actually known on the day it is "standing on".** If a backtest on 15 March 2020 uses a number that was first published in April 2020, the results are fake. This is called *look-ahead bias*.

Every row stores two dates: the date the value is **about** (`obs_date`) and the date we could first have **known** it (`known_at`). Every read asks "what did we know as of date X?" For example:
- A closing price or a CBOE index close is known at that day's close.
- A FRED series is usually posted the next business day, so `known_at` is one business day later.

## Read first
White paper §4.1 (inputs and data hygiene) and §9 (data revisions, options data availability).
