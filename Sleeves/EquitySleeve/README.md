# Sleeves / EquitySleeve (Sleeve B: Equity options)

## What this folder is for
This sleeve bets on **which direction stocks go**, using option trades rather than buying or shorting stocks outright. What it does depends on the market's mood:

- **Stressed:** buys **index put spreads**, which pay off if the market falls. These also partly protect the rest of the portfolio.
- **Calm:** sells **covered calls**, and sells **out-of-the-money puts** on high-volatility and leveraged ETFs such as **TQQQ** (a fund that moves about 3× the Nasdaq-100 each day). Their options pay rich premiums because they're so volatile.

**"The wheel":** if a put we sold gets **assigned** (we're forced to buy the shares), we hold the shares and sell calls against them until we hit an exit target or the shares get "called away" (bought from us). Whether we keep going or exit early depends on the mood: continue while calm, get out when stress probability is high.

Think of it as renting out umbrellas on sunny days and buying them yourself when clouds roll in.

## Files that will live here (planned)
| File | What it does | Complexity |
|---|---|---|
| `stress_put_spreads.py` | Picks the strikes, expiries and size for index put spreads in stressed moods. | Medium |
| `calm_premium.py` | Picks covered calls and the put strikes to sell on TQQQ-type ETFs in calm moods. | Medium |
| `wheel.py` | Tracks where each wheel position is (put sold → assigned → holding shares + selling calls → exited) and applies the mood-based exit rules. | High |
| `equity_sleeve.py` | Ties it together and returns the wanted positions, following the [rule all sleeves share](../README.md). | Medium |

## What it talks to
- **Gets from:** [ModelHome](../../ModelHome/) (budget + probabilities), [Data/DataBase](../../Data/DataBase/) (prices, option chains), [Common](../../Common/) (option pricing, Greeks, expiry calendar), and [Portfolio](../../Portfolio/) (to learn whether a put was assigned and what shares we now hold).
- **Hands to:** [RiskManagement](../../RiskManagement/) (wanted positions).

## Complexity: High
Each trade is simple. The **wheel's step-by-step logic** and handling **assignment** properly (in both backtest and live) are fiddly and easy to get wrong.

## Watch-outs
1. **Gap risk.** TQQQ fell about **80% in 2022**. One bad day can wipe out months of premium. The mood check before selling puts and the limits in [RiskManagement](../../RiskManagement/) exist for this reason.
2. **Assignment must be simulated honestly** in the backtest, including early assignment and what happens at expiry. See [Backtesting](../../Backtesting/).
3. In calm moods this sleeve is **short volatility at the same time as Sleeve A**, so a shock hits both. The combined limits in [RiskManagement](../../RiskManagement/) cover this.

## Read first
White paper §5.2 (with Figure 3, the wheel) and §7. Israelov & Nielsen (2015), "Covered Calls Uncovered", breaks down where covered-call returns really come from.
