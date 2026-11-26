# Regime-Multi-Strat-Model
LTG Quant: Regime-Driven Multi-Strategy Derivatives Portfolio (Laurier Trading Group / Laurier Fintech).

## Where we are
- **v1.0 is done (Sprint 2, closed 2026-11-26).** The full system runs end to end with the sleeves **off**: regime → allocator →
  VIX breaker → stand-in ETFs → Portfolio → simulated broker → `trading.duckdb`.
- **First result (2008 → 2026-11, sleeves off):** 8.4% a year at 9.8% vol, worst drop −15.8%, Sharpe 0.72
  (SPY: 11.2%, 19.7%, −51.9%, Sharpe 0.56). Lower return, much lower risk. Mood mixes are still hand-set placeholders.
- **Next: Sprint 3 / v2.0** = sleeves **on** (Jacob's option sleeves), learned mood mixes, tuning. See [Docs/SPRINTS.md](Docs/SPRINTS.md).

## Run it
```
python Data/DataBase/setup_run_once/create_databases.py   # once per computer (then copy market_data.duckdb from OneDrive)
python tests/system_check.py      # seconds: do all the pieces work? --> READY TO GO
python tests/run_regime.py        # ~20 min: run the regime from 1995, save it, print its run_id
                                  #   --> paste the run_id into Config/backtest.yaml under run: regime_run_id
python tests/run_v1_test.py       # ~5 min: full v1.0 backtest, 7 checks, report vs SPY, charts in Docs/output/charts/
```
Use `.venv/Scripts/python.exe`. Every setting is in [Config/](Config/), not in the code.

## Docs
- Project documents (white paper, reference paper, database diagrams, sprint tracker): [Docs/](Docs/).
- Jacob's sleeve implementation history and progress: [Docs/JACOB_PROGRESS.md](Docs/JACOB_PROGRESS.md).
- Every folder has its own README explaining its job and what's built.
