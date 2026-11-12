# Data / DataSources

## What this folder is for
This is the code that fetches data from outside providers, cleans it, and builds the measures the models need. It then writes everything into the database in [../DataBase](../DataBase/). **This is the only folder allowed to write to `market_data.duckdb`.**

Think of it as the receiving dock. Deliveries arrive here, get checked, unpacked and labelled, and then get sent to the shelves.

## Entry point
```
python Data/DataSources/refresh.py                   # every source
python Data/DataSources/refresh.py --only fred cboe  # just some
```
Close anything that has `market_data.duckdb` open first. Re-running is always safe. What to download comes from `meta.series` (in [schema_market.sql](../DataBase/setup_run_once/schema_market.sql)), not from these files.

**SSL errors** ("certificate verify failed") come from antivirus or school networks re-signing HTTPS traffic. `refresh.py` handles this by using the operating system's certificate store (`truststore`; yfinance gets a bundle built from the Windows store).

## Files
Built: `fred_source.py`, `cboe_source.py`, `yfinance_source.py`, `bloomberg_import.py`, `features.py`, `refresh.py` (+ `_common.py`, shared helpers). Planned: `ibkr_source.py`.
| File | What it does | Complexity |
|---|---|---|
| `fred_source.py` | Downloads from FRED: 10y and 2y Treasury yields (`DGS10`, `DGS2`), the Baa corporate minus 10y spread (`BAA10Y`, our long-history credit measure), the 3-month T-bill (`DTB3`), WTI crude (`DCOILWTICO`) and USD/CAD (`DEXCAUS`). Needs a free FRED API key in `Config/.env`. | Low |
| `cboe_source.py` | Downloads CBOE's free daily index files: `VIX`, `VIX3M`, `VIX9D`, `VVIX`, `VXN` (Nasdaq-100 vol), `OVX` (oil vol), `GVZ` (gold vol), `SKEW`. | Low |
| `yfinance_source.py` | Downloads daily prices for ETFs and indices: SPY, QQQ, TQQQ, TLT, IEF, HYG, GLD, DBC, UUP, ^GSPC, ^NDX, ^MOVE. Stores **both** the raw close and the adjusted close. | Low |
| `bloomberg_import.py` | Loads CSVs exported by hand from the Prism lab terminal (exports are allowed): full-history HY OAS and option implied vols by moneyness and expiry. Bloomberg can't be queried from code here. Export files go in the git-ignored `bloomberg_exports/series/<series_id>.csv` (date, value) and `bloomberg_exports/option_iv/<underlying>.csv` (date, tenor_days, moneyness_type, moneyness, iv). Bloomberg's own wide BDH layout (date + one `<tenor>_IMPVOL_<m>%MNY_DF` column per field, in percent) is read directly from either folder. Current exports: IV grids for spx, ndx, tlt, gld, tqqq (30/60/90/180 days × 90–110% moneyness), `hy_oas` (LF98OAS, percent) and `spx_div_yield`. | Medium |
| `ibkr_source.py` | **Later, not this term's first milestone.** Live prices and option chains through [LiveIBKRConnection](../../LiveIBKRConnection/). IBKR has **no history for expired options**. | Medium |
| `cleaning.py` | Lines every series up on one trading calendar (from [Common](../../Common/)), handles holidays and missing days (forward-fill at most a few days, then flag), and flags stale or bad values. Never edits the raw tables. For now the `clean` views in the database handle missing values and splits, and `access.py` forward-fills at read time. | Medium |
| `features.py` | Builds the raw measures the models use: curve slope (10y − 2y), credit spread level and change, log VIX, VIX/VIX3M (term structure), cross-asset trend, and realised volatility over 1, 5 and 22 days (the inputs to the HAR forecast in Sleeve A). Runs as the last step of `refresh.py` (`--only features` rebuilds just these). 15 features: `curve_slope`, `credit_spread`, `credit_spread_chg_20d`, `log_vix`, `vix_term`, `trend_spy/tlt/gld/dbc` (12-month total return), `rv_spy_1d/5d/22d`, `rv_qqq_1d/5d/22d` (annualised). Each value's `known_at` is the latest `known_at` of its inputs. Add one by writing a function and one line in `FEATURES`. **No scaling or z-scoring here.** That is part of the model, fitted on past data only, so it lives in [ModelHome](../../ModelHome/). | Medium |
| `refresh.py` | **Entry point.** One command that runs every source and records what was updated and when in `meta.refresh_log`. Run daily when live. | Low |

## What it talks to
- **Gets from:** the internet (FRED, CBOE, yfinance), Bloomberg export files, [LiveIBKRConnection](../../LiveIBKRConnection/) (later), the trading calendar in [Common](../../Common/), and API keys and the list of tickers in [Config](../../Config/).
- **Hands to:** [../DataBase](../DataBase/) only. Nothing reads from this folder directly.

## Complexity: Medium
Each download on its own is easy. The hard part is getting the details right: timing, holidays, revisions, and keeping raw data separate from cleaned data.

## Watch-outs
1. **FRED's high-yield spread (HY OAS) only goes back 3 years now.** Since April 2026 the licence holder (ICE) limits FRED to the last 3 years. Bring in full-history HY OAS from Bloomberg as the main credit measure, and keep `BAA10Y` as a free cross-check and fallback.
2. **ALFRED is only needed for numbers that get revised** (CPI, payrolls, GDP). Yields, spreads, VIX and prices are never revised, so plain FRED is fine for everything above. Still store `known_at` for every row.
3. **Adjusted close quietly uses the future.** yfinance back-adjusts old prices for dividends paid later. Use adjusted close for **returns only**. Use the raw close for price levels and option strikes.
4. **Time zones and closing times.** Oil, FX and US stocks don't all close at the same moment. Don't use a price that closed *after* the moment the decision was made.
5. **yfinance is unofficial and rate-limited.** Download once into the raw tables and read from there. A backtest must never call the internet.
6. **Never commit Bloomberg exports.** Bloomberg's licence forbids redistribution and the repo is public. Keep them in a git-ignored folder.
7. **Options history is the big gap.** Free sources and IBKR can't give historical option prices, and Bloomberg has download limits. Bloomberg implied vols by moneyness are the main source. Pull the most important underlyings first, since terminal download limits apply. Where we have no Bloomberg history, options are repriced with Black-Scholes using the vol indices above (VIX for SPX, VXN as a rough stand-in for TQQQ). See white paper §9.

## Read first
White paper §4.1 (candidate inputs, data hygiene) and §9 (data revisions, options data availability).
