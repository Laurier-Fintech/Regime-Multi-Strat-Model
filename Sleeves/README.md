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

## Shared files
| File | What it does | Complexity |
|---|---|---|
| `base_sleeve.py` | The common template all sleeves follow (the input/output rule above). | Low |
| `regime_inputs.py` | Validates the four model states and derives calm/stressed and bull/bear probabilities. | Low |

## Regime input contract

`SleeveContext` now requires exactly the four labels returned by
`RegimeModel.update`: `calm-bull`, `calm-bear`, `stressed-bull`, `stressed-bear`.
All four must be present, even when a state's probability is zero. Values must
be finite real numbers in [0, 1]; booleans are rejected. Total probability must
be within 1e-8 of one. Totals inside that tolerance are normalized to remove
rounding error; other totals raise an error.

Both sleeves use the immutable `context.market_regime` view:

| Property | Calculation |
|---|---|
| `calm` | `calm-bull + calm-bear` |
| `stressed` | `stressed-bull + stressed-bear` |
| `bull` | `calm-bull + stressed-bull` |
| `bear` | `calm-bear + stressed-bear` |

For example, joint probabilities of 0.10, 0.20, 0.30 and 0.40 in the order above
give calm = 0.30, stressed = 0.70, bull = 0.40 and bear = 0.60. Stress and
direction describe different dimensions; do not add all four marginals together.
The original joint distribution remains available in the read-only
`context.regime_probabilities` mapping. No strategy thresholds are applied here.

The future engine/dispatcher should pass `moods.to_dict()` from the model's
pandas Series when constructing a context. It must supply a timezone-aware
decision timestamp that matches the daily data cutoff. If the model returns
`None` during warm-up, skip strategy dispatch for that date under an explicit
engine policy; do not substitute zero probabilities or an empty target list.
This boundary validates values, not their historical provenance or freshness.

This replaces the earlier allowance for arbitrary regime labels. Callers using
`{"calm": ..., "stress": ...}` must now supply the four joint states. The engine
is still a stub. Both sleeve target pipelines are implemented with explicit
adapter inputs; engine/Portfolio/execution wiring and historical validation
remain. See the [target integration guide](../Docs/SLEEVE_TARGET_INTEGRATION.md).

Run the focused checks from the repository root (standard library only):

```powershell
python -B -m unittest discover -s tests -p "test_regime_inputs.py" -v
```

Checks cover marginal calculations, reordered labels, zero/one probabilities,
invalid and unavailable inputs, rounding tolerance, immutable snapshots,
configuration migration, the directional equity gate and zero-budget vol behavior.

## What it talks to
- **Gets from:** [ModelHome](../ModelHome/) (budget + probabilities), [Data/DataBase](../Data/DataBase/) (prices, volatility, option data), and [Common](../Common/) (option pricing, Greeks, calendar).
- **Hands to:** [RiskManagement](../RiskManagement/) (wanted positions, for checking).

## Read first
White paper §5 (strategy sleeves), §5.4 (sleeve comparison table) and §8 (diversification profile).
