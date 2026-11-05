# Data

## What this folder is for
This is where every number the system uses comes from. Raw data is downloaded from outside sources, cleaned, turned into useful measures ("features"), and stored in a database. **No other part of the system goes to the internet for data.** Everything else reads from the database.

Think of it as the kitchen's pantry. Groceries come in from the suppliers (`DataSources`) and get washed and labelled. Then they're put on the shelves (`DataBase`). The cooks (the rest of the system) only ever take from the shelves.

## Sub-folders
| Folder | What it does |
|---|---|
| [DataSources/](DataSources/) | Connects to yfinance, FRED, Bloomberg exports and IBKR. Downloads, cleans and builds features. |
| [DataBase/](DataBase/) | The DuckDB database(s) that hold raw and processed data, plus the one module everyone uses to read from them. |

## How data flows
```
Outside sources ──► DataSources (download → clean → build features) ──► DataBase ──► everything else
```

## What it talks to
- **Gets from:** the outside world (yfinance, FRED/ALFRED, Bloomberg files, IBKR).
- **Hands to:** [ModelHome](../ModelHome/) (regime inputs), [Sleeves](../Sleeves/) (prices, volatility, option data), [RiskManagement](../RiskManagement/) (VIX for the circuit breaker), [Backtesting](../Backtesting/) and [Reporting](../Reporting/).

## The one rule that matters most
**The system may only see data that was actually known on the day it is "standing on".** If a backtest on 15 March 2020 uses a number that was first published in April 2020, the results are fake. This is called *look-ahead bias*. Every table stores the date a value became known, and every read asks "what did we know as of date X?"

## Read first
White paper §4.1 (inputs and data hygiene) and §9 (data revisions, options data availability).
