# Equity and volatility target generation

Implemented locally on 2026-11-23. This describes the research baseline and
the adapter contracts required to run it. Parameters are supplied by callers;
none have been calibrated by this implementation.

## Output and ownership

Both `generate_targets(context)` methods return complete desired holdings.
Quantities are signed whole shares/contracts, never incremental orders.
Omitted holdings target zero. Related option legs retain a stable `group_id`;
shared volatility hedges use `vol:hedge:<risk factor>`. Duplicate holdings
within an instrument/group combine, separate groups remain attributed slices,
and opposing slices fail rather than silently netting away strategy exposure.

The engine must pass the **whole book** through RiskManagement and Portfolio.
Risk changes to option quantities require recalculating/checking the hedge and
preserving spread ratios. Portfolio must aggregate instrument quantities for
execution while retaining the group ledger. It owns actual holdings, open
orders, cash, fills and lifecycle events. No sleeve sends orders or applies
assignment. Existing engine/allocator, Risk and Portfolio implementations are
still team dependencies; finishing these methods does not finish those layers.

## Shared inputs: `Common/targeting.py`

`SelectionPolicy(base_currency, market_timezone, max_relative_spread,
fee_per_contract, max_contracts)` has no production defaults. The spread
measure is `(ask-bid)/mid`. Fees are per option contract in the base currency;
zero explicitly models no option fees. `max_contracts` bounds integer sizing
and the volatility sizing search. Supply reasonable research limits.

`MarketSnapshot(underlying, as_of, currency, spot)` must match the exact market,
decision timestamp and base currency. `market_lookup(underlying, as_of)` must
use only information known then. The timestamp denotes a valuation at the
decision cutoff; its adapter must reject stale underlying observations.

Builders accept daily DataFrames with these mandatory columns:

| Column | Contract |
|---|---|
| `underlying` | Exact logical traded market, never an implicit proxy. |
| `obs_date`, `known_at` | Python dates, both equal the decision's local market date. |
| `source` | Nonempty, single disambiguated source; retain a model-priced tag if applicable. |
| `contract_id` | Provider identity; must resolve to a separate canonical instrument ID. |
| `expiry`, `strike`, `call_put` | Date, positive finite strike, `C`/`P`. |
| `bid`, `ask` | Finite nonnegative bid, positive ask, no crossed quotes. |

Empty chains, duplicate/ambiguous contracts, mixed sources and missing metadata
raise. Out-of-policy DTE/spread rows are excluded. A selected short entry needs
a positive bid. The spread filter is **not** evidence of executable size: no
order-book depth, volume or open-interest minimum is inferred. Execution must
check actual liquidity. DATE metadata relies on the data adapter enforcing
its documented daily release cutoff; it cannot prove intraday availability.

Canonical resolution must match quoted underlying, expiry, strike and type.
Multipliers and currencies are explicit. `series_id` must identify the exact
exercise/settlement/deliverable family (including settlement timing, adjusted
terms and quote conventions), not merely an underlying ticker. Both legs
require the same series, expiry, multiplier and currency, and distinct IDs.
The Common contract-master adapter must reject unsupported baskets/terms.
`EquityInstrument` now has optional `expiry`, `strike`, `series_id` fields for
legacy holding compatibility; all three are required when selecting entries.
Volatility's `OptionContractRef` requires those exact fields and `call_put` /
`underlying` in addition to its original ID/multiplier/currency fields.

## Capital and sizing

Construct **one shared** `CapitalModel(base_currency, lookup)` per equity
sleeve, and supply it to both equity builders. Volatility receives its model
through the structure builder. `lookup(instrument_id, as_of)` returns:

```python
CapitalSnapshot(
    instrument_id=canonical_id,
    as_of=decision_time,
    currency=base_currency,
    long_requirement=long_reserve_per_unit,
    short_requirement=short_reserve_per_unit,
    policy_source="named broker/research funding policy",
)
```

