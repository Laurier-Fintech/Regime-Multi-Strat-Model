# Stuck states diagnosis — progress log

Open this any time to see where it's at. Charts are in `Docs/output/diagnosis/` (`raw_*.png`, `z_*.png`).

| Step | Status |
|---|---|
| 1. Fit each of the 5 features alone (raw levels) | ✅ done |
| 2. Fit each full model (stress, direction) | ✅ done |
| 3. Same fits with the z-score idea (level features only) | ✅ done |
| 4. Results + what to do next | ✅ done, waiting for Armaan's OK |

## Found (raw levels)
- **Direction culprit = `curve_slope`.** Alone it's "steep" 99%+ for 2,092 days straight (2008 → 2015). The direction
  model reads steep curve = bear, so it says bear 2008–2015 even though `trend_spy` alone says bull 2010–2014.
- **Stress culprit = `credit_spread` level.** Alone it's stressed 804 days straight (Nov 2007 → 2010) and 100% in 2012.
  `log_vix` and `credit_spread_chg_20d` behave (VIX's long run is the real 2008–09 crisis).

## Results with z-scores (fit through 2011, then run forward, like the real walk-forward)
| | longest stuck run | verdict |
|---|---|---|
| STRESS model, raw | 2008–2010 at 100% | stuck |
| STRESS model, z-scored levels | 249 days (the real 2008 crisis) | **fixed** |
| DIRECTION model, raw | bear 2008 → 2015 | stuck |
| DIRECTION model, z-scored | better 2010–2017, but wrong in 2020 / 2024 | not fixed |
| `trend_spy` alone | bull 2010–2018 and 2024, bear 2001 and 2008, mixed 2022 | best direction signal |

`curve_slope` is the real direction problem, even z-scored: when the curve un-inverts (2024) it reads that as bear.

## Recommended next step (needs Armaan's OK, no project code changed yet)
1. Stress: z-score the level features (`log_vix`, `credit_spread`). A setting in model.yaml.
2. Direction: drop `curve_slope`, use `trend_spy` only.
3. One full walk-forward regime run (~20 min) to confirm, then rerun the v1 test.

## Catches seen
- z-scored stress fades in long crises: 2009 averages 0.55 even though the crisis ran into early 2009.
- z-scores need a year of daily data, so the stress model's first output moves later (~2004). The backtest starts 2008, so fine.

## Notes
- The diagnosis script lives outside the repo. These are one fit per feature (seconds each), not the 20-min daily run.

## Implemented (2026-11-26, after Armaan's OK)
- `Config/model.yaml`: `zscore_features: [log_vix, credit_spread]`, `zscore_window: 252`, `direction_features: [trend_spy]`.
- Quick check (2010-06 → 2013 run): calm-bull 2010 and 2013, stressed 40% in 2011, no more "bear 2008–2015".
- Next: Armaan runs `tests/run_regime.py` (full 1995 run) and `tests/run_v1_test.py`.
