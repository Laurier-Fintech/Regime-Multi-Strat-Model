# ModelHome

## What this folder is for
This is the brain of the system, and it has two jobs:

1. **The regime engine.** Every day it estimates how likely it is that the market is in each "mood" (for example calm, stressed or inflationary). It then decides how much capital each sleeve and the defensive reserve should get.
2. **The engine (main loop).** This is the clock that runs the whole system one day at a time, calling every other part in the right order. The **same loop** runs a 20-year backtest in minutes and runs live trading one real day at a time. Only the clock and the broker change.

Think of it as the head chef and the kitchen timer together. The chef decides how much of each dish to make tonight. The timer makes sure every station does its step in the right order.

## Files that will live here (planned)

### Regime engine
| File | What it does | Complexity |
|---|---|---|
| `regime_hmm.py` | The **hidden Markov model (HMM)**. It assumes the market is always in one of a few hidden moods, learns what each mood "looks like" in the data (yield-curve slope, credit spreads, VIX, trend), and outputs the probability of each mood today, e.g. 70% stressed / 30% calm. | High |
| `walk_forward.py` | Re-fits the HMM over time using **only data available up to that day**, then predicts forward. This stops the model from "knowing the future" in a backtest. | High |
| `state_labels.py` | Each time the HMM is re-fitted, it may number the moods differently ("state 1" was calm, now it's stressed). This file matches the new states to the old ones so "stressed" always means stressed. | Medium |
| `target_mixes.py` | For each mood, the ideal split of capital across Sleeves A, B, C and the reserve. It's learned from how each sleeve behaved in past moods, with guardrails (weight caps, a pull toward equal weights) because there are only a few historical crises to learn from. | High |
| `allocator.py` | Blends the mixes by probability (70% stressed + 30% calm gives 70% of the stressed mix plus 30% of the calm mix) and smooths changes so we don't trade too much. | Medium |
| `sleeve_dispatcher.py` | Hands each sleeve its capital budget and today's mood probabilities, and collects the positions each sleeve wants to hold. | Low |

### Engine (main loop)
| File | What it does | Complexity |
|---|---|---|
| `clock.py` | Supplies "today". In a backtest it steps through historical trading days as fast as possible. Live, it waits for the real market close (or a set time). | Low |
| `engine.py` | The daily loop. See below. | Medium |

## The daily loop (the heart of the whole system)
```
clock gives "today"
  → Data: read everything known as of today            (Data/DataBase)
  → Regime: today's mood probabilities                 (ModelHome)
  → Allocate: capital per sleeve + reserve             (ModelHome)
  → Sleeves: each returns the positions it WANTS       (Sleeves)
  → Risk: cut or veto anything over the limits         (RiskManagement, reads Portfolio)
  → Portfolio: wanted − currently held = orders        (Portfolio)
  → Broker: simulated (Backtesting) or real (Execution → LiveIBKRConnection)
  → Fills come back → Portfolio updates positions, cash and P&L
  → Save the day's record                              (Data/DataBase, trading.duckdb)
repeat
```
Because backtest and live share this loop, a strategy that works in the backtest is running the **exact same code** live.

## What it talks to
- **Gets from:** [Data/DataBase](../Data/DataBase/) (regime inputs, through the as-of reader), [Config](../Config/) (number of moods, guardrails, smoothing), and [Portfolio](../Portfolio/) (current holdings).
- **Hands to:** [Sleeves](../Sleeves/) (budgets + probabilities), [RiskManagement](../RiskManagement/), [Portfolio](../Portfolio/), and the broker ([Backtesting](../Backtesting/) or [Execution](../Execution/)). It saves the daily probabilities and allocations to the database for [Reporting](../Reporting/).

## Complexity: High
The HMM maths is manageable. The hard parts are avoiding look-ahead, keeping mood labels consistent, and not over-fitting to a handful of crises.

## Watch-outs
1. **Few crises to learn from.** Keep the number of moods small (2–4) and always judge the model on data it wasn't fitted on.
2. **The model is slow by design.** It takes days to recognise a new mood. Fast protection comes from [RiskManagement](../RiskManagement/) (the VIX circuit breaker), not from here.
3. **Never fit on the full history and then backtest on it.** Use `walk_forward.py`.

## Read first
White paper §3 (architecture) and §4 (regime engine). Kritzman, Page & Turkington (2012), "Regime Shifts", is the closest published version of this idea; read it first. Then Ang & Timmermann (2011) for the limits of regime models.
