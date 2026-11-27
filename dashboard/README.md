# Regent dashboard (mock-up)

Home page from `Docs/design/regent_home.dc.html` + `regent_growth_box.dc.html`, filled with real run data.
Quarantined: everything lives in this folder, opens both databases read-only, imports no strategy code.

```
# 1. export data --> dashboard/public/data/*.json   (also runs tests/system_check.py, ~1 min)
.venv/Scripts/python.exe dashboard/export_data.py               # add --no-checks to skip the check
# 2. view
cd dashboard && npm install && npm run dev
```

Re-run step 1 after every new backtest. Only finished `backtest_*` runs show in the dropdown.

Rules picked for the mock-up (constants at the top of `export_data.py`):
- MOOD event = the most likely mood changes; a mood that flips back within 5 days is shown once as a "blip"
- REBAL event = a sleeve weight moves 10+ pts in a day (skipped if a MOOD event is on the same day)
- Sharpe = daily excess return over the 3m T-bill (`tbill_3m`), annualised with √252
- Capital Now = weekly target weights from Jan 1 of last year to the run's end
- Growth box $ levels and milestones scale to each run (every 1× of starting cash)
