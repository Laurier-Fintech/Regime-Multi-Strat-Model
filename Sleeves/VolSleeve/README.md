# Sleeves / VolSleeve (Sleeve A: Volatility)

## What this folder is for
This sleeve bets on **how big market moves will be**, not which way they go.

An option's price contains the market's guess of future volatility (**implied volatility**). Historically that guess has usually been *higher* than the volatility that actually happened (**realised volatility**). The gap is called the **variance risk premium**, and it's why option sellers tend to earn money over time. This sleeve forecasts realised volatility itself and compares it with what options imply:
- Options look **expensive** (implied well above our forecast) → **sell** volatility.
- Options look **cheap**, or stress probability is rising → **buy** volatility.

Think of it as an insurance company. Most of the time it collects premiums because people overpay for insurance. It has to be very careful about the rare disaster.

## Files that will live here (planned)
| File | What it does | Complexity |
|---|---|---|
| `rv_forecast.py` | Forecasts realised volatility. The baseline is **HAR-RV**, a simple model that combines yesterday's, last week's and last month's volatility. **GARCH** is the alternative baseline, with a machine-learning version as an optional extra. | High |
| `signal.py` | Implied vol minus forecast vol, per market. Decides rich, cheap or neutral, adjusted by the mood probabilities. | Medium |
| `structures.py` | Picks the actual options to trade (e.g. short straddles or strangles when selling vol, long options when buying), and their strikes and expiries. | High |
| `delta_hedge.py` | Adds offsetting futures or ETF positions so the trade has no view on direction, only on volatility. **Delta** is how much an option's price moves when the underlying moves. | Medium |
| `vol_sleeve.py` | Ties it together and returns the wanted positions, following the [rule all sleeves share](../README.md). | Medium |

**Universe:** liquid options on equity indices, Treasuries, gold and oil.

## What it talks to
- **Gets from:** [ModelHome](../../ModelHome/) (budget + probabilities), [Data/DataBase](../../Data/DataBase/) (prices, realised vol inputs, implied vol and option chains), and [Common](../../Common/) (option pricing, Greeks, vol surface, expiry calendar).
- **Hands to:** [RiskManagement](../../RiskManagement/) (wanted positions).

## Complexity: High
It needs volatility forecasting, option pricing and Greeks, and hedging. It also depends on **historical option data, which is hard to get**.

## Watch-outs
1. **Short volatility makes small steady gains and occasionally loses a lot.** A sudden spike can wipe out months of gains. The VIX circuit breaker and the cap on total short-vol exposure in [RiskManagement](../../RiskManagement/) exist mainly because of this sleeve and Sleeve B.
2. **Transaction costs matter a lot.** Option bid-ask spreads are wide, so a backtest without realistic costs will look far too good.
3. **Delta-hedging isn't free.** Hedging too often costs money, and hedging too rarely leaves direction risk. Pick and test a rule.

## Read first
White paper §5.1 and §7 (risk management). Carr & Wu (2009), "Variance Risk Premiums", is the foundation for this sleeve.
