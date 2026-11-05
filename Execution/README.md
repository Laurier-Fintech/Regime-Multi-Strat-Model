# Execution

## What this folder is for
**Live trading only.** This folder takes the orders [Portfolio](../Portfolio/) wants placed and works out *how* to place them well at IBKR: what order type to use, how to send multi-leg option trades together, what to do if an order doesn't fill, and how to report fills back.

It handles the trading logic. The actual connection to IBKR is in [LiveIBKRConnection](../LiveIBKRConnection/), which this folder uses.

Think of it as the trader on the desk. The portfolio manager says "buy 10 of these". The trader decides how to buy them without overpaying.

## Files that will live here (planned)
| File | What it does | Complexity |
|---|---|---|
| `order_builder.py` | Turns an order into a real IBKR order: the correct contract, a quantity rounded to whole contracts (using multipliers from [Common](../Common/)), and an order type (usually a limit order around the mid-price for options). | Medium |
| `combo_orders.py` | Sends multi-leg option trades (put spreads, straddles) as **one combined order**, so we never end up with only half a spread filled. | Medium |
| `order_manager.py` | Tracks open orders, moves limit prices if they don't fill, cancels anything stale, and handles partial fills. | Medium |
| `live_broker.py` | The live version of the broker "plug" defined in [Portfolio](../Portfolio/): takes orders, places them through IBKR, and returns fills in the same format the simulated broker uses. | Medium |
| `reconcile.py` | Each day, compares Portfolio's record with IBKR's actual positions and cash, and flags any difference. | Medium |

## What it talks to
- **Gets from:** [Portfolio](../Portfolio/) (orders) and [Common](../Common/) (contract details).
- **Hands to:** [LiveIBKRConnection](../LiveIBKRConnection/) (orders to send) and [Portfolio](../Portfolio/) (fills).

## Complexity: Medium
The main challenge is handling real-world messiness: partial fills, rejections, disconnections and market hours.

## Watch-outs
1. **Start on IBKR's paper-trading account.** Don't touch real money until weeks of paper trading match the backtest.
2. **Never send option legs one at a time** when they belong to a spread.
3. **Have a kill switch**: one command that cancels all open orders.

## Read first
White paper §3 (architecture) and §1 (daily-to-weekly decisions on liquid, IBKR-tradable instruments).
