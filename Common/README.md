# Common

## What this folder is for
These are shared tools that **several folders need**, kept in one place so there's only ever one version of each. If the option pricing formula lived separately in three sleeves, they would eventually disagree, and nobody would notice until the numbers stopped adding up.

Think of it as the shared toolbox. Every station in the kitchen uses the same knives and the same scales.

## Files that will live here (planned)
| File | What it does | Complexity |
|---|---|---|
| `option_pricing.py` | Prices options: **Black-Scholes** for stock and ETF options, **Black-76** for options on futures (oil, gold, Treasuries). | Medium |
| `greeks.py` | Option sensitivities: **delta** (to the underlying's price), **vega** (to implied volatility), gamma and theta. | Medium |
| `implied_vol.py` | Works backwards from an option's market price to the volatility it implies. | Medium |
| `vol_surface.py` | Fills in implied volatility for strikes and expiries we don't have a quote for, by smoothing between the ones we do. Needed to value options and to rebuild historical prices. | High |
| `calendar.py` | Trading days, market holidays, option expiry dates and futures roll dates. Every folder uses the same calendar. | Low–Medium |
| `instruments.py` | The **contract master**: one list of every instrument we trade, with its symbol, type, **multiplier** (e.g. one US equity option = 100 shares), currency, exchange and IBKR ID. | Low–Medium |
| `logging_setup.py` | One consistent way to write logs, so a problem can be traced across folders. | Low |

## What it talks to
- **Gets from:** nothing in the system. It's pure tools. [LiveIBKRConnection](../LiveIBKRConnection/) fills in the IBKR IDs in the contract master.
- **Hands to:** almost everyone: [Sleeves](../Sleeves/), [RiskManagement](../RiskManagement/), [Portfolio](../Portfolio/), [Backtesting](../Backtesting/), [Execution](../Execution/) and [Data](../Data/).

## Complexity: Medium
The formulas are textbook. The vol surface, and making sure every edge case is handled (expiry day, deep in or out of the money), takes care.

## Watch-outs
1. **Test these hardest.** A small bug in Greeks or pricing quietly affects every sleeve and every risk check.
2. **Multipliers and currencies** are a classic source of "P&L is 100× too big" bugs.
3. **Don't put strategy logic here.** If it makes a decision, it belongs in a sleeve.

## Read first
White paper Appendix A (glossary: implied vs realised volatility, delta and vega, delta-hedging) and §5.4 (core maths per sleeve).
