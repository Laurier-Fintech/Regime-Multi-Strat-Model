# Jacob's implementation progress

Last updated: 2026-11-23 (America/Toronto).

This is the running record of Jacob's sleeve work: what changed, why it was
needed, what was checked and what remains. Update it after each completed
implementation task. Implementation and successful unit tests do not imply
that a strategy is ready for trading or has demonstrated performance.

## Current position

Working branch: `jacob/dev`; release base: main commit `13fac5a`.
The original sleeve foundation is already in main (`4f90c28`). Tasks 1-5 below
are packaged in the sleeve implementation release described in
[the 2026-11-23 release notes](SLEEVE_RELEASE_2026-11-23.md). That release
publishes the same tested commit to `jacob/dev` and `main` using normal
fast-forward updates. The sprint tracker separates implemented components
from unfinished production integration and historical validation.

| Component | Current status |
|---|---|
| Shared sleeve interface | Implemented; complete desired holdings remain the output contract. |
| Shared four-state regime input | Implemented and tested locally. |
| Shared option pricing and Greeks | Implemented and tested locally, with documented model limits. |
| HAR-style volatility forecast | Implemented baseline from the original foundation; historical fitting/data adapter still needed. |
| Equity wheel state and decisions | Implemented and tested locally; Portfolio/Execution still own fills and assignment. |
| Calm-premium and stress-spread builders | Implemented and tested locally; exact contracts, coverage, cash collateral and gross funding checks. |
| Volatility signal and database adapter | Implemented and tested locally; explicit proxy/session assumptions are required. |
| Volatility structures and hedger | Implemented and tested locally; exact forecast expiry, whole lots, factor hedges and combined funding. |
| Equity/volatility sleeve orchestration | Both complete-target pipelines implemented and tested with supplied adapters. |
| Shared targeting inputs and funding | Implemented; explicit point-in-time market/capital/contract adapters remain necessary. |
| Session calendar | Explicit date-list utility implemented; an independent exchange schedule must be supplied. |
| Contract master, Portfolio/equity data adapters, historical chains | Integration work remains. |
| Reserve sleeve | Planned in the team sprint tracker. |

## Foundation and main synchronization

The original contribution created the shared sleeve context and target records,
the working HAR-style variance forecasting baseline and the A/B component
skeletons (13 Python files). Commit: `4f90c28`, already pushed to main.
The interfaces keep desired positions separate from orders, confirmed fills
and assignment accounting. Synthetic HAR checks were run; they were not a
historical performance backtest or a committed test suite.

On 2026-11-23, fetched four newer commits and fast-forwarded local main and
`jacob/dev` to `13fac5a`, leaving the working checkout on `jacob/dev`. No merge
conflicts occurred. The updates brought Bloomberg CSV exports, database/import
work, the HMM regime model and the Docs/sprint structure. Existing sleeve code
was unchanged by that update. Local DuckDB files were not created or populated.

## Task 1: shared regime inputs — implemented locally

Completed: 2026-11-23.

Changed `Sleeves/regime_inputs.py`, `Sleeves/base_sleeve.py`, the equity
configuration and related interface comments/READMEs. Added
`tests/test_regime_inputs.py`.

The context now requires the model's four joint probabilities: `calm-bull`,
`calm-bear`, `stressed-bull` and `stressed-bear`. It validates their values and
total, normalizes only tiny rounding error within 1e-8, and exposes immutable
joint values plus calm/stressed and bull/bear totals. All four joint states
remain available; the totals do not replace direction information.

This gives both sleeves the same input definitions. Removed the equity
configuration's old `calm_regime` / `stress_regime` arguments, which assumed
different labels. The future dispatcher must convert the model's pandas
Series with `.to_dict()` and handle its `None` warm-up result explicitly.

Verification at completion: 18 unit tests passed. Covers probability arithmetic,
invalid/missing inputs, rounding, immutable snapshots and configuration
migration. No live regime-model or historical strategy test was performed.

## Task 2: shared option pricing and Greeks — implemented locally

Completed: 2026-11-23.

Added `Common/__init__.py`, `Common/option_pricing.py`, `Common/greeks.py`,
`tests/test_option_pricing.py` and `tests/test_greeks.py`. Updated Common and
both sleeve READMEs with model selection, units, usage and limitations.

Implemented Black-Scholes-Merton for European spot options, Black-76 for
European futures options and a CRR tree for European/American spot options.
Added delta, gamma, vega, theta and rho, with explicit reporting units, plus
conversion to cash delta using a supplied multiplier and FX rate.