Both reserves must be positive finite **base-currency** amounts for one share
or contract. IDs, currency and timestamp are checked. The adapter must include
funding/margin buffers and applicable entry/exit fees, including hedge trading
costs. No broker margin formula is fabricated. Stock purchases normally need
full cash; stock shorts need an explicit borrow/funding policy; futures need
explicit contract margin and multipliers. Unsupported shorts must raise.

The book uses gross additive reserves:
`sum(abs(quantity) * reserve_for_that_position_sign)`. It deliberately does
not grant spread, covered-call or cross-market margin offsets. Long option
reserves must cover ask times multiplier plus configured option fees. Puts in
the wheel additionally require strike times deliverable shares plus fees;
premium receipts do not reduce that assignment reserve. New equity routes
share the available cash once, after reserving desired retained wheel holdings.
An adapter which double-counts fees makes sizing conservative; an adapter
which omits material costs must be corrected before using results.

Short-vol funding reserves are **not maximum-loss estimates**. Short calls
can have unbounded loss even with a positive margin reserve. Margin expansion,
stress loss, borrow, FX, settlement obligations and cross-sleeve coverage remain
Risk/Portfolio checks. These APIs accept validated adapters, not a live broker
margin feed implemented by this task.

## Volatility policy and pipeline

1. Split the capital allocation equally across configured markets. Unused
   allocations remain idle; no opportunistic redistribution is assumed.
2. Read RV/IV at the cutoff, forecast with that market's fitted forecaster,
   and generate the existing volatility signal. Missing/unfitted/stale inputs
   propagate errors and do not become flatten instructions.
3. Neutral means target **zero options and zero associated hedge**. A zero
   sleeve budget explicitly flattens without requiring fresh data. Removed
   markets also disappear from the complete desired book.
4. Require actual quoted expiry **equal to `iv.horizon_end`** and inside DTE
   bounds. A nearby monthly expiry does not silently substitute for a trading
   horizon. If none exists, raise; configure an expiry-aligned horizon or later
   build an explicitly validated expiry-specific forecasting policy.
5. Straddles use the common call/put strike nearest spot, ties to lower strike.
   Strangles use the strictly OTM put/call pair with smallest total distance,
   ties to lower put strike. Canonical incompatible chosen terms fail closed;
   this baseline does not optimize over multiple settlement series.
6. Both legs have equal quantities and the signal's sign. Budget and
   `max_contracts` determine the initial whole-lot count.
7. Calculate a hedge for each candidate count, descending until options plus
   hedge fit that market's slice. Aggregate options and rehedge the combined
   book. If shared-factor rounding breaches the sleeve budget, remove whole
   lots from the lexically last group and rehedge until it fits. This is a
   deterministic conservative fallback, not an allocation optimizer.

Delta adapters return `DeltaSnapshot` for each exact instrument at the
decision cutoff. `cash_delta_per_unit` is base-currency P&L for a +1% move in
the named factor, including multipliers, FX and any explicit factor mapping.
Use the same convention for options and hedges. The mapping may deliberately
use an ETF/future proxy only if its factor relationship is modeled by the
adapter; naming the factor alone cannot validate hedge effectiveness.

`hedge_quantity = -sum(option_quantity * option_cash_delta) / hedge_cash_delta`.
Round to the nearest whole unit, ties away from zero. Each factor's estimated
residual is at most half a hedge unit's cash delta; Risk must decide whether
that absolute residual is acceptable. There is no universal acceptable delta
limit inferred here. Missing factors, stale sensitivities, wrong currency,
zero hedge delta and reuse of one hedge across independent active factors
raise. An option cannot also be configured as its hedge instrument.

The structure uses an ATM volatility comparison even when selecting an OTM
strangle; skew/term structure and costs can change its economic attractiveness.
That research assumption still needs historical validation.

## Equity policy and pipeline

`EquitySleeveConfig(stress_underlying_ids, premium_underlying_ids,
stressed_bear_entry_probability)` now requires the directional threshold.
The wheel continues using its configured calm, calm-bull and total-stress
gates. Bearish spreads require **joint stressed-bear** at/above the separate
threshold. Stressed-bull alone closes the defensive wheel without opening
bearish spreads. Any overlap between configured wheel/spread gates splits
remaining capital equally among eligible market/strategy routes.

