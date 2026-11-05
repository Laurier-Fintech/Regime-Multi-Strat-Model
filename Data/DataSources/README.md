# Data / DataSources

## What this folder is for
This is the code that fetches data from outside providers, cleans it, and builds the measures the models need. It then writes everything into the database in [../DataBase](../DataBase/).

Think of it as the receiving dock. Deliveries arrive here, get checked, unpacked and labelled, and then get sent to the shelves.

## Files that will live here (planned)
| File | What it does | Complexity |
|---|---|---|
| `yfinance_source.py` | Downloads daily prices for ETFs, indices and futures proxies (SPY, TQQQ, GLD, USO, FX, ^VIX and so on). | Low |
| `fred_source.py` | Downloads macro and credit series from FRED: the 10y and 2y Treasury yields, high-yield credit spreads (HY OAS) and T-bill rates. It uses **ALFRED** (FRED's archive) to get the value *as it was first published*, not the revised value. | Medium |
| `bloomberg_import.py` | Loads files exported by hand from the Bloomberg terminal (for example option data and vol surfaces), since Bloomberg can't be queried directly from code here. | Medium |
| `ibkr_source.py` | Pulls live and recent prices and option chains from Interactive Brokers through [LiveIBKRConnection](../../LiveIBKRConnection/). IBKR has **no history for expired options**. | Medium |
| `cleaning.py` | Fixes the usual problems: missing days, holidays, stock splits, bad ticks, and series from different markets that close at different times. It lines everything up on one trading calendar (from [Common](../../Common/)). | Medium |
| `features.py` | Builds the inputs the models use: the yield-curve slope (10y minus 2y), credit-spread level and change, VIX level and VIX term structure (short-dated vs longer-dated VIX), trend measures across assets, and realised volatility at daily, weekly and monthly horizons (the inputs to the HAR volatility forecast in Sleeve A). | Medium |
| `refresh.py` | One command that runs everything above in order and records what was updated and when. Run daily when live. | Low |

## What it talks to
- **Gets from:** the internet (yfinance, FRED/ALFRED), Bloomberg export files, [LiveIBKRConnection](../../LiveIBKRConnection/), the trading calendar in [Common](../../Common/), and API keys and the list of tickers in [Config](../../Config/).
- **Hands to:** [../DataBase](../DataBase/) only. Nothing reads from this folder directly.

## Complexity: Medium
Each download on its own is easy. The hard part is getting the details right: timing, holidays, revisions, and keeping raw data separate from cleaned data.

## Watch-outs
1. **Revised data is a lie in a backtest.** Macro numbers get revised months later. Always store the first-published value and the date it was published.
2. **Time zones and closing times.** Oil, FX and US stocks don't all close at the same moment. Don't use a price that closed *after* the moment the decision was made.
3. **Options history is the big gap.** yfinance and IBKR can't give historical option prices, and Bloomberg has download limits. Plan where this comes from early. See white paper §9.

## Read first
White paper §4.1 (candidate inputs, data hygiene) and §9 (data revisions, options data availability).
