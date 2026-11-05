# Reporting

## What this folder is for
This folder turns the stored results into charts, tables and summaries people can read: how the portfolio did, **which sleeve made or lost the money**, how it behaved in each mood, and how close we came to risk limits. The same reports work for a backtest and for live trading, because both write results to the database in the same format.

Think of it as the scoreboard and the post-game analysis.

## Files that will live here (planned)
| File | What it does | Complexity |
|---|---|---|
| `performance.py` | Standard measures: total return, volatility, **Sharpe ratio** (return per unit of risk), max drawdown (the worst peak-to-trough fall), and win rate. | Low |
| `attribution.py` | Splits P&L **by sleeve** and **by mood** (regime), to answer "where did the returns come from?" | Medium |
| `regime_charts.py` | A timeline of mood probabilities against market prices, plus allocations over time. | Low |
| `risk_report.py` | Exposure over time (delta, vega), how often the VIX circuit breaker fired, and how close we came to each limit. | Low–Medium |
| `tearsheet.py` | A one-document summary of a backtest or live period, for PM meetings and bi-weekly milestones. | Low–Medium |
| `daily_live_report.py` | A short daily summary when live: positions, P&L, today's mood probabilities and any risk actions taken. | Low |

## What it talks to
- **Gets from:** [Data/DataBase](../Data/DataBase/) (`trading.duckdb`, which holds daily NAV, trades, positions, regime probabilities and risk actions, all written by [Portfolio](../Portfolio/), [Backtesting](../Backtesting/), [ModelHome](../ModelHome/) and [RiskManagement](../RiskManagement/)).
- **Hands to:** people: files, charts and slides.

## Complexity: Low–Medium
It's mostly straightforward analysis. Attribution by sleeve and mood takes a bit more care.

## Watch-outs
1. **Always label model-priced results.** If option prices were rebuilt from a model (see [Backtesting](../Backtesting/)), say so on the report.
2. **Show in-sample and out-of-sample separately.** Only out-of-sample results are evidence.
3. **This folder only reads results; it never changes them.**

## Read first
White paper §2 (multi-strategy payoff: combined Sharpe vs each sleeve) and §8 (diversification profile).
