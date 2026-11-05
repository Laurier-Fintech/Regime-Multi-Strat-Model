# Sleeves / SpreadSleeve (Sleeve C: Cross-asset spread)

## What this folder is for
This sleeve bets on **relationships between markets**. Some assets in different markets are linked by real economics, for example **crude oil and the Canadian dollar** (Canada exports a lot of oil), or **interest-rate differences and FX**. They tend to move together in a certain ratio. What's left over after applying that ratio is the **spread**. When the spread stretches unusually wide, the sleeve bets it will snap back.

The ratio isn't fixed. A **Kalman filter** (a method for tracking something you can't see directly, updated with each new data point) re-estimates it every day, so the spread is always measured against *today's* relationship rather than an old one.

The sleeve **switches off in stressed moods**, because relationships between markets tend to break down in a crisis.

Think of it as two dogs on a leash. They wander apart and come back together. You bet on them coming back when the leash is stretched, unless there's a thunderstorm and they bolt.

## Files that will live here (planned)
| File | What it does | Complexity |
|---|---|---|
| `pair_screen.py` | Scans many possible pairs, then keeps only those that (i) have a believable economic reason to be linked **and** (ii) still work on data the screen never saw. This avoids pairs that only look good by chance. | High |
| `kalman_hedge.py` | The Kalman filter that updates the hedge ratio every day. | High |
| `spread_signal.py` | Measures how stretched the spread is compared with normal (a "z-score") and sets the rules for entering and exiting. | Medium |
| `spread_sleeve.py` | Ties it together, turns itself off in stress, and returns the wanted positions, following the [rule all sleeves share](../README.md). | Medium |

**Instruments:** futures, FX and ETFs.

## What it talks to
- **Gets from:** [ModelHome](../../ModelHome/) (budget + probabilities), [Data/DataBase](../../Data/DataBase/) (prices across markets), and [Common](../../Common/) (calendar, contract details such as futures sizes and roll dates).
- **Hands to:** [RiskManagement](../../RiskManagement/) (wanted positions).

## Complexity: High
The Kalman filter and the statistics behind pair testing (**cointegration**, a test that two series move together over the long run) are the most mathematical parts of the project.

## Watch-outs
1. **Pairs found by scanning often look good only by luck.** Insist on an economic reason and out-of-sample testing.
2. **Relationships break**, sometimes permanently. Use stop-losses or time limits as well as the stress switch.
3. **Costs and crowding.** Well-known pairs may have little edge left after trading costs.

## Read first
White paper §5.3, §5.4 and §9 (costs and crowding).
