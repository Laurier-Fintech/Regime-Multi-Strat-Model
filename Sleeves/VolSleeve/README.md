# Sleeves / VolSleeve (Sleeve A: Volatility)

## What this folder is for
This sleeve bets on **how big market moves will be**, not which way they go.

The sleeve compares annualized implied volatility with its own forecast of
realized volatility over the same future window. The implemented edge is a
volatility difference, not a variance-swap premium or a profit estimate after
costs:
- Options look **expensive** (implied well above our forecast) → **sell** volatility.
- Options look **cheap** → consider **buying** volatility. High stress vetoes
  a short-volatility proposal; stress alone does not force a long trade.

Think of it as an insurance company. Most of the time it collects premiums because people overpay for insurance. It has to be very careful about the rare disaster.

## Files and status
| File | What it does | Status |
|---|---|---|
| `rv_forecast.py` | HAR-style variance baseline and validated forecast records. | Implemented; historical training preparation remains |
| `signal.py` | Validates alignment/freshness; compares IV with forecast and applies a stress veto. | Implemented and tested |
| `market_data.py` | Read-only database adapter for RV features, horizon-aligned ATM IV and actual chains. | Implemented and tested |
| `structures.py` | Canonical contract selection and whole-structure sizing. | Implemented and tested locally |
| `delta_hedge.py` | Sensitivity aggregation and desired whole-unit hedges. | Implemented and tested locally |
| `vol_sleeve.py` | Complete option/hedge targets within shared capital budgets. | Implemented and tested locally |

**Universe:** liquid options on equity indices, Treasuries, gold and oil.

## Regime inputs and current implementation

