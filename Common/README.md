# Common

## What this folder is for
These are shared tools that **several folders need**, kept in one place so there's only ever one version of each. If the option pricing formula lived separately in three sleeves, they would eventually disagree, and nobody would notice until the numbers stopped adding up.

Think of it as the shared toolbox. Every station in the kitchen uses the same knives and the same scales.

## Files and status
| File | What it does | Status |
|---|---|---|
| `option_pricing.py` | Validated vanilla call/put inputs; Black-Scholes-Merton, Black-76 and CRR binomial prices. | Implemented |
| `greeks.py` | Delta, gamma, vega, theta, rho and contract cash-delta conversion. | Implemented |
| `targeting.py` | Shared quote/contract validation, market snapshots, gross funding reserves and grouped target checks. | Implemented; requires explicit adapters |
| `implied_vol.py` | Infer volatility from an option's price. | Planned |
| `vol_surface.py` | Interpolate IV across strikes and expiries. | Planned |
| `calendar.py` | Explicit immutable session dates and next-session lookup. | Implemented; caller supplies the exchange schedule; holiday generation, expiries and rolls remain planned |
| `instruments.py` | Shared contract master, multipliers, currencies and broker IDs. | Planned |
| `logging_setup.py` | Shared log setup. | Planned |

## Choosing a pricing model

Call `price_option(inputs, model=...)` and `calculate_greeks(inputs, model=...)`
with the same inputs and model. Exercise style is required in `OptionInputs`;
obtain it from the exact contract specification rather than guessing from a
ticker. The model argument is also required to avoid silently using the wrong
pricing assumptions.

| `PricingModel` | `underlying_price` means | Supported exercise | Calculation |
|---|---|---|---|
| `BLACK_SCHOLES` | Spot price | European | Black-Scholes-Merton with continuous dividend yield |
| `BLACK_76` | Futures price | European | Discounted Black formula; `dividend_yield` must be zero because carry is already reflected in the supplied futures price |
| `CRR` | Spot price | European or American | Cox-Ross-Rubinstein tree; American nodes compare exercise against continuation |

