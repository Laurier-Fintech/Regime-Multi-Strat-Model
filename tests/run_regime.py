"""Runs the regime engine on real data and saves it to trading.duckdb (20+ minutes from 1995):

    .venv/Scripts/python.exe tests/run_regime.py

Then paste the printed run_id into Config/backtest.yaml as regime_run_id.
Also prints how "stressed" each crisis year was and saves a chart to Docs/output/charts/
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))     # repo root, so imports work

import matplotlib
matplotlib.use("Agg")       # save to file, no window
import matplotlib.pyplot as plt

from Config.settings import load
from Data.DataBase.access import get_prices
from Data.DataBase.db import REPO_ROOT
from ModelHome.RegimeHMM.regime_store import load_regime_probs, save_regime_run

SETTINGS = load("model.yaml", "regime_model")
MOODS = load("model.yaml", "moods")
CHARTS_DIR = REPO_ROOT / load("configs.yaml", "output")["charts_dir"]


def stressed_by_year(probs):
    """Average and peak P(stressed) in each crisis year --> does stressed light up?"""
    stressed = probs["stressed-bull"] + probs["stressed-bear"]
    print("\nyear   avg stressed   peak   lit up?")
    for year in SETTINGS["stressed_years"]:
        that_year = stressed[stressed.index.year == year]
        if that_year.empty:
            print(f"{year}   (no output yet, regime still warming up)")
            continue
        lit = "yes" if that_year.max() > 0.5 else "NO"
        print(f"{year}   {that_year.mean():12.0%}   {that_year.max():4.0%}   {lit}")

    # stuck states: long stretches with stressed above 99%
    stuck = (stressed > 0.99).astype(int)
    longest = (stuck.groupby((stuck != stuck.shift()).cumsum()).cumsum()).max()
    print(f"\nlongest run of stressed > 99%: {longest} trading days (very long = stuck state)")


def chart(probs, run_id):
    """The 4 moods stacked over time, saved as a PNG"""
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.stackplot(probs.index, [probs[m] for m in MOODS], labels=MOODS, alpha=0.85)
    ax.set_title(f"Regime moods ({run_id})")
    ax.set_ylabel("probability")
    ax.set_ylim(0, 1)
    ax.legend(loc="upper left", ncol=4)
    path = CHARTS_DIR / f"{run_id}.png"
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return path


if __name__ == "__main__":
    start = SETTINGS["run_start"]
    end = get_prices("spy", "2000-01-01", as_of=time.strftime("%Y-%m-%d")).index[-1].date()   # latest data

    print(f"running the regime {start} --> {end} (20+ minutes)...")
    t = time.time()
    run_id = save_regime_run(start, end, notes="tests/run_regime.py")
    print(f"done in {(time.time() - t) / 60:.1f} min")

    probs = load_regime_probs(run_id)
    stressed_by_year(probs)
    print(f"\nchart: {chart(probs, run_id)}")
    print(f"\nrun_id: {run_id}  --> paste into Config/backtest.yaml as regime_run_id")