The orchestrator reads an exact confirmed `EquityPortfolioSnapshot`, manages
held wheel markets even after removal from the entry universe, and rejects
unknown strategy attribution. Builders and WheelManager must share the
same canonical instrument adapter. Calm builder's `strategy_id` must match the
manager; stress builder's ID must differ (defaults: `wheel`,
`stress_put_spread`). Preserve those tags in Portfolio's holding ledger.
`TargetPosition` carries group attribution; strategy mapping/persistence must
remain in Portfolio, since the existing trading schema does not store it yet.

Wheel entries choose the earliest expiry, then the nearest strictly OTM put
or call. New puts require the flat-wheel policy and full cash collateral.
Covered calls retain **all** confirmed wheel shares and cannot exceed the
unused physical share deliverables established by WheelManager. New wheel
entries support whole pure-share deliverables equal to the quote multiplier;
unsupported adjusted terms fail. Existing options/shares retain their groups.
Blocked entries preserve holdings; they do not flatten the book.

Retained puts also require an actual strike and a funding reserve covering
strike-based assignment cash plus fees. Optional legacy metadata permits wheel
inspection; it does not waive the funding check when retaining a short put.

On stress, zero allocation, removal from the universe or an oversized retained
wheel after an allocation cut, exit options first. While short calls remain
confirmed, the target retains the shares. After Portfolio confirms those
calls closed, the next decision can target the shares to zero. A staged
reduction may temporarily exceed a reduced budget only if the result is a
strict subset of already confirmed holdings, without increased quantities.
This exception enables unwinding while preserving coverage; Risk must still
approve it and Portfolio must fund closing trades. No exception permits a
new trade above budget.

Any open equity orders block issuance of a replacement book with
`PendingOrdersError`. It contains `pending_order_ids` and wheel
`cancel_order_ids` **intent** for exiting risk-increasing orders. The caller
must resolve/confirm orders then request targets again. Existing closing
orders are not automatically cancelled. Catching the exception must **not**
substitute an empty target list. Stress-order cancellation/closing workflow
and all actual cancellation calls belong to Execution.

Stress spreads use the earliest expiry with a pair of puts, choose the long
strike nearest to (at or below) spot, then the closest lower short strike.
They require equal compatible terms and positive ask-minus-bid debit plus
fees below strike width times multiplier. Equal whole quantities preserve
the spread. Funding remains gross rather than claiming broker offsets.
Inactive/removed stress strategies target zero; active strategies are rebuilt
from that day's selection. Execution must close/roll spreads as protected
groups, retain hedges/coverage during transitions and reserve actual cash for
old positions plus new orders. Desired-book funding is not a transition-path
funding guarantee and does not assume close proceeds have arrived.

## Wiring and verification

Each builder constructor now requires `market_lookup=` and `capital_model=`.
Each builder config adds `selection=SelectionPolicy(...)`. Volatility's
`build` adds required `horizon_end=`. `DeltaHedger` keeps its original public
constructor and returns hedge targets only. See
[`test_sleeve_targeting.py`](../tests/test_sleeve_targeting.py) for complete
synthetic adapter wiring of both sleeves and all constructor arguments.
[`test_vol_data_integration.py`](../tests/test_vol_data_integration.py) also
runs production-schema in-memory access -> daily adapter -> fitted HAR ->
signal -> actual fixture chain -> canonical resolution -> funded targets ->
hedge. No local databases, broker orders or real chains are fabricated.

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p "test_*.py" -v
git diff --check
```

To run against actual data, supply the contract master, point-in-time spot /
delta / funding adapters, independent exchange sessions, actual or explicitly
model-priced chains and confirmed Portfolio state. `DatabaseVolMarketData`
already supplies the volatility data methods; its same-day `get_option_chain`
also matches EquityMarketData's method for explicitly configured markets.
Historical fitting, assignments/dividends, realistic execution/costs, regime
model fixes and out-of-sample portfolio testing remain required before
performance or live-readiness claims.