ETF options permit American exercise ([OCC contract specifications](https://www.theocc.com/clearance-and-settlement/clearing/etf-options)).
The TQQQ wheel therefore has an early-exercise-capable spot pricer in `CRR`.
The European formulas reject American inputs. American options on futures
are not supported by the Black-76 path; do not relabel those as European.

These are estimates with constant volatility, interest rate and dividend
yield. The spot models use a **continuous dividend yield**, not scheduled cash
distributions. The tree includes optimal exercise on its grid; it does not
simulate actual holder exercise, assignment, ex-dividend dates, market fills,
transaction costs or collateral. Portfolio and Backtesting still own those
events. Discrete dividends and adjusted/nonstandard deliverables need a later
contract-aware implementation before historical assignment results can be
treated as realistic.

## Units and numerical boundaries

All prices and Greeks describe **one long option per underlying unit**, before
contract multiplier, position quantity and currency conversion.

| Input/output | Convention |
|---|---|
| `underlying_price`, `strike`, returned price | Quote-currency price units; both inputs strictly positive. Negative futures prices require a different model. |
| `time_to_expiry` | Nonnegative calendar-year fraction. For an ACT/365F convention use elapsed calendar time / 365 days; the caller supplies this consistently. A forecast's trading-day count is not this quantity. |
| `volatility` | Nonnegative annualized decimal, e.g. `0.20` means 20%. |
| `risk_free_rate`, `dividend_yield` | Finite continuously compounded annual decimals; negative values are supported. |
| Delta / gamma | First / second price derivative with respect to spot (`BLACK_SCHOLES`, `CRR`) or futures price (`BLACK_76`). |
| Vega | Derivative per +1.0 decimal volatility; `vega_per_vol_point` multiplies it by 0.01. |
| Theta | Derivative per calendar year of **elapsed time**, holding other inputs fixed. `theta_per_calendar_day` divides by 365. It is a local estimate rather than a full one-day reprice. |
| Rho | Derivative per +1.0 decimal rate; `rho_per_rate_point` multiplies it by 0.01. Black-76 rho holds the supplied futures price fixed. |

Multiply unit value or Greeks by signed contract quantity and the actual
contract multiplier to obtain position amounts. Never assume every option
has a 100-share multiplier or deliverable. FX conversion is separate.

At expiry, prices return intrinsic value. At zero volatility, European prices
use the discounted deterministic payoff; American prices maximize discounted
exercise value over the configured grid. Greeks reject expiry and zero
volatility explicitly, since kinks and settlement require a separate policy.
Inputs reject NaN, infinity, booleans, invalid enum values and negative time or
volatility. Unsupported model/exercise combinations always raise an error.
Numerically unrepresentable exponents and inadmissible tree probabilities
raise rather than being replaced with fabricated prices.

The CRR default is `tree_steps=501`, with a minimum of 2. Time is O(N squared)
and working memory O(N). More steps increase cost; check convergence for the
contracts being priced (for example 501 versus 1001), especially near expiry
or an exercise boundary. A probability outside [0, 1] is rejected with a
request to increase steps. It is never clipped into range.

European Greeks are analytic. CRR delta/gamma/theta use the first two tree
levels; vega and rho use central repricing bumps on the same grid. Default
volatility/rate bumps are `0.0001` in decimal units (one basis point); the
volatility bump is capped at half the input volatility. Tree Greeks are
numerical estimates and can be noisy near exercise boundaries.

## Example and sleeve integration

This standalone example uses hypothetical inputs, with no database access:

```python
from Common.option_pricing import (
    ExerciseStyle, OptionInputs, OptionType, PricingModel, price_option,
)
from Common.greeks import calculate_greeks, cash_delta_for_one_percent_move

inputs = OptionInputs(
    option_type=OptionType.PUT,
    exercise_style=ExerciseStyle.AMERICAN,
    underlying_price=80.0,
    strike=75.0,
    time_to_expiry=30 / 365,
    volatility=0.70,
    risk_free_rate=0.04,
    dividend_yield=0.01,
)
unit_price = price_option(inputs, model=PricingModel.CRR)
greeks = calculate_greeks(inputs, model=PricingModel.CRR)

# Use a multiplier resolved from the contract master; 100 is illustrative.
multiplier = 100.0
contract_value = unit_price * multiplier
cash_delta = cash_delta_for_one_percent_move(
    greeks.delta, inputs.underlying_price, multiplier=multiplier, fx_rate=1.0,
)
```

`cash_delta` is first-order base-currency P&L for a +1% move in this price
variable, per one long contract. `fx_rate` is base currency per one unit of
quote currency. Multiply by signed quantity for the option book's exposure.
For Sleeve A this matches `DeltaSnapshot.cash_delta_per_unit` **only after**
its adapter verifies the same risk factor, price variable, currency, multiplier
and information cutoff. A futures delta cannot silently substitute for an ETF
spot delta or a differently mapped risk factor.

Sleeve B's builders can use model prices and Greeks when selecting and sizing
wheel contracts and spreads. Sleeve A can use the same tools for option
structures, sensitivity aggregation and delta hedging. These connections are
still to be implemented: this task supplies pure calculations, without
changing the sleeve decision rules or producing orders.

Callers must read inputs through `Data/DataBase/access.py`, enforce their
`as_of` cutoff and reject stale/misaligned inputs. These functions validate
numbers, not data provenance. Reconstructed quotes must be marked model-priced
in Backtesting and fill records; a model estimate is not an executable quote.

## Verification and references

Pricing/Greek tests use the standard library. The full suite now also tests
the database adapter and requires the project's pandas, DuckDB, NumPy and
PyYAML dependencies. From the repository root, use the configured environment:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p "test_*.py" -v
```

`tests/test_option_pricing.py` checks reference prices, put-call parity,
monotonicity, bounds, tree convergence, a hand-calculated American exercise
case and input/boundary errors. `tests/test_greeks.py` checks analytic Greeks
against price differences, tree-Greek convergence, immediate exercise and
contract/FX scaling. The same command includes the existing regime tests.

The implementation uses standard formulas, independently written here.
Reference material and cross-checks:

- [QuantLib BlackCalculator](https://github.com/lballabio/QuantLib/blob/master/ql/pricingengines/blackcalculator.cpp): Black valuation and derivative conventions.
- [QuantLib European option tests](https://github.com/lballabio/QuantLib/blob/master/test-suite/europeanoption.cpp): published Haug reference cases used in the pricing tests.
- [Cox, Ross and Rubinstein (1979), Option Pricing: A Simplified Approach](https://bpb-us-w2.wpmucdn.com/u.osu.edu/dist/7/36891/files/2017/07/CRR79-1yy8av8.pdf): binomial valuation and early exercise.
- [OCC ETF option specifications](https://www.theocc.com/clearance-and-settlement/clearing/etf-options): exercise style and adjusted contract units.

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
