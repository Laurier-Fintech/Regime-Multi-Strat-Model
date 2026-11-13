# Backtesting

## What this folder is for
A backtest replays history and asks: "If this system had been running since, say, 2007, what would have happened?" This folder makes that replay **honest**.

The backtester **doesn't** sit at the end of a pipeline. It **drives** the same daily loop that runs live (the engine in [ModelHome](../ModelHome/)), just with a clock that races through historical days and a **simulated broker** in place of IBKR. Everything else (regime, sleeves, risk, portfolio) is the exact same code that will trade live.

Think of it as a flight simulator. It's the same cockpit and the same controls as the real plane, but the world outside is a recording of the past.

**The split:** [ModelHome](../ModelHome/) decides *what we want to hold*. This folder answers *what the market would have done to our orders*. Nothing here is used live. To go live, unplug `sim_broker.py` and plug in `live_broker.py` from [Execution](../Execution/); the engine doesn't change.

The backtester works with the sleeves **off** (regime + allocator on plain ETFs, the first test) or **on** (the full options system). The switch lives in [Config](../Config/).

## Files that will live here (planned)
| File | What it does | Complexity |
|---|---|---|
| `sim_broker.py` | The simulated broker. It fits the same "plug" as the live broker (see [Portfolio](../Portfolio/)). It takes orders and returns fills with realistic **bid-ask spreads, slippage and commissions**. | High |
| `margin.py` | Checks we'd actually have had enough margin (collateral) to hold short options. It forces cuts if not, as a real broker would. | Medium |
| `assignment.py` | Simulates options expiring and short options being **assigned**, including early assignment, so the [EquitySleeve](../Sleeves/EquitySleeve/) wheel behaves realistically. | Medium–High |
| `option_history.py` | Rebuilds historical option prices where real ones aren't available, by **re-pricing options from a model** (using [Common](../Common/)) on historical implied volatility. Every such result must say clearly that it's model-priced. | High |
| `run_backtest.py` | Sets the start and end dates, sleeves on/off and other settings from [Config](../Config/), plugs `sim_broker.py` into the engine, runs it over history, and saves results to the database. | Low–Medium |

There's no separate walk-forward file. Refitting on past data only happens inside the regime itself (`ModelHome/RegimeHMM/regime_model.py`), so every backtest is walk-forward automatically.

## What it talks to
- **Gets from:** [ModelHome](../ModelHome/) (it runs the engine), [Portfolio](../Portfolio/) (orders to fill), [Data/DataBase](../Data/DataBase/) (historical prices, as-of only), [Common](../Common/) (option pricing, calendar), and [Config](../Config/) (run settings, cost assumptions).
- **Hands to:** [Portfolio](../Portfolio/) (fills) and the database (`trading.duckdb`: daily NAV, trades, regime probabilities), which [Reporting](../Reporting/) reads.

## Complexity: High
The loop itself is simple. Realistic fills, costs, margin, assignment and **historical option prices** are where backtests usually go wrong.

## Watch-outs
1. **Look-ahead bias is the number one killer.** Every data read goes through the as-of reader in [Data/DataBase](../Data/DataBase/), and every model is fitted only on past data.
2. **Costs from day one.** Selling options looks wonderful before costs and much less so after. Never show a result without costs.
3. **Few crises in the data.** A great backtest may just be a lucky fit to 2008, 2020 and 2022. Out-of-sample results are the ones that count.

## Read first
White paper §4.2 (guardrails against over-fitting) and §9 (key risks: few regime episodes, data revisions, options data, costs).
