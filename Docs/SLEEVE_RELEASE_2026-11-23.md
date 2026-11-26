# Equity and volatility sleeve implementation release

Release date: 2026-11-23. Development branch: `jacob/dev`.
Main baseline: `13fac5adebb778946d013094a39d8ce822ef0767`.

## Publication scope and synchronization

This release packages Jacob's five follow-on sleeve tasks and the project
briefing. Before publication, a fresh origin fetch and branch comparison
showed `jacob/dev` HEAD and `origin/main` at the same baseline, with zero
commits ahead/behind and no main changes to merge. The original foundation
(`4f90c28`) and the team's database/HMM/Bloomberg work were already in main;
they are not new contributions in this release.

The publication advances both `origin/jacob/dev` and `origin/main` to the same
tested release commit using an atomic, ordinary fast-forward push. There is
no force push or history rewrite. A concurrent incompatible change to main
causes publication to fail rather than overwriting another contributor.
Use the commit introducing these notes and the remote branch hashes as the
publication record; a successful push is verified against GitHub afterward.

## What changed and why it matters

| Area | Changes in this release | Significance |
|---|---|---|
| Shared sleeve inputs | Validated immutable four-state joint regime probabilities and marginal views. | Preserves calm-bull versus calm-bear and stressed-bull versus stressed-bear for direction-sensitive policies. |
| Shared pricing and Greeks | Black-Scholes-Merton, Black-76 and CRR; delta, gamma, vega, theta, rho and explicit cash-delta units. | Gives both sleeves one pricing/sensitivity convention and rejects incompatible exercise styles. |
| Calendar and targeting | Explicit session list; daily quote/canonical contract checks; dated spot and gross funding snapshots; grouped target checks. | Prevents inferred holidays, provider-ID substitution, missing multiplier/FX assumptions and independent reuse of the full capital allocation. |
| Equity wheel | Confirmed state, pending-order coverage reservations, calm/calm-bull/stress gates, cash-secured puts, covered calls and staged exits. | Uses actual holdings and deliverables, keeps covering shares until calls are confirmed closed and preserves existing holdings when entry gates are blocked. |
| Bearish equity spreads | Same-series higher-strike long/lower-strike short puts, debit/width checks and whole-lot funding. | Adds a bearish route gated by joint stressed-bear probability rather than all stressed observations. |
| Volatility inputs and signal | Public database adapter, source/proxy provenance, session-aligned IV total variance, validated edge and stress veto. | Aligns the IV and forecast windows, rejects future/stale inputs and distinguishes neutral decisions from data failures. |
| Volatility structures and hedge | Exact-expiry straddles/strangles, canonical terms, signed whole lots and factor cash-delta hedges. | Includes options and hedge funding in sizing and preserves related legs and attribution. |
| Both public entry points | Complete desired holdings, route/market allocation, final coverage/funding checks and explicit errors. | Finishes the internal target-generation pipelines for use by the team's engine, Risk and Portfolio layers. |
| Database API | Opt-in `include_metadata=True` for features, IV and chains. | Retains actual availability/version metadata while preserving legacy default output shapes; no schema changes. |
| Dependencies and documentation | Explicit NumPy 2.5.2 dependency, running progress log, integration guide, briefing PDF, README and sprint updates. | Makes the numerical dependency visible and documents algorithms, ownership, interface migrations, evidence and remaining work. |

## Interface changes callers must adopt

- `SleeveContext.regime_probabilities` requires the exact four joint keys:
  `calm-bull`, `calm-bear`, `stressed-bull`, `stressed-bear`. The model's pandas
  Series must be converted with `.to_dict()`; warm-up `None` needs an engine
  policy, not zero probabilities.
- `EquitySleeveConfig` requires `stressed_bear_entry_probability` alongside its
  two universes. `WheelConfig` supplies the calm, calm-bull and total-stress
  gates. `WheelManager.plan(context, state)` reads the probabilities from context.
- All selection configs require `SelectionPolicy`; builders require explicit
  `market_lookup` and `capital_model` dependencies. Equity builders and the
  wheel share the same instrument adapter; equity builders share one funding
  model. No production defaults for thresholds or costs are calibrated here.
- Canonical entry contracts require exact underlying, expiry, strike, type,
  multiplier, currency and a settlement/exercise/deliverable `series_id`.
  Legacy wheel inspection metadata does not waive retained-put collateral checks.
- Volatility structure building requires `horizon_end`, and selected expiry
  must equal it. Missing that exact quoted expiry raises rather than rolling
  the forecast window silently.
- Desired quantities are complete signed whole holdings. Omitted positions
  target zero; volatility neutral explicitly unwinds. Errors, including equity
  `PendingOrdersError`, must not be replaced with empty target lists.
- Portfolio must preserve strategy/group attribution and resolve pending work
  and staged exits. Risk changes to options require hedge recalculation or a
  fresh combined exposure check.

## Verification

The full suite was rerun before publication: **187 tests passed**. It covers
regime boundaries, pricing/Greeks, partial wheel assignment/fills, coverage,
metadata/revision cutoffs, calendars, signals, contract selection, gross
funding, integer hedges, budget sharing, staged exits and error propagation.
The production-schema in-memory DuckDB case runs actual public reads through
the daily adapter, fitted synthetic HAR, signal, fixture contracts, sizing
and a funded hedge. `git diff --check` is also part of the release checks.

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p "test_*.py" -q
git diff --check
```

The briefing was rendered and all 12 pages visually reviewed when created.
It records the pre-publication development snapshot; these release notes and
Git history supersede its local/uncommitted status wording.

## Remaining dependencies and limits

Production contract/spot/Greeks/funding adapters, historical chains or explicitly
model-priced reconstruction, point-in-time HAR training, validated exchange
sessions and proxy policies remain. Portfolio/Execution must implement actual
cash reservations, strategy/group persistence, cancellation acknowledgements,
protected multi-leg transitions and assignment/dividend handling. The current
trading schema does not yet persist the required group/strategy ledger.

The engine/allocator, combined Risk implementation, Reserve sleeve and the
regime model's documented stuck-state problem remain separate team work.
Gross funding reserves are not maximum loss; short-volatility exposure still
needs stress and margin controls. The tests do not establish historical P&L,
liquidity, profitability or live readiness.

## Further documentation

- [Jacob's running progress](JACOB_PROGRESS.md)
- [Target integration contracts and policies](SLEEVE_TARGET_INTEGRATION.md)
- [Project manager and lead briefing](output/pdf/Jacob_Equity_and_Volatility_Sleeve_Briefing.pdf)
- [Team sprint tracker](SPRINTS.md)

The release excludes personal `.vscode` settings, virtual environments,
temporary report-generation/QA assets, local databases and credentials.
