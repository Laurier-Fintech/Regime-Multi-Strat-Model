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

## Sprint 2: working system v1.0

### Graydon: finish the regime and allocations
- [ ] Run the regime on real data from 1995
- [ ] **Fix stuck states** (see below)
- [ ] Check stressed lights up in 1998, 2001, 2008, 2011, 2020, 2022
- [ ] Allocator: mood mixes, blend by probability, smoothing
- [ ] VIX circuit breaker (moves weight to the reserve on a VIX jump)
- [ ] Output allocations, then test them on base ETFs with sleeves off

### Jacob: options and sleeves
- [ ] Shared option pricer and greeks
- [ ] Sleeve 2: TQQQ wheel
- [ ] Reserve sleeve

### Armaan: backtest and wiring
- [ ] Backtest engine: positions, P&L, costs
- [ ] Wire everything together: version 1.0

### Data layer
- [ ] `write_regime_probs`: save daily regime output to `trading.duckdb`, so backtests reuse it instead of re-running the regime (a full regime run takes 20+ minutes)
- [ ] Fix the credit-spread fallback: use FRED only after Bloomberg's last date, then rebuild features

### Known problem: stuck states
In a 2005–2012 test run, stressed switched on in Q3 2007 (good) but stayed at 100% until 2011, and bear stayed at 100% through 2012. The model is likely splitting "before 2008" vs "after 2008", because feature levels (e.g. credit spread) sat higher after 2008 even on calm days. Try:
- changes, or levels relative to the last year, instead of raw levels
- a rolling training window (e.g. last 10 years) instead of all history
- fitting one feature at a time to find the cause

### Speed notes
- Live trading: a normal day takes ~0.05 s; a refit day (once a quarter) ~10–40 s.
- Full regime backtest from 1995: 20+ minutes. Save the output once (`write_regime_probs`) and reuse it.
- If still slow: refit twice a year, or use a rolling window.

---

## Sprint 3

- [ ] Sleeve 3: spread sleeve
- [ ] Add `vix_term` back to the stress model once Bloomberg VIX3M history (2008) is loaded
- [ ] Clean implied-vol glitch cells (~107 candidates on 29 dates)
- [ ] Make publish-lag calculation skip holidays
- [ ] Live IBKR connection and paper trading
- [ ] Presentation to LTG
