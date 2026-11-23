# Sleeves / EquitySleeve (Sleeve B: Equity options)

## What this folder is for
This sleeve bets on **which direction stocks go**, using option trades rather than buying or shorting stocks outright. What it does depends on the market's mood:

- **Stressed:** buys **index put spreads**, which pay off if the market falls. These also partly protect the rest of the portfolio.
- **Calm:** sells **covered calls**, and sells **out-of-the-money puts** on high-volatility and leveraged ETFs such as **TQQQ** (a fund that moves about 3× the Nasdaq-100 each day). Their options pay rich premiums because they're so volatile.

**"The wheel":** if a put we sold gets **assigned** (we're forced to buy the shares), we hold the shares and sell calls against them until we hit an exit target or the shares get "called away" (bought from us). Whether we keep going or exit early depends on the mood: continue while calm, get out when stress probability is high.

Think of it as renting out umbrellas on sunny days and buying them yourself when clouds roll in.

## Files and status
| File | What it does | Status |
|---|---|---|
| `stress_put_spreads.py` | Selects and sizes same-series bearish put spreads. | Implemented and tested locally |
| `calm_premium.py` | Selects and sizes wheel puts/calls, retains shares and stages exits. | Implemented and tested locally |
| `wheel.py` | Classifies confirmed holdings, checks coverage and proposes entry/hold/exit decisions. | Implemented and tested |
| `equity_sleeve.py` | Combines complete strategy books with directional gates and shared funding. | Implemented and tested locally |

## Regime inputs and current implementation

The shared [regime input contract](../README.md#regime-input-contract) supplies
the wheel with `context.market_regime.calm` and
`context.market_regime.stressed`. Each is the sum of two joint states, so a
calm-bear observation contributes to calm probability and a stressed-bull
observation contributes to stress probability. These totals summarize market
stress only. All four joint states remain available for directional policies;
stressed-bull and stressed-bear must not automatically imply the same bearish
trade. Spread decisions and both target pipelines are now implemented as a
research baseline; historical validation and external adapters remain required.

`EquitySleeveConfig` accepts `stress_underlying_ids`, `premium_underlying_ids`
and the required `stressed_bear_entry_probability`. Remove the old `calm_regime` and `stress_regime`
arguments when constructing it. Example:

```python
config = EquitySleeveConfig(
    stress_underlying_ids=("spx",),
    premium_underlying_ids=("tqqq",),
    stressed_bear_entry_probability=0.50,  # illustrative, uncalibrated
)
```

The wheel's entry/exit thresholds belong to `WheelConfig` and are supplied
explicitly. Wheel inspection, selection, sizing and orchestration are implemented.
Portfolio remains the source of
confirmed holdings and assignment events.

Shared pricing and Greeks are now implemented in [Common](../../Common/README.md).
Use `PricingModel.CRR` with American exercise for the wheel's ETF options;
European pricing paths reject that exercise style. The current tree uses a
continuous dividend yield, so it does not yet reproduce scheduled cash-dividend
or assignment events. Contract-master adapters and Portfolio execution wiring
remain external integration tasks.

## Wheel state and decisions

`WheelManager.inspect(context, underlying, snapshot)` reads an immutable equity
Portfolio snapshot whose timezone-aware `as_of` matches the decision cutoff.
It uses canonical instrument metadata and explicit strategy attribution
(`WheelConfig.strategy_id`, default `wheel`). Other strategies' puts are not
guessed to be wheel positions. Holding slices must reconcile to the actual
Portfolio book; the manager cannot verify that reconciliation independently.

| Confirmed wheel holdings | `WheelStage` |
|---|---|
| No shares or short options | `FLAT` |
| Short puts only | `SHORT_PUTS` |
| Long shares without wheel options | `HOLDING_SHARES` |
| Shares and covered short calls, without puts | `COVERED_CALLS` |
| Short puts alongside shares/calls, such as partial assignment | `MIXED` |

Pending orders appear in the state but do not change its stage or confirmed
quantities. Assignment/expiry events are checked against the information
cutoff and are never applied again. Portfolio must already have reflected
them in its holdings and cash.

`WheelManager.plan(context, state)` rechecks the state against its snapshot and
returns a `WheelPlan`. Its policy is evaluated in this order:

| Condition | Decision |
|---|---|
| Total stressed probability meets the exit threshold | Block entries; request exit of wheel holdings/pending wheel work. |
| Capital budget is zero | Block entries; request exit of wheel holdings/pending wheel work. |
| Any open order for this underlying in the equity snapshot | Pause entries until fills/cancellations are confirmed. |
| Total calm probability is below the entry threshold | Hold/manage existing inventory, without new entries or an automatic exit. |
| Flat wheel, calm gate met, calm-bull gate met, positive available cash | Permit the builder to consider new puts. |
| Calm gate met and confirmed unreserved shares remain | Permit the builder to consider covered calls. |

Threshold comparisons are inclusive. Stress wins if configured entry and exit
gates overlap. The separate calm-bull put gate makes direction explicit: two
days with the same total calm probability can produce different put-entry
decisions. Covered calls manage shares already owned and use the calm gate;
they do not require a new bullish entry. Both stressed-bull and stressed-bear
contribute to the defensive wheel exit. This is a configurable research
baseline, not a calibrated or historically validated trading policy.

Example configuration (values are illustrative test settings only):

```python
from Sleeves.EquitySleeve.wheel import WheelConfig, WheelManager

wheel = WheelManager(
    WheelConfig(
        calm_entry_probability=0.60,
        stress_exit_probability=0.50,
        calm_bull_entry_probability=0.40,
        strategy_id="wheel",
    ),
    instruments=instrument_adapter,  # supplied by Common's contract master
)
state = wheel.inspect(context, "tqqq", portfolio_snapshot)
plan = wheel.plan(context, state)
```

The old `plan(..., calm_probability=..., stress_probability=...)` arguments
have been removed. The method now reads the validated joint distribution from
the context. `calm_bull_entry_probability` is a new required configuration
value. No production thresholds have been added to Config.

## Coverage, orders and scope

The state reports confirmed share/put/call quantities, the existing wheel
call-share obligation, available call shares and pending order IDs. Share
capacity is the smaller of wheel-attributed free shares and free physical
shares across this equity snapshot for the same exact underlying. Both
calculations reserve for held short calls, unfilled sell-call orders and
pending share sales. Long calls and unfilled share purchases provide no
physical coverage. Pending call purchases do not release coverage yet.

Held/pending calls with insufficient confirmed coverage raise an error.
Simultaneous share-sale/call-buy exit orders are not assumed to fill in a safe
order: execution must close/cancel the call exposure before releasing its
shares. Pending share sales cannot exceed wheel shares, and option buy orders
cannot overshoot the confirmed short inventory into an unsupported long
option position. Counts use actual pure-share deliverables, including
non-100-share lots. Missing, fractional or unsupported deliverables fail.

`WheelPlan.cancel_order_ids` is cancellation **intent** for wheel entry orders
when exiting (short-option sales and share buys). Existing risk-reducing
orders and other strategies' orders are not automatically cancelled. No
cancel/fill/assignment is executed here. Portfolio/Execution must confirm
cancellations before replacing orders or treating reservations as released.
This cancellation route is still an integration task.

The manager supports long shares and short pure-share-deliverable options in
the snapshot base currency. Unsupported holdings, duplicate records,
unidentified strategy attribution, stale/future snapshots and future-known
events raise explicit errors. No FX conversion or option-to-share assignment
is inferred. Common's adapter must expose only supported simple deliverables.
Portfolio must also account for share encumbrances outside this equity
snapshot, including any other sleeve using the same shares.

Entry flags grant eligibility only. The builder must still choose exact
contracts, satisfy whole-contract coverage, allocate the capital budget,
check strike-based put collateral and costs, and preserve existing holdings
in its complete targets. A blocked entry is not a request for an empty target
list. Both builders and the complete equity entry point are now implemented.
They require valid canonical contract, market, funding and Portfolio adapters.

## Selection, sizing and full targets

See the [target integration guide](../../Docs/SLEEVE_TARGET_INTEGRATION.md)
for required constructor arguments, chain columns, funding conventions,
strategy attribution, cancellation handling and execution dependencies.

Calm selection uses the earliest eligible expiry and nearest strictly OTM
strike. Puts reserve full strike-based cash plus fees, without crediting
premium receipts. Calls use actual deliverables and keep confirmed shares.
Stress selection uses same-expiry compatible puts: long nearest at/below spot,
short next lower strike, equal whole quantities and a positive debit below
strike width after costs. New spreads require the **joint stressed-bear**
gate; stressed-bull alone does not open bearish spreads.

Retained wheel holdings reserve capital first; eligible routes split the
remaining budget and confirmed available cash equally. Inactive stress
strategies target zero. Removed wheel markets unwind in stages. Exits close
options before releasing shares that cover confirmed short calls. An
allocation cut can temporarily leave those shares above budget only while
strictly reducing confirmed exposures; Risk must approve the staged unwind.

Open equity orders raise `PendingOrdersError` with pending IDs and any wheel
entry cancellation intent. No replacement book or cancellation acknowledgement
is fabricated. Resolve pending work through Execution, then request targets
again. An error must never be converted into an empty target list.

Selection uses spread quality filters, not executable-size guarantees. Shared
gross funding reserves include costs and do not assume margin offsets.
Execution must protect grouped legs and fund the actual transition path.
Synthetic full-pipeline checks are in
[test_sleeve_targeting.py](../../tests/test_sleeve_targeting.py).

Tests are in [test_wheel.py](../../tests/test_wheel.py). Run all current Python
unit tests from the repository root:

```powershell
python -B -m unittest discover -s tests -p "test_*.py" -v
```

See [Jacob's running progress log](../../Docs/JACOB_PROGRESS.md) for completed
tasks, checks and remaining integration work.

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
