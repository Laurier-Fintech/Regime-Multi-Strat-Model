# Sleeves / Reserve (Defensive reserve)

## What this folder is for
The defensive reserve is **deliberately not a strategy**. It looks for no edge and makes no predictions. It's a safe place the regime engine moves capital into as stress rises. Keeping it plain is the point: in a real crisis, markets start moving together, option prices get expensive, and complex strategies tend to fail at the same time.

It lives in the `Sleeves` folder only so the engine can hand it a budget the same way it does for the other sleeves.

Think of it as the emergency fund and the fire extinguisher. Boring, always there, and it earns its keep in a crisis.

## What it holds
- **Short-term Treasury bills**: near-cash that earns interest.
- **Gold**: often holds up when both stocks and bonds fall.
- **Cash.**
- **A small, permanent tail hedge**: out-of-the-money index puts that pay off in a crash while the sleeves are losing, buying time for the slower regime engine to react.

**Why not just bonds?** Bonds don't always protect against stock losses. In **2022 stocks and bonds fell together**, which is why gold and cash are included alongside T-bills.

## Files that will live here (planned)
| File | What it does | Complexity |
|---|---|---|
| `reserve.py` | Splits the reserve's budget across T-bills, gold and cash using fixed rules from [Config](../../Config/). | Low |
| `tail_hedge.py` | Keeps the permanent OTM put hedge in place and rolls it before expiry. | Low–Medium |

## What it talks to
- **Gets from:** [ModelHome](../../ModelHome/) (how much capital the reserve gets), [Data/DataBase](../../Data/DataBase/) (prices), and [Common](../../Common/) (option pricing and expiry calendar for the tail hedge).
- **Hands to:** [RiskManagement](../../RiskManagement/) (wanted positions). RiskManagement also checks the tail hedge is always in place.

## Complexity: Low
Simple on purpose. The only moving part is rolling the tail-hedge puts.

## Watch-outs
1. **Resist making it clever.** Once it starts trying to earn returns, it stops being a reliable safe place.
2. **The tail hedge costs money every year** when nothing goes wrong. That's expected. Size it so the cost is acceptable.

## Read first
White paper §6 (defensive reserve) and §7 (permanent tail hedge).