The sleeve uses the same [regime input contract](../README.md#regime-input-contract)
as the equity sleeve. `context.market_regime.stressed` is the sum of
`stressed-bull` and `stressed-bear`; `calm`, `bull` and `bear` are also available.
The four joint probabilities remain available for more detailed policies.

The implemented signal uses total stressed probability to veto short volatility.
Both stress directions count for this movement-size policy. It preserves the
joint states for future policies; the equity wheel separately uses calm-bull
probability for put entries. Contract selection, sizing, hedging and complete
target generation are now implemented with explicit adapters; historical
validation and production integration remain.

Shared pricing and Greeks are now implemented in [Common](../../Common/README.md).
Choose the model from the exact underlying type and exercise style. European
spot options use Black-Scholes-Merton; European futures options use Black-76;
American spot options use the CRR tree. The cash-delta helper converts unit
delta into P&L for a +1% price move using an explicit multiplier and FX rate.
The adapter to `DeltaSnapshot` must still verify the risk-factor mapping and
information cutoff before those sensitivities can be used by the hedger.

## Signal policy

`VolSignalGenerator.generate(context, forecast, implied_vol)` requires matching
logical underlying IDs, trading-day horizons and forecast decision timestamps.
The IV observation must have been known by the decision cutoff and must pass
the configured observation-age limit. A newer revision does not make an old
market observation fresh. Missing, stale or incompatible data raises an error
instead of being represented as `NEUTRAL`.

Age limits measure elapsed time in UTC, including daylight-saving changes.

| Validated comparison | Signal |
|---|---|
| IV - forecast >= `min_edge`, below stress veto threshold | `SHORT_VOL` |
| IV - forecast >= `min_edge`, at/above stress veto threshold | `NEUTRAL` (short proposal vetoed) |
| IV - forecast <= `-min_edge` | `LONG_VOL` |
| Gap inside the band | `NEUTRAL` |

All values use annualized decimals: `min_edge=0.02` means two volatility
percentage points. Edge thresholds are inclusive, with only relative 1e-12
arithmetic roundoff tolerance. High stress never creates a long-volatility
trade without a sufficiently cheap IV comparison. This is a research baseline;
its thresholds and behavior are not calibrated performance results.

`VolSignalConfig` now requires `min_edge`, `stress_block_short_probability` and
`max_iv_age` (`timedelta`). Earlier code constructing it with only `min_edge`
must supply the other two. A signal expresses exposure intent, not orders.
The structure builder and full sleeve implement neutral as an unwind: options and associated
hedges target zero. Signal generation itself never sends orders.

## Read-only daily market adapter

`DatabaseVolMarketData` implements `VolMarketData` using only public functions
from `Data/DataBase/access.py`. It performs no downloads, direct SQL or writes.
The reader's new optional `include_metadata=True` mode retains actual `known_at`
dates; default calls keep their previous outputs. RV feature metadata is long
format and forbids filling, so provenance cannot be silently carried forward.

Required adapter inputs are explicit:

- `VolMarketSpec` identifies the strategy market, RV feature underlying and
  IV source underlying. A different source identity requires a `proxy_reason`.
  For example, SPY RV features may be explicitly acknowledged as an SPX
  research proxy. This does not prove they are equivalent. There are no default
  SPY/SPX or QQQ/NDX substitutions. Returned records retain source identities.
- `SessionCalendar` contains a complete sorted tuple of independently known
  exchange session dates covering observations and future horizons. Holidays
  must be included correctly by the caller; never build it from future prices.
- `VolDataConfig` defines market timezone, local daily availability time,
  maximum observation age, one IV source and an optional actual-quote source.

The database currently has DATE precision. The adapter stamps observation and
known dates at the supplied availability time in the supplied market timezone.
This is a declared daily convention, not evidence of intraday release times.
Decisions before that time or on dates outside the session calendar fail.
Session-close-to-session-close horizons are used; this is not intraday timing.
The upstream daily metadata cannot establish whether an intraday revision was
already available at an earlier hour of its recorded known date.

RV reads use the latest observation date and require all three requested
`rv_<source>_1d/5d/22d` features on that same date. Missing values/dates are not
filled or mixed with older rows. `RVInputs` now optionally retains
`source_underlying`, `observed_at` and `known_at`. Manually prepared historical
examples remain compatible, but training preparation must enforce the same
source mapping, availability convention and future outcome window.

### Matching IV to the future window

The adapter selects the latest ATM (`pct_spot=100`) curve from one configured
source. It uses the actual next H supplied sessions after decision date D to
find horizon end E. Provider tenors are calendar days; Bloomberg month tenors
have already been normalized by the importer to multiples of 30 days.

For an observation dated O, it linearly interpolates **total variance**
`W(t) = IV(t)^2 * t`, with t in calendar days. It returns annualized volatility
`sqrt((W(E-O) - W(D-O)) / (E-D))`. This covers the decision-to-end window even
when the allowed observation is older. The zero-variance origin supplies the
start of an older quote's forward window, implying flat volatility between
zero and the first tenor. The end must be bracketed by actual quoted tenors:
no short-end or long-end horizon extrapolation is allowed. Decreasing total
variance, duplicate tenors and invalid values are rejected.

This convention follows the total-variance/forward-variance approach documented
in [QuantLib's variance curve](https://github.com/lballabio/QuantLib/blob/master/ql/termstructures/volatility/equityfx/blackvariancecurve.cpp)
and [forward volatility implementation](https://github.com/lballabio/QuantLib/blob/master/ql/termstructures/volatility/equityfx/blackvoltermstructure.cpp).
It is an ATM term-curve estimate, not a complete option surface or variance-swap
replication. No blanket 252/365 conversion is applied to volatility.

The output records observation/availability timestamps, source underlying,
source name, horizon end and tenors used. Source age limits still apply after
forward-window adjustment; interpolation cannot make stale data acceptable.

### Actual option chains

`get_option_chain()` reads actual quotes for the logical traded underlying on
the decision date, retains their metadata/provider contract IDs and checks
basic contract/quote validity. Multiple quote sources must be disambiguated.
Liquidity, canonical instrument resolution and final DTE selection remain
builder responsibilities. An empty chain raises: Bloomberg IV grids do not
manufacture historical contracts. Model-priced chain reconstruction remains
an explicit Backtesting/contract-master integration task.

### Configuration example

Values below are illustrative. `exchange_session_dates`, `market_timezone`,
`context` and `fitted_forecaster` must be supplied by the application.

```python
from datetime import time, timedelta
from Common.calendar import SessionCalendar
from Sleeves.VolSleeve.market_data import DatabaseVolMarketData, VolDataConfig, VolMarketSpec
from Sleeves.VolSleeve.signal import VolSignalConfig, VolSignalGenerator

data = DatabaseVolMarketData(
    VolDataConfig(
        markets=(VolMarketSpec("spx", "spy", "spx", "Explicit SPY RV proxy for SPX research."),),
        market_timezone=market_timezone,
        available_time=time(16, 15),
        max_observation_age=timedelta(days=3),
        iv_source="bloomberg",
    ),
    calendar=SessionCalendar(exchange_session_dates),
)
inputs = data.get_rv_inputs("spx", as_of=context.as_of)
forecast = fitted_forecaster.forecast(inputs, horizon_trading_days=22)
iv = data.get_implied_vol("spx", as_of=context.as_of, horizon_trading_days=22)
signal = VolSignalGenerator(
    VolSignalConfig(0.02, 0.50, timedelta(days=3))
).generate(context, forecast, iv)
```

## Verification

Run the full suite in the configured project environment:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p "test_*.py" -v
```

Signal, adapter and production-schema in-memory DuckDB tests cover cutoffs,
future revisions, proxy acknowledgement, fresh/stale observations, coherent
feature dates, holidays, tenor interpolation/forward windows, source selection,
quote checks and default API compatibility. One integration case fits HAR to
synthetic outcomes, then passes database inputs through forecast and signal.
Tests do not populate the local database or demonstrate trading performance.

The complete volatility entry point now returns funded option and hedge
targets with supplied adapters. See the
[target integration guide](../../Docs/SLEEVE_TARGET_INTEGRATION.md) and
[Jacob's progress log](../../Docs/JACOB_PROGRESS.md).

## Contract selection and integrated sizing

`StructureConfig` now requires a shared `SelectionPolicy`; the builder also
requires `market_lookup=` and `capital_model=`. Exact canonical references
include underlying, expiry, strike, option type and settlement-series ID.
No provider ID, multiplier, currency, margin or spot is invented.

Vol structures require a quoted expiry **equal to the IV/forecast horizon end**
and within configured DTE bounds. Missing that expiry raises rather than
substituting a different risk window. Straddles use the nearest common ATM
strike; strangles use the nearest strictly OTM put/call pair. Legs retain a
stable group and equal signed whole-contract counts.

Each configured market receives an equal budget slice. Sizing covers the
combined option and hedge reserves, then recomputes shared-factor hedges and
checks the entire sleeve budget. Gross funding reserves are supplied by an
explicit policy adapter; a short premium is not collateral or maximum loss.
Neutral, removed markets and zero budgets target zero; data/model errors raise.

The hedger uses base-currency P&L per +1% factor move for each desired option
unit and its configured hedge. It rounds nearest whole units, ties away from
zero; estimated residual is at most half one hedge unit. Risk must assess that
absolute residual, stress exposure and funding. Shared hedges receive
`vol:hedge:<factor>` groups. Risk changes to options require rehedging.

The production-schema integration test now extends through fitted HAR,
canonical fixture contracts, whole-lot sizing and a funded delta hedge. This
is a synthetic integration check, not a historical P&L test or live adapter.

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
