# Sprint Tracker

What's done, what's next, and who owns it. Tick a box when it's merged into `main`.

---

## Sprint 1: foundations (closed 2026-11-15)

### Project setup
- [x] White paper and reference paper (Kritzman, Page & Turkington, "Regime Shifts")
- [x] Folder structure with a README in every folder explaining its job
- [x] Settings kept out of code; secrets only in the git-ignored `Config/.env`

### Data layer (Armaan)
- [x] Two DuckDB databases: `market_data.duckdb` (inputs) and `trading.duckdb` (run records)
- [x] As-of rule: every value has an `obs_date` and a `known_at`; reads never see the future
- [x] One-command refresh (`refresh.py`): FRED, CBOE, prices, Bloomberg exports, then features
- [x] Loaded: ~140k series rows, ~94k price rows, ~505k implied-vol rows, ~111k feature rows
- [x] 15 features built (curve slope, credit spread + 20-day change, log VIX, VIX term, 4 trend, 6 realised vol)
- [x] Test notebook `tests/test_database.ipynb`: coverage, integrity, as-of checks, charts
- [x] ER diagrams ([market_data](diagrams/er_market_data.png), [trading](diagrams/er_trading.png))

### Sleeves (Jacob)
- [x] Sleeve interfaces, HAR volatility baseline, Sleeve A and B skeletons

### Regime model skeleton (Armaan)
- [x] Layout decided: `ModelHome` decides what to hold; `Backtesting` is the plug-in fake broker; sleeves on/off switch
- [x] Two 2-state HMMs: stress (calm/stressed) and direction (bull/bear), combined into 4 moods
- [x] `regime_hmm.py`: the maths (fit, forward/backward, filter_step, filter_all), numpy only
- [x] `state_labels.py`: fixed state order after every refit
- [x] `regime_model.py`: reads features as of each day, quarterly refits with warm start, daily step
- [x] Tested on fake data (98% of days labelled right); wiring checked on real data

---

## Sprint 2: working system v1.0 (closed 2026-11-26)

v1.0 = the whole system running with the sleeves **off** (stand-in ETFs). Sleeves **on** is v2.0 (Sprint 3).

### Regime and allocations (Armaan, took over Graydon's part)
- [x] Run the regime on real data from 1995, saved to `trading.duckdb` and reused by every backtest (`regime_store.py`)
- [x] **Fixed stuck states.** Diagnosis ([Docs/output/diagnosis](output/diagnosis/stuck_states_progress.md)): the `credit_spread`
      level stuck stress on 2008–2010, the `curve_slope` level stuck direction on "bear" 2008–2015. Fix: `log_vix` and
      `credit_spread` go in as z-scores vs their last year; direction uses `trend_spy` only
- [x] Stressed lights up in 2008, 2011, 2020, 2022 (1998 / 2001 are before the z-scored model's first output, ~2004)
- [x] Allocator: hand-set mood mixes (`Config/model.yaml`), blended by probability, smoothing + no-trade band
- [x] VIX circuit breaker: VIX up 20%+ from 25+, or above 35 → vol sleeve weight to reserve, hold 5 days, rebuild over 10
- [x] Allocations tested on stand-in ETFs with sleeves off (`tests/run_v1_test.py`)

### Jacob: options and sleeves
- [x] Shared option pricer and greeks: Black-Scholes-Merton, Black-76 and CRR, with shared unit conventions and tests
- [x] Shared four-state sleeve context, quote validation and explicit gross funding checks
- [x] Equity wheel state, coverage, put/call selection, bearish spreads and complete desired targets
- [x] Volatility data/signal pipeline, structure selection, sizing, delta hedging and complete desired targets
- [ ] Moved to Sprint 3 (v2.0): wheel and volatility production integration, historical validation, reserve sleeve

Sleeve implementation details, breaking interface changes and verification are
recorded in [the 2026-11-23 release notes](SLEEVE_RELEASE_2026-11-23.md).

### Backtest and wiring (Armaan)
- [x] Portfolio: positions (sleeve / strategy / group slices), cash ledger, valuation (NAV + P&L), rebalancer, broker plug
- [x] Simulated broker: fills at the close + half-spread + slippage, IBKR-style commission
- [x] Engine (`ModelHome/engine.py`): the daily loop, sleeves on/off switch (on raises "not wired yet")
- [x] Speed-up: prices / VIX / T-bill / dividends / splits loaded once per run (`market_book.py`), full run ~5 min
- [x] Tests: `system_check.py` (12 checks, seconds), `run_regime.py`, `run_v1_test.py` (7 checks + report + charts)

### Data layer
- [x] `write_regime_probs` / `load_regime_probs` (`regime_store.py`), shared `runs` helper (`Data/DataBase/runs.py`)
- [x] Credit-spread fallback fixed: FRED only after Bloomberg's last date, features rebuilt
- [x] Every tunable number moved to `Config/*.yaml`, read through `Config/settings.py`
- [x] Trading schema v2: `strategy_id` + `group_id` on positions / target_positions / orders / fills
- [x] New data: CBOE PutWrite index (`putw_index`, vol stand-in in calm moods) and VIXY (`vixy`, in stressed moods)

### v1.0 result (2008-01-02 → 2026-11-11, sleeves off, all 7 checks pass)
| | v1.0 | SPY |
|---|---|---|
| Yearly return | 8.4% | 11.2% |
| Yearly vol | 9.8% | 19.7% |
| Worst drop | −15.8% | −51.9% |
| Sharpe / Sortino | 0.72 / 1.01 | 0.56 / 0.80 |
| Turnover | 4.2× a year | |

---

## Sprint 3: v2.0 (sleeves on) and tuning

### Sleeves on (v2.0)
- [ ] `Portfolio/snapshots.py`: Jacob's `EquityPortfolioSnapshot` from our positions / ledger (pseudocode written)
- [ ] `Portfolio/lifecycle.py`: option expiry and assignment for the wheel (pseudocode written)
- [ ] Simulated broker prices options from the implied-vol grid (`is_model_priced`), per-contract fees
- [ ] Engine: build `SleeveContext` per sleeve, collect targets, pass the whole book through RiskManagement
- [ ] Jacob: reserve sleeve, contract / funding / delta adapters, historical validation of both sleeves
- [ ] Sleeve 3: spread sleeve

### Tuning and model
- [ ] Learned mood mixes from sleeve stand-in returns per mood, with caps and a pull toward equal weights
- [ ] Tune placeholders (mixes, smoothing, band, breaker, costs). Don't fit them to 2008 / 2020 / 2022 specifically
- [ ] Turnover went 2.5× → 4.2× with z-scores: z-scores are relative, so a small VIX rise after a calm year reads "stressed"
- [ ] Add `vix_term` back to the stress model once Bloomberg VIX3M history (2008) is loaded
- [ ] `credit_spread_chg_20d` is a 20-*month* change in 1994–97 (Bloomberg monthly then); only matters for pre-2000 runs

### Data and live
- [ ] Clean implied-vol glitch cells (~107 candidates on 29 dates)
- [ ] Make publish-lag calculation skip holidays
- [ ] Live IBKR connection and paper trading
- [ ] Presentation to LTG
