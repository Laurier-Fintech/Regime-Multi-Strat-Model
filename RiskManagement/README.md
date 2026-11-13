# RiskManagement

## What this folder is for
This layer sits under everything and **can override any sleeve**. Each sleeve only looks after itself. This layer looks at the **whole portfolio at once** and cuts risk when the combined picture is too dangerous.

It exists because the regime engine is **slow by design**: it takes days to recognise a new mood. In calm moods, Sleeves A and B can both be selling volatility at the same time, so a sudden shock would hit both. This layer reacts **the same day**.

Think of it as the circuit breaker in your house. The appliances (sleeves) do their own thing, and the breaker cuts power to everything if the total load gets dangerous.

## The controls
| Control | What it does | Speed |
|---|---|---|
| Aggregate exposure caps | Adds up **net delta** (direction exposure) and **net vega** (exposure to volatility changes) across all sleeves, and caps the total short-volatility exposure. | Continuous |
| VIX circuit breaker | A sharp jump in the VIX immediately cuts short-volatility positions, **without waiting for the regime model**. | Same day |
| Regime de-risking | As stress probability rises, capital shifts from sleeves into the reserve. (The allocation itself is set in [ModelHome](../ModelHome/); this layer makes sure it actually happens.) | Days |
| Permanent tail hedge check | Confirms the reserve's OTM index puts are always in place. | Always on |

## Files that will live here (planned)
| File | What it does | Complexity |
|---|---|---|
| `exposure.py` | Adds up delta and vega across all sleeves, using current holdings from [Portfolio](../Portfolio/) plus the new wanted positions. | Medium |
| `limits.py` | Checks the totals against limits from [Config](../Config/) and **scales down** the wanted positions that would break them. | Medium |
| `circuit_breaker.py` | Watches the VIX and, on a sharp jump, moves weight out of the short-vol sleeves into the reserve immediately. It also decides when to rebuild gradually afterwards. It acts on the allocator's weights (the engine calls it right after the allocator), so it works with the sleeves on or off. | Medium |
| `risk_manager.py` | Runs all checks in order, returns the approved positions, and logs every cut and the reason. | Low–Medium |

## What it talks to
- **Gets from:** [Sleeves](../Sleeves/) (wanted positions), [Portfolio](../Portfolio/) (what we already hold, and the current Greeks), [Data/DataBase](../Data/DataBase/) (VIX), [Common](../Common/) (Greeks), and [Config](../Config/) (limits).
- **Hands to:** [Portfolio](../Portfolio/) (approved positions, which Portfolio turns into orders).

## Complexity: Medium
The rules are simple. Getting the Greeks right across many option positions, and choosing sensible thresholds without over-fitting, takes care.

## Watch-outs
1. **Risk must use what we actually hold**, not just what sleeves want today. That's why it reads from [Portfolio](../Portfolio/).
2. **Every cut gets logged.** Later you'll want to know how often the breaker fired and whether it helped.
3. **Don't tune thresholds to the 2008, 2020 and 2022 crises specifically.** That's over-fitting with extra steps.

## Read first
White paper §7 (risk management, with Figure 4) and §8 (diversification profile).