The equity builders can use these tools to value wheel/spread contracts.
The volatility sleeve can use the same calculations for structures and
hedging. The tree supports exercise on its grid but uses continuous dividend
yield; actual cash-dividend dates, exercise/assignment simulation, adjusted
deliverable baskets, fills and fees remain separate work.

Verification at completion: 35 new tests plus the 18 regime tests, 53 total,
passed. Checks include reference prices, parity/bounds, independent Greek
price bumps, early exercise, convergence and boundary/error handling. The
Common README example was executed successfully. No historical backtest.

## Task 3: TQQQ wheel state and decision rules — implemented locally

Completed: 2026-11-23.

Implemented `Sleeves/EquitySleeve/wheel.py`, updated the equity entry-point
integration notes and README, and added `tests/test_wheel.py`. Added this log
and links to it from the project documentation.

`inspect()` derives flat, short-put, share-holding, covered-call or mixed state
from confirmed, strategy-attributed holdings. Mixed state supports partial
assignment. Events are already applied by Portfolio and are not applied again.
Open orders remain separate from filled inventory. Call coverage reserves
confirmed shares against held/pending short calls and pending share sales;
planned share purchases and call buybacks do not release/create coverage.
Actual pure-share deliverables are used instead of assuming every lot is 100.

`plan()` applies an explicit baseline:

- Stress exit has priority, followed by a zero capital budget.
- Pending orders pause entries until execution confirms their outcome.
- New puts require a flat wheel, positive available cash, the calm gate and a
  separate calm-bull gate. The direction distinction therefore affects entries.
- Covered calls require the calm gate and confirmed unreserved shares.
- Failing an entry gate preserves existing inventory unless an exit condition
  separately applies. Existing short puts are not automatically scaled up.
- Exit plans identify wheel entry orders to cancel, while preserving existing
  risk-reducing orders and other strategies' orders.

Thresholds are required configuration inputs; test/example values are not
production calibration. Both stress directions trigger the defensive wheel
exit; this does not define the separate bearish index-spread policy.
`plan(context, state)` replaces the old duplicate probability keyword inputs.

Verification at completion: 40 new wheel tests plus the previous 53, **93 total**,
passed. Covers partial fills/assignment, direction-sensitive entries, gates,
open-order reservations, cross-strategy coverage, cutoff/metadata validation,
unsupported exposure and immutable/repeatable decisions. No broker calls,
real option-chain test or historical performance backtest was performed.

## Task 4: volatility signal and database adapter — implemented locally

Completed: 2026-11-23.

Implemented `Sleeves/VolSleeve/signal.py` and added `market_data.py` plus the
explicit `Common/calendar.py` session utility. Added optional provenance to
`RVInputs`. Extended `Data/DataBase/access.py` with optional metadata output
for features, IV and chains, preserving the default output shapes and existing
as-of/version rules. Updated volatility, database and Common documentation.

The signal validates market, horizon, decision time, availability and age. It
returns short volatility for sufficiently rich IV, long volatility for
sufficiently cheap IV and neutral within the band. A configurable total-stress
gate vetoes the short proposal, without forcing a long trade. Both stress
directions count for this movement-size policy. Thresholds are research
configuration inputs, not calibrated production settings.

The adapter reads only through the public database API and retains source and
availability metadata. It requires an acknowledged proxy if RV/IV source
underlyings differ from the logical market. It rejects missing/misaligned
features, stale observations, future versions and ambiguous sources. It maps
the next H supplied exchange sessions to a calendar end date and interpolates
ATM total variance to that future window. Older allowed observations are
forward-window adjusted without resetting their age. No horizon-end
extrapolation is allowed; the zero-to-first-tenor anchor for a forward start is
an explicit flat-front-volatility assumption.

The adapter can read and validate actual option chains. It does not reconstruct
contracts from the Bloomberg grids. Those grids remain distinct from a tradable
historical chain. No forecasts are silently trained, no orders are generated
and the full sleeve remains unfinished.

Verification at completion: **43 new tests plus the previous 93, 136 total**,
passed. Coverage includes signal policy, source identity, metadata/cutoffs,
calendar holidays/DST age checks, interpolation, stale-quote forward adjustment, bad/missing
inputs and actual quotes. Real DuckDB integration tests load the production
schema into an in-memory database, verify legacy API compatibility and exclude
future revisions. One case fits HAR to synthetic outcomes and runs real-reader
inputs through forecast and signal. No historical performance backtest or live
market database refresh was performed.

The volatility README configuration example was also executed against the
in-memory production schema. Python syntax and whitespace checks passed.

