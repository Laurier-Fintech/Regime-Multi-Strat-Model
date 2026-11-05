# Sleeves

## What this folder is for
A "sleeve" is one self-contained strategy with its own slice of capital. Each sleeve bets on something different, so they don't all win or lose at the same time:

| Sleeve | Bets on | Folder |
|---|---|---|
| A: Volatility | **How big** market moves will be | [VolSleeve/](VolSleeve/) |
| B: Equity options | **Which direction** stocks go | [EquitySleeve/](EquitySleeve/) |
| C: Cross-asset spread | **Relationships** between markets | [SpreadSleeve/](SpreadSleeve/) |
| Defensive reserve | Nothing. It's a safe parking spot, **not a strategy** | [Reserve/](Reserve/) |

Think of each sleeve as a different station in the kitchen (grill, pastry, salad). The head chef ([ModelHome](../ModelHome/)) decides how much each station makes tonight. Each station decides *how* to make it.

## The rule every sleeve follows
Every sleeve works the same way, so the engine can treat them all alike:

> **Input:** today's date, its capital budget, and today's mood probabilities.
> **Output:** a list of **positions it wants to hold** (for example "short 3 SPY 30-day 4500 puts").

Sleeves **don't place orders** and **don't track what they already own**. That's [Portfolio](../Portfolio/)'s job. They also don't check limits; that's [RiskManagement](../RiskManagement/)'s job. Keeping sleeves this simple makes each one easy to build, test and present on its own.

## Planned shared file
| File | What it does | Complexity |
|---|---|---|
| `base_sleeve.py` | The common template all sleeves follow (the input/output rule above). | Low |

## What it talks to
- **Gets from:** [ModelHome](../ModelHome/) (budget + probabilities), [Data/DataBase](../Data/DataBase/) (prices, volatility, option data), and [Common](../Common/) (option pricing, Greeks, calendar).
- **Hands to:** [RiskManagement](../RiskManagement/) (wanted positions, for checking).

## Read first
White paper §5 (strategy sleeves), §5.4 (sleeve comparison table) and §8 (diversification profile).
