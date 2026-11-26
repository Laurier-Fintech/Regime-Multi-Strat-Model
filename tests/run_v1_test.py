"""The full v1.0 test: a backtest with sleeves OFF (Config/backtest.yaml), then checks + a report:

    .venv/Scripts/python.exe tests/run_v1_test.py                  # uses regime_run_id from backtest.yaml
    .venv/Scripts/python.exe tests/run_v1_test.py regime_2026...   # or a saved regime run you name

Needs a saved regime run first (tests/run_regime.py). Saves a NAV vs SPY chart to Docs/output/charts/
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))     # repo root, so imports work

import matplotlib
matplotlib.use("Agg")       # save to file, no window
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from Backtesting.run_backtest import run_backtest
from Config.settings import load, sleeves
from Data.DataBase.access import get_prices, get_series, get_trading_records, get_versions
from Data.DataBase.db import REPO_ROOT

CHARTS_DIR = REPO_ROOT / load("configs.yaml", "output")["charts_dir"]
TRADING_DAYS = load("configs.yaml", "trading_days_per_year")


def _replay(fills, start, end):
    """Every fill and split in date order --> what we should hold at the end

    A split changes shares without a fill (vixy 1-for-4: shares x 0.25), so a plain sum of fills won't match.
    Splits go first on their day, like the engine does them at the start of the day
    """
    ids = sorted(fills["instrument_id"].unique())
    splits = get_versions("splits", ids, start, end, as_of=end)
    events = [(pd.Timestamp(r.obs_date), 0, r.series_id, r.value) for r in splits.itertuples()]
    events += [(pd.Timestamp(r.as_of), 1, r.instrument_id, r.quantity) for r in fills.itertuples()]
    held = {}
    for day, kind, sid, amount in sorted(events):
        if kind == 0:
            held[sid] = held.get(sid, 0.0) * amount     # split
        else:
            held[sid] = held.get(sid, 0.0) + amount     # fill
    held = pd.Series(held, dtype=float)
    return held[held.abs() > 1e-6]                    # fully closed --> not in positions


def checks(rid, start_cash):
    """PASS / FAIL on the bookkeeping. Return: number failed"""
    nav = get_trading_records("nav", rid)
    total = nav[nav["sleeve"] == "total"].sort_values("as_of")
    alloc = get_trading_records("allocations", rid)
    positions = get_trading_records("positions", rid)
    fills = get_trading_records("fills", rid)
    cash = get_trading_records("cash_ledger", rid)
    events = get_trading_records("risk_events", rid)

    last = total["as_of"].max()
    final_held = positions[positions["as_of"] == last].groupby("instrument_id")["quantity"].sum()
    replayed = _replay(fills, total["as_of"].min(), last)
    weights_per_day = alloc.groupby("as_of")["target_weight"].sum()
    end_value = total["nav"].iloc[-1]
    covid = events[(pd.to_datetime(events["as_of"]) >= "2020-02-01") & (pd.to_datetime(events["as_of"]) <= "2020-03-31")]

    results = {
        "weights add up to 1, none below 0": np.allclose(weights_per_day, 1) and (alloc["target_weight"] >= -1e-12).all(),
        "NAV = cash + holdings (last day)": abs(end_value - (cash["amount"].sum() + positions[positions["as_of"] == last]["market_value"].sum())) < 0.01,
        "positions = fills (+ splits) replayed": final_held.sort_index().round(6).equals(replayed.sort_index().round(6)),
        "daily P&L adds up to the NAV change": abs(total["pnl_day"].sum() - (end_value - start_cash)) < 0.01,
        "every fill paid commission": (fills["commission"] > 0).all(),
        "NAV never below 0": (total["nav"] > 0).all(),
        "breaker fired in the Covid crash": len(covid) > 0,
    }
    print("\nchecks")
    for name, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    return sum(not ok for ok in results.values())


def report(rid, start_cash):
    """Our NAV vs SPY buy-and-hold: return, vol, worst drop, turnover. Saves the chart"""
    nav = get_trading_records("nav", rid)
    total = nav[nav["sleeve"] == "total"].sort_values("as_of").set_index("as_of")["nav"]
    total.index = pd.to_datetime(total.index)

    # SPY buy-and-hold with the same starting money (total_return includes dividends)
    spy_ret = get_prices("spy", total.index[0], total.index[-1], as_of=total.index[-1], field="total_return")["spy"]
    spy = start_cash * (1 + spy_ret.reindex(total.index).fillna(0)).cumprod()

    fills = get_trading_records("fills", rid)
    traded = (fills["quantity"].abs() * fills["price"]).sum()
    years = len(total) / TRADING_DAYS

    # risk-free = the T-bill rate (percent, yearly) --> a daily return, for Sharpe / Sortino
    tbill = get_series("tbill_3m", total.index[0], total.index[-1], as_of=total.index[-1])["tbill_3m"]
    risk_free = (tbill.reindex(total.index).ffill().bfill() / 100 / TRADING_DAYS).iloc[1:]

    print(f"\nreport ({total.index[0].date()} --> {total.index[-1].date()})")
    print(f"{'':22}{'v1.0':>10}{'SPY':>10}")
    rows = []
    for series in [total, spy]:
        daily = series.pct_change().dropna()
        excess = daily - risk_free.values
        downside = excess.clip(upper=0)
        rows.append({
            "total return": series.iloc[-1] / series.iloc[0] - 1,
            "yearly return": (series.iloc[-1] / series.iloc[0]) ** (1 / years) - 1,
            "yearly vol": daily.std() * np.sqrt(TRADING_DAYS),
            "worst drop": (series / series.cummax() - 1).min(),
            # return above T-bills per unit of risk (all ups and downs / only the downs)
            "sharpe": excess.mean() / excess.std() * np.sqrt(TRADING_DAYS),
            "sortino": excess.mean() / np.sqrt((downside ** 2).mean()) * np.sqrt(TRADING_DAYS),
        })
    for key in rows[0]:
        fmt = ".2f" if key in ("sharpe", "sortino") else ".1%"
        print(f"{key:22}{rows[0][key]:10{fmt}}{rows[1][key]:10{fmt}}")
    print(f"{'turnover per year':22}{traded / total.mean() / years:10.1f}x")
    print(f"{'trades':22}{len(fills):10d}")

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(total.index, total, label="v1.0 (sleeves off)")
    ax.plot(spy.index, spy, label="SPY buy-and-hold", alpha=0.7)
    ax.set_title(f"v1.0 NAV vs SPY ({rid})")
    ax.set_ylabel("$")
    ax.legend()
    path = CHARTS_DIR / f"{rid}.png"
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"\nchart: {path}")
    print(f"chart: {allocation_chart(rid)}")


def allocation_chart(rid):
    """Each sleeve's weight over time (stacked), black marks on the days the VIX breaker fired"""
    alloc = get_trading_records("allocations", rid)
    weights = alloc.pivot(index="as_of", columns="sleeve", values="target_weight")
    weights.index = pd.to_datetime(weights.index)
    weights = weights[[s for s in sleeves() if s in weights.columns]]
    events = get_trading_records("risk_events", rid)
    fired = sorted(pd.to_datetime(events.loc[events["rule"] == "vix_circuit_breaker", "as_of"].unique()))

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.stackplot(weights.index, [weights[s] for s in weights.columns], labels=list(weights.columns), alpha=0.85)
    for day in fired:
        ax.axvline(day, color="black", alpha=0.25, linewidth=1)
    ax.plot([], [], color="black", alpha=0.5, label="VIX breaker on")   # legend entry for the black marks
    ax.set_title(f"v1.0 sleeve weights ({rid})")
    ax.set_ylabel("share of NAV")
    ax.set_ylim(0, 1)
    ax.legend(loc="upper left", ncol=5)
    path = CHARTS_DIR / f"{rid}_allocations.png"
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return path


if __name__ == "__main__":
    settings = load("backtest.yaml")
    if settings["run"]["sleeves_on"]:
        sys.exit("v1.0 is sleeves OFF: set sleeves_on: false in Config/backtest.yaml")
    if len(sys.argv) > 1:
        settings["run"]["regime_run_id"] = sys.argv[1]
    if not settings["run"]["regime_run_id"]:
        sys.exit("No regime_run_id: run tests/run_regime.py first, then paste its run_id into Config/backtest.yaml")

    print(f"backtest {settings['run']['start']} --> {settings['run']['end']}, regime run {settings['run']['regime_run_id']}...")
    rid = run_backtest(settings, notes="tests/run_v1_test.py")
    print(f"run_id: {rid}")

    start_cash = settings["run"]["starting_cash"]
    failed = checks(rid, start_cash)
    report(rid, start_cash)
    print("\nv1.0 PASSED" if failed == 0 else f"\nv1.0 FAILED ({failed} checks)")
    sys.exit(1 if failed else 0)