Created the git-ignored `.venv`, reused the existing NumPy 2.5.2 and installed
the repository-pinned pandas 3.0.6, DuckDB 1.5.6 and PyYAML 6.0.3 there for
integration tests. Global packages and requirements.txt are unchanged.

Remaining limits: a real exchange schedule and conservative daily availability
convention must be supplied. Database metadata is DATE precision, so timestamp
conversion is an assumption and cannot certify intraday release timing. Proxy
equivalence, historical HAR training, actual chain coverage and downstream
neutral-signal hold/unwind behavior still require validation/integration.

## Task 5: contract selection, sizing and full sleeve targets — implemented locally

Completed: 2026-11-23.

Implemented `calm_premium.py`, `stress_put_spreads.py`, `structures.py`,
`delta_hedge.py` and both sleeve `generate_targets()` methods. Added
`Common/targeting.py`, extended canonical equity metadata and exposed the
wheel's read-only strategy/instrument dependencies. Added
`tests/test_sleeve_targeting.py`, updated obsolete skeleton assertions in
`test_regime_inputs.py`, and extended the production-schema database test
through funded option and hedge targets.

**What changed and why:**

- Shared daily quote checks reject missing metadata, stale/future observations,
  mixed sources, ambiguous contracts and crossed/nonfinite quotes. Canonical
  resolution checks exact quoted terms and compatible settlement-series IDs;
  provider IDs are never assumed to be canonical IDs.
- The explicit `SelectionPolicy` supplies spread limits, base currency,
  timezone, fees and a maximum whole-lot count. Point-in-time market and capital
  snapshots are required. Gross reserves include each position sign's funding
  and costs; no margin offsets, FX or broker rules are invented.
- Wheel puts select the earliest eligible expiry and nearest OTM strike, with
  full strike-based assignment cash plus fees. Covered calls use actual share
  deliverables and preserve all confirmed shares. Existing groups survive hold
  decisions. Exits close calls before releasing their covering shares, using
  a later confirmed snapshot; allocation cuts and removed markets also unwind.
- Bearish put spreads select compatible same-expiry higher-strike long and
  lower-strike short puts, preserve equal whole quantities, check executable-
  side debit plus fees against width, and respect gross funding. The equity
  config now requires `stressed_bear_entry_probability`; stressed-bull alone
  cannot trigger bearish spreads. Inactive stress holdings target zero.
- Equity reserves desired retained holdings first and divides remaining budget
  and confirmed available cash once across eligible market/strategy routes.
  Pending orders raise `PendingOrdersError` with IDs and wheel entry-cancel
  intent instead of issuing a conflicting book. Unknown strategy attribution
  fails explicitly. Covered-call exits may temporarily retain shares above a
  reduced budget only as a strict reduction of confirmed holdings for Risk
  approval; they cannot add above-budget exposure.
- Volatility selects ATM straddles or strictly OTM strangles with exact quoted
  expiry equal to the session-aligned forecast end. Both legs retain one group
  and equal quantities. Neutral/removed markets and zero budgets target zero;
  missing data never becomes a neutral/flatten result.
- Delta hedging aggregates desired option sensitivities by factor, checks exact
  timestamp/currency/identity, rounds nearest whole unit with ties away from
  zero, and returns shared hedge groups. Each market's sizing includes hedge
  funding. The combined book is rehedged and checked; whole lots are removed
  deterministically if shared-factor rounding would overdraw the budget.

**How this connects to the product:** both sleeves now produce complete desired
books from the shared regime context and valid read-only inputs. This finishes
their internal target pipeline. The engine can pass those books to Risk and
Portfolio once the team's adapters and execution layers exist. It does not
create broker orders, fill records, a contract database or assignment events.

**Verification:** all **187 tests passed** in the project `.venv` (previously
136). There are 50 new selection/funding/hedge/pipeline checks and one additional
regime/config regression check. The existing DuckDB integration case now runs
real public access queries against an in-memory production schema, fits HAR to
synthetic historical outcomes, selects canonical fixture contracts and returns
two option legs plus a funded hedge. Tests cover quote rejection, exact expiry,
non-100 multipliers, whole lots, cash sharing, actual deliverable coverage,
confirmed wheel transitions, retained put collateral, invalid non-flat put
entry plans, staged exits, reduced allocations, pending work,
directional stressed states, hedge rounding and error propagation. Whitespace
checks passed. These are synthetic correctness tests, not performance results.

