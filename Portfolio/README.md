# Portfolio

## What this folder is for
This is the **book of record**: the single source of truth for what we own, how much cash we have, and how much money we've made or lost. It also turns *what we want to hold* into *orders to place*.

The key design point is that it **works exactly the same in a backtest and live**. Each day it gets the approved positions from [RiskManagement](../RiskManagement/), compares them with what it currently holds, and produces the orders needed to close the gap. Those orders go to a broker. In a backtest that's the simulated broker in [Backtesting](../Backtesting/). Live, it's [Execution](../Execution/) → IBKR. Fills (confirmations of what actually traded) come back here and update the books. Portfolio never knows or cares which broker it's talking to.

Think of it as the accountant. It doesn't decide what to buy. It knows exactly what's in the account, works out what needs to change, and records every transaction.

## Files that will live here (planned)
| File | What it does | Complexity |
|---|---|---|
| `positions.py` | The current holdings: each stock, ETF, future and option contract, its quantity, cost, and **which sleeve owns it**. | Medium |
| `ledger.py` | Cash and every transaction (trades, commissions, interest on T-bills, dividends). | Medium |
| `valuation.py` | Prices every holding each day to get **NAV** (total portfolio value) and P&L, split by sleeve. Options without a live price are valued with the pricing tools in [Common](../Common/). | Medium–High |
| `greeks.py` | Adds up delta, vega and so on across all holdings, for [RiskManagement](../RiskManagement/). | Medium |
| `lifecycle.py` | Handles events that change holdings without a trade: options **expiring**, **assignment** (a short put turns into shares; [EquitySleeve](../Sleeves/EquitySleeve/) needs to know this for the wheel), futures **rolls**, and stock splits. | High |
| `rebalancer.py` | Wanted positions minus current positions gives the orders. It skips tiny trades that aren't worth the cost. | Medium |
| `broker_interface.py` | The one common "plug" that both the simulated broker and the live IBKR broker fit into: *send orders, get fills back*. Swapping this plug is how backtest becomes live. | Low–Medium |

## What it talks to
- **Gets from:** [RiskManagement](../RiskManagement/) (approved positions), the broker ([Backtesting](../Backtesting/) or [Execution](../Execution/), as fills), [Data/DataBase](../Data/DataBase/) (prices for valuation), and [Common](../Common/) (option pricing, contract details such as multipliers).
- **Hands to:** the broker (orders), [RiskManagement](../RiskManagement/) and [Sleeves](../Sleeves/) (current holdings), [ModelHome](../ModelHome/) (current NAV for sizing), and the database (`trading.duckdb`), which [Reporting](../Reporting/) reads.

## Complexity: Medium–High
Bookkeeping sounds easy. Options make it hard: contract multipliers, expiries, assignment and valuing positions that didn't trade today. Bugs here quietly corrupt every performance number.

## Watch-outs
1. **Every position is tagged with its sleeve**, or you can't tell which strategy made or lost money.
2. **Live, check the books against IBKR every day.** If our record and the broker's disagree, the broker is right and we need to find out why.
3. **One code path.** Never write a separate "backtest portfolio" and "live portfolio". That's how backtests and live results quietly drift apart.

## Read first
White paper §3 (architecture), §5.2 (assignment handling in the wheel) and §7 (aggregate exposure caps).
