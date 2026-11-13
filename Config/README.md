# Config

## What this folder is for
Every setting the system uses, in one place, kept **separate from the code**. That way you can change a risk limit or add a ticker without editing logic, and every backtest records exactly which settings it used.

Think of it as the control panel. The machine stays the same, and you turn the dials here.

## Files that will live here (planned)
| File | What it does | Complexity |
|---|---|---|
| `universe.yaml` | Which instruments each sleeve may trade, and which data series feed the regime model. | Low |
| `model.yaml` | Regime engine settings: which features feed the stress model and the direction model, how often to refit, how much history to wait for before the first fit, the capital mix for each of the four moods, how much to smooth allocations, and the weight caps and shrinkage guardrails. | Low |
| `sleeves.yaml` | Per-sleeve settings: entry and exit thresholds, option expiries and strikes to target, wheel exit rules. | Low |
| `risk.yaml` | Risk limits: maximum net vega and delta, the VIX circuit-breaker trigger, and tail-hedge size. | Low |
| `backtest.yaml` | Start and end dates, cost assumptions (commissions, slippage), **sleeves on/off**, and the stand-in ETF for each sleeve when sleeves are off. | Low |
| `.env.example` | A **template** listing the secret keys needed (FRED API key, IBKR account and port), with blank values. | Low |
| `.env` | **Your real keys. Never committed to Git**: the repo is public. Each person keeps their own copy. | — |

## What it talks to
- **Gets from:** people. You edit these files by hand.
- **Hands to:** every folder reads its own section.

## Complexity: Low
These are plain settings files.

## Watch-outs
1. **Never commit `.env` or any password, key or account number.** The repo is public, and anything pushed should be treated as leaked, even if it's deleted afterwards.
2. **Save the settings with every backtest result**, so you can always tell which settings produced which numbers.
3. **Paper vs live account** is set here. Make it obvious and hard to change by accident.

## Read first
White paper §4.2 (guardrails), §7 (risk controls) and §9 (realistic cost model).