Documentation: added [the target integration guide](SLEEVE_TARGET_INTEGRATION.md)
covering signatures, required inputs, policies, capital formulas, attribution,
error handling, execution sequencing and remaining limits. Updated both sleeve
READMEs, shared sleeve/Common READMEs and the Docs index. No database schemas,
live data or broker accounts changed. This task was initially completed
locally; its code and documentation are included in the implementation release
recorded below.

## Project manager and lead briefing

Prepared: 2026-11-23.

Created a [12-page sleeve implementation briefing](output/pdf/Jacob_Equity_and_Volatility_Sleeve_Briefing.pdf)
covering the original foundation and Tasks 1-5, what each change contributes,
the shared architecture and four-state regime distinction, pricing/Greeks,
HAR training and data alignment, volatility selection/sizing/hedging, confirmed
wheel state and staged exits, bearish spreads, file locations, verification
and the remaining integration and validation work. Includes illustrative
numerical examples and a concise project-meeting explanation.

Reviewed the report against the current implementation, progress log and sprint
tracker. Rendered and visually inspected all 12 PDF pages; checked page count
and extracted text. This was a documentation task: algorithms and tests were
unchanged, and the previously recorded 187-test result was not rerun. The
briefing distinguishes local implementation from merged delivery and full
system readiness. The Word renderer was unavailable in this Windows runtime,
so the shareable deliverable is a verified PDF.

## Main synchronization and sleeve implementation release

Prepared: 2026-11-23, following Jacob's instruction to synchronize the branch
and publish the updates to main if conflict-free.

Fetched origin and compared committed history: `jacob/dev` HEAD and
`origin/main` were both `13fac5adebb778946d013094a39d8ce822ef0767`
(zero commits ahead/behind). There were no new main updates to merge and
no unresolved merge conflicts. The remote `jacob/dev` was still at `0970a38`;
the release advances it together with main.

Reran the complete suite: **187 tests passed**. Reviewed and explicitly
selected the implementation, tests, repository documentation and briefing PDF.
Personal `.vscode/settings.json` remains local. The virtual environment,
temporary report-generation/QA files and database files are excluded.
Declared the already-tested NumPy 2.5.2 dependency explicitly in requirements
so the HAR/HMM numerical dependency is not merely transitive through pandas.

Added the release notes, linked them from the Docs index, and updated the
sprint tracker to distinguish the delivered internal components from pending
Portfolio/execution/data connections. The briefing PDF is retained as the
dated explanation prepared before publication; its original local/uncommitted
status statements are historical. This release record and Git history carry
the current delivery status.

Publication uses a normal atomic push of the same commit to `origin/main`
and `origin/jacob/dev`, with no force update. A concurrent incompatible main
change is rejected rather than overwritten and requires a fresh comparison.
The final remote branch hashes must be verified after publication.

## Remaining work and dependencies

Next, supply the production adapters and actual/model-priced option-chain
connections so the completed pipelines can run against point-in-time data:

1. Validate any chosen SPY/SPX or QQQ/NDX research proxies, supply an independent
   exchange schedule and daily cutoff, and prepare point-in-time HAR training
   with the same source/window convention. No implicit proxy is used.
2. Build the shared contract master and remaining market/Portfolio adapters.
   Bloomberg grids are not historical contract chains. Reconstructed quotes
   must be explicitly model-priced.
3. Connect canonical resolution, point-in-time underlying valuations, shared
   Greeks-to-cash-delta inputs and explicit broker/research funding reserves.
   Supply complete settlement-series specifications and supported deliverables.
4. Wire the completed sleeve target pipelines into the allocator/engine and
   combined Risk checks. Configure/validate expiry-aligned forecast windows,
   spread/fee/lot policies, probabilities and absolute hedge-residual limits.
5. Connect cancellation/exit sequencing to Portfolio/Execution. Snapshot
   coverage is scoped to the equity sleeve; Portfolio/Risk must also reserve
   any shares encumbered outside it. Strategy/group attribution is not yet
   persisted by the trading schema and requires coordination with its owner.
6. Complete historical backtest wiring, exercise/assignment/dividend handling,
   realistic costs and out-of-sample checks before performance claims.

Team dependencies still include the regime model's documented stuck-state
issue and unfinished allocator/engine. These do not block isolated sleeve
tests with supplied valid inputs, but do block a complete system evaluation.

## Re-running checks

From the repository root, with the project's Python interpreter:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p "test_*.py" -v
git diff --check
```

The 187-test suite includes pandas/NumPy/DuckDB integration tests and needs
the project environment's dependencies. Test data is synthetic and the DuckDB
fixtures are in-memory; no local market database, download or broker is needed.
For each future update, record files, purpose, verification and remaining
limits here, and update the current-status table as components are completed.
