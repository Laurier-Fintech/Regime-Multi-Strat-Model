# ModelHome

## What this folder is for
This is the brain of the system. It decides **what we want to hold today**, and it has three parts:

1. **The regime engine (`RegimeHMM/`).** Every day it estimates how likely it is that the market is in each of four moods: calm-bull, calm-bear, stressed-bull and stressed-bear. It stands alone. It knows nothing about sleeves, brokers or loops, so it can be tested by itself.
2. **The allocator.** It turns the mood probabilities into a capital split across the sleeves and the defensive reserve.
3. **The engine (main loop).** This is the clock that runs the whole system one day at a time, calling every other part in the right order. The **same loop** runs a 20-year backtest in minutes and runs live trading one real day at a time. Only the clock and the broker change.

Think of it as the head chef and the kitchen timer together. The chef decides how much of each dish to make tonight. The timer makes sure every station does its step in the right order.

**What this folder never does:** fill orders. Fills come from a broker that is plugged in from outside: the simulated broker in [Backtesting](../Backtesting/), or the live broker in [Execution](../Execution/). Swapping that plug is the only difference between a backtest and live trading.

## Files that will live here (planned)

### Regime engine: `RegimeHMM/`
The regime is **two small HMMs**, combined:

| Model | Question it answers | Features it reads (from `features.series`) |
|---|---|---|
| **Stress** (2 states) | Calm or stressed? | `log_vix`, `credit_spread`, `credit_spread_chg_20d` (+ `vix_term` in v2, see To do later) |
| **Direction** (2 states) | Bull or bear? | `trend_spy`, `curve_slope` |

The four moods are the combinations: P(calm-bull) = P(calm) × P(bull), and so on. Treating the two models as independent is a simplification. It keeps each model small and stable, which matters with so few crises to learn from.

| File | What it does | Complexity |
|---|---|---|
| `regime_hmm.py` | The **maths only**: no dates, no database. `fit()` learns what each state looks like and how often the market switches (Baum-Welch). `filter_step()` updates today's state probabilities from yesterday's plus today's data (the forward algorithm). Used by both models. | High |
| `state_labels.py` | Each refit numbers the states in a random order. This file names them: in the stress model, the state with the higher average VIX is `stressed`; in the direction model, the state with the higher average trend is `bull`. | Low–Medium |
| `regime_model.py` | `RegimeModel.update(as_of)`: the **only** file here that reads the database. It loads the features known as of that day, decides whether it's a refit day (refit on all data up to that day only), runs one filter step on each model, and returns the four mood probabilities. `RegimeModel.run(start, end)` calls `update` day by day for research charts. | Medium |

**No look-ahead:** the regime refits on a schedule (e.g. monthly) using only data known up to that day, and only ever outputs **filtered** probabilities. Smoothed probabilities use future data and are only used inside fitting.

### Allocator
| File | What it does | Complexity |
|---|---|---|
| `target_mixes.py` | For each of the four moods, the ideal split of capital across the sleeves and the reserve. Starts as a hand-set table in [Config](../Config/). Later it's learned from how each sleeve behaved in past moods, with guardrails (weight caps, a pull toward equal weights) because there are only a few historical crises to learn from. | Medium–High |
| `allocator.py` | Blends the mixes by probability (55% calm-bull + 45% stressed-bear gives 55% of that mix plus 45% of the other) and smooths changes so we don't trade too much. Output: a target weight per sleeve. | Medium |

### Engine (main loop)
| File | What it does | Complexity |
|---|---|---|
| `clock.py` | Supplies "today". In a backtest it steps through historical trading days as fast as possible. Live, it waits for the real market close (or a set time). | Low |
| `sleeve_dispatcher.py` | Hands each sleeve its capital budget and today's mood probabilities, and collects the positions each sleeve wants to hold. | Low |
| `engine.py` | The daily loop. See below. It has a **sleeves on/off** switch in [Config](../Config/). | Medium |

## The daily loop (the heart of the whole system)
```
clock gives "today"
  → Regime: RegimeModel.update(today) → 4 mood probabilities     (ModelHome/RegimeHMM)
  → Allocate: weight per sleeve + reserve                        (ModelHome/allocator)
  → VIX circuit breaker: trim short-vol weight if VIX jumps      (RiskManagement)
  → Positions wanted:
       sleeves OFF → each sleeve's weight goes into its stand-in ETF (the regime-only test)
       sleeves ON  → each sleeve turns its budget into option positions  (Sleeves)
  → Risk: cut or veto anything over the limits                   (RiskManagement, reads Portfolio)
  → Portfolio: wanted − currently held = orders                  (Portfolio)
  → Broker plug: simulated (Backtesting) or real (Execution → LiveIBKRConnection)
  → Fills come back → Portfolio updates positions, cash and P&L
  → Save the day's record                                        (trading.duckdb)
repeat
```
Because backtest and live share this loop, a strategy that works in the backtest is running the **exact same code** live.

**Sleeves off** is the first test: it checks the regime and allocator on plain ETFs before any options are involved. Which ETF stands in for each sleeve is set in [Config](../Config/).

## What it talks to
- **Gets from:** [Data/DataBase](../Data/DataBase/) (features and prices, through the as-of reader `access.py`), [Config](../Config/) (features per model, refit schedule, mood mixes, smoothing, sleeves on/off), and [Portfolio](../Portfolio/) (current holdings and NAV).
- **Hands to:** [Sleeves](../Sleeves/) (budgets + probabilities), [RiskManagement](../RiskManagement/), [Portfolio](../Portfolio/), and whichever broker is plugged in. It saves the daily mood probabilities (`regime_probs`) and allocations (`allocations`) to `trading.duckdb` for [Reporting](../Reporting/).

## Complexity: High
The HMM maths is manageable. The hard parts are avoiding look-ahead, keeping state names consistent across refits, and not over-fitting to a handful of crises.

## Watch-outs
1. **Few crises to learn from.** That's why there are two 2-state models rather than one bigger one. Always judge the regime on data it wasn't fitted on.
2. **The model is slow by design.** It takes days to recognise a new mood. Fast protection comes from [RiskManagement](../RiskManagement/) (the VIX circuit breaker), not from here.
3. **Never fit on the full history and then backtest on it.** `RegimeModel` only ever fits on data known up to the day it's asked about.
4. **Feature history.** `vix_term` starts in Sept 2009 (CBOE VIX3M history), so the stress model can't see 2008 until a longer VIX3M history is loaded.

## To do later
- **Add `vix_term` back to the stress model (v2).** It was left out of v1 because it only starts 2009-09-18 and would cut 2008 out of the stress model's history. Steps: export `VIX3M Index` PX_LAST history from Bloomberg, load it into the database, rebuild `vix_term`, then add it to `STRESS_FEATURES` in `RegimeHMM/regime_model.py` (there's a TODO there).

## Read first
White paper §3 (architecture) and §4 (regime engine). Kritzman, Page & Turkington (2012), "Regime Shifts", is the closest published version of this idea; read it first. Then Ang & Timmermann (2011) for the limits of regime models.
