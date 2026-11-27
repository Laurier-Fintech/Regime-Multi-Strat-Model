"""Dashboard export: reads trading.duckdb + market_data.duckdb (read-only) --> JSON in dashboard/public/data/

    .venv/Scripts/python.exe dashboard/export_data.py            # also runs tests/system_check.py (~1 min)
    .venv/Scripts/python.exe dashboard/export_data.py --no-checks

Never writes to the databases or anywhere outside dashboard/. Imports no strategy code.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "public" / "data"
TRADING_DB = ROOT / "Data" / "DataBase" / "trading.duckdb"
MARKET_DB = ROOT / "Data" / "DataBase" / "market_data.duckdb"
SYSTEM_CHECK = ROOT / "tests" / "system_check.py"

SLEEVES = ["reserve", "equity", "spread", "vol"]       # draw order, bottom --> top
PNL_ROWS = ["equity", "reserve", "spread", "vol", "total"]
STATES = ["stressed-bull", "stressed-bear", "calm-bull", "calm-bear"]
MOOD_HOLD_DAYS = 5          # a mood flip that reverts within 5 days is a "blip"
REBAL_MOVE = 0.10           # a sleeve weight moving 10+ pts in a day is a REBAL event
N_TRADES = 10
N_EVENTS = 3


def _q(con, sql, *args):
    return con.execute(sql, list(args)).df()


def _pct(v):
    """0.9985 --> '99.9%', 0 --> '0%'"""
    s = f"{v * 100:.1f}".rstrip("0").rstrip(".")
    return (s if s != "-0" else "0") + "%"


def run_system_check():
    """Run tests/system_check.py in its own process and parse its OK / FAIL lines"""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    started = datetime.now()
    p = subprocess.run([sys.executable, str(SYSTEM_CHECK)], cwd=str(ROOT), env=env,
                       capture_output=True, text=True, timeout=900)
    checks = []
    for line in p.stdout.splitlines():
        m = re.match(r"\s+(OK|FAIL)\s+(\w+)(?::\s*(.*))?", line)
        if m:
            checks.append({"name": m.group(2), "ok": m.group(1) == "OK", "error": m.group(3) or ""})
    if not checks:
        raise ValueError(f"system_check printed no results, stderr:\n{p.stderr[-2000:]}")
    return {"ran_at": started.strftime("%Y-%m-%d %H:%M"), "checks": checks}


def _spy_index(mcon, start, end):
    """SPY total-return index, 1.0 on the first day"""
    df = _q(mcon, "SELECT obs_date, total_return FROM clean.prices WHERE series_id = 'spy' "
                  "AND obs_date BETWEEN ? AND ? ORDER BY obs_date", start, end)
    s = pd.Series(df["total_return"].fillna(0).values, index=pd.to_datetime(df["obs_date"]))
    s.iloc[0] = 0.0
    return (1 + s).cumprod()


def _tbill_daily(mcon, start, end, index):
    """3m T-bill yield (%) --> daily rate, forward filled onto the NAV days"""
    df = _q(mcon, "SELECT obs_date, value FROM clean.series WHERE series_id = 'tbill_3m' "
                  "AND obs_date BETWEEN ? AND ? ORDER BY obs_date", start, end)
    s = pd.Series(df["value"].values, index=pd.to_datetime(df["obs_date"]))
    return (s.reindex(index.union(s.index)).ffill().reindex(index).fillna(0) / 100 / 252)


def _max_dd(s):
    return float((s / s.cummax() - 1).min())


def _mood_events(probs):
    """Dominant mood flips. A mood that lasts <= MOOD_HOLD_DAYS then flips back is one event:
    calm bull --> stressed bull (1 day) --> calm bull  ==>  '04-02 stressed bull to calm bull (one-day blip)'"""
    top = probs.idxmax(axis=1)
    flip_days = list(top[top != top.shift()].index[1:])
    events = []
    for k, day in enumerate(flip_days):
        old, new = top[top.index < day].iloc[-1], top[day]
        prev_flip = flip_days[k - 1] if k > 0 else None
        before_old = top[top.index < prev_flip].iloc[-1] if prev_flip is not None else None
        old_held = int(((top.index >= prev_flip) & (top.index < day)).sum()) if prev_flip is not None else 10**9
        next_flip = flip_days[k + 1] if k + 1 < len(flip_days) else None
        new_held = int(((top.index >= day) & (top.index < next_flip)).sum()) if next_flip is not None else 10**9
        if next_flip is not None and new_held <= MOOD_HOLD_DAYS and top[next_flip] == old:
            continue        # this flip is the start of a blip, reported when it flips back
        msg = f"{old.replace('-', ' ')} to {new.replace('-', ' ')}"
        if old_held <= MOOD_HOLD_DAYS and before_old == new:
            msg += " (one-day blip)" if old_held == 1 else f" ({old_held}-day blip)"
        events.append({"date": day, "kind": "MOOD", "state": new, "msg": msg})
    return events


def _rebal_events(alloc_w, fills, breaker_days):
    """Days a sleeve weight moved REBAL_MOVE+ --> biggest trade that day + why"""
    diff = alloc_w.diff()
    events = []
    for day, row in diff.iloc[1:].iterrows():
        big = row[row.abs() >= REBAL_MOVE]
        if big.empty:
            continue
        sleeve = big.abs().idxmax()
        day_fills = fills[(fills["as_of"] == day) & (fills["sleeve"] == sleeve)]
        if day_fills.empty:
            day_fills = fills[fills["as_of"] == day]
        if day_fills.empty:
            continue
        f = day_fills.loc[(day_fills["quantity"].abs() * day_fills["price"]).idxmax()]
        verb = "bought" if f["quantity"] > 0 else "sold"
        way = "up" if row[sleeve] > 0 else "down"
        msg = f"{verb} {abs(f['quantity']):,.0f} {f['instrument_id'].upper()}: {sleeve} {way} to {_pct(alloc_w.loc[day, sleeve])}"
        if day in breaker_days:
            msg += " as vol was cut"
        events.append({"date": day, "kind": "REBAL", "msg": msg})
    return events


def _breaker(events, last_day):
    """Banner: is the VIX breaker cutting on the last day, and when did this streak start"""
    if events.empty:
        return {"active": False, "text": "never triggered"}
    latest = events.iloc[-1]
    on_last = latest["as_of"] == last_day
    # last trigger = latest event where VIX jumped (later ones just keep the cut on)
    trig_row = latest
    for row in events.iloc[::-1].itertuples():
        if re.search(r"vix [\d.]+ \(\+?\d+%\)", row.detail or ""):       # "(+22%)" or "(22%)", not "(-10%)"
            trig_row = events.loc[row.Index]
            break
    moved = re.search(r"moved ([\d.]+%)", latest["detail"] or "")
    vix = re.search(r"vix ([\d.]+) \(([-+]?\d+)%\)", trig_row["detail"] or "")
    trig = trig_row["as_of"].strftime("%m-%d")
    if vix:
        jump = int(vix.group(2))
        how = f"a {abs(jump)}% {'jump' if jump > 0 else 'drop'}"
        trig += f", VIX {vix.group(1)} after {how}"
    sleeve = latest["sleeve"] or "vol"
    text = f"{sleeve} sleeve's {moved.group(1) if moved else '?'} parked in reserve · last trigger {trig}"
    if not on_last:
        text = f"clear · last trigger {trig}"
    return {"active": bool(on_last), "text": text}


def export_run(tcon, mcon, run, checks):
    rid = run["run_id"]
    cfg = json.loads(run["config_snapshot"] or "{}")
    cfg_run = cfg.get("run", {})

    nav = _q(tcon, "SELECT as_of, sleeve, nav, pnl_day FROM nav WHERE run_id = ? ORDER BY as_of", rid)
    nav["as_of"] = pd.to_datetime(nav["as_of"])
    total = nav[nav["sleeve"] == "total"].set_index("as_of")["nav"]
    pnl = nav.pivot_table(index="as_of", columns="sleeve", values="pnl_day", aggfunc="sum").fillna(0)
    for s in SLEEVES + ["total"]:
        if s not in pnl:
            pnl[s] = 0.0
    last_day = total.index[-1]
    start_cash = float(cfg_run.get("starting_cash") or total.iloc[0])

    # mood
    probs = _q(tcon, "SELECT as_of, state, probability FROM regime_probs WHERE run_id = ?", rid)
    probs["as_of"] = pd.to_datetime(probs["as_of"])
    probs = probs.pivot_table(index="as_of", columns="state", values="probability").reindex(columns=STATES).fillna(0)
    now_probs = probs.loc[:last_day].iloc[-1]

    # allocations (target weights)
    alloc = _q(tcon, "SELECT as_of, sleeve, target_weight FROM allocations WHERE run_id = ?", rid)
    alloc["as_of"] = pd.to_datetime(alloc["as_of"])
    alloc_w = alloc.pivot_table(index="as_of", columns="sleeve", values="target_weight").reindex(columns=SLEEVES).fillna(0)
    cap_start = pd.Timestamp(last_day.year - 1, 1, 1)
    weekly = alloc_w.loc[cap_start:].groupby(alloc_w.loc[cap_start:].index.to_period("W")).tail(1)

    # fills
    fills = _q(tcon, "SELECT as_of, sleeve, instrument_id, quantity, price FROM fills WHERE run_id = ? "
                     "ORDER BY as_of DESC, fill_id DESC", rid)
    fills["as_of"] = pd.to_datetime(fills["as_of"])
    trades = [{"d": r.as_of.strftime("%m-%d"), "sleeve": r.sleeve, "qty": float(r.quantity),
               "sym": r.instrument_id.upper(), "price": float(r.price)} for r in fills.head(N_TRADES).itertuples()]

    # risk events
    risk = _q(tcon, "SELECT as_of, rule, action, sleeve, detail FROM risk_events WHERE run_id = ? "
                    "AND rule = 'vix_circuit_breaker' ORDER BY as_of", rid)
    risk["as_of"] = pd.to_datetime(risk["as_of"])
    breaker = _breaker(risk, last_day)

    moods = _mood_events(probs.loc[:last_day])
    mood_days = {e["date"] for e in moods}
    rebals = [e for e in _rebal_events(alloc_w, fills, set(risk["as_of"])) if e["date"] not in mood_days]
    events = sorted(moods + rebals, key=lambda e: e["date"], reverse=True)[:N_EVENTS]
    for e in events:
        e["d"] = e.pop("date").strftime("%m-%d")

    # sleeve P&L
    month = pnl.loc[pnl.index.to_period("M") == last_day.to_period("M")].sum()
    today = pnl.loc[last_day]
    cum = pnl[SLEEVES].cumsum()
    year_ends = cum.groupby(cum.index.year).tail(1)
    cum_pts = {s: [0.0] + [float(v) for v in year_ends[s]] for s in SLEEVES}

    # growth (month ends)
    spy = _spy_index(mcon, total.index[0], last_day).reindex(total.index).ffill()
    monthly = pd.DataFrame({"eq": total / start_cash, "spy": spy,
                            "st": probs[["stressed-bull", "stressed-bear"]].sum(axis=1).reindex(total.index).ffill().fillna(0)})
    m_eq = monthly[["eq", "spy"]].groupby(monthly.index.to_period("M")).last()
    m_st = monthly["st"].groupby(monthly.index.to_period("M")).mean()

    rets = total.pct_change().dropna()
    rf = _tbill_daily(mcon, total.index[0] - pd.Timedelta(days=30), last_day, rets.index)
    excess = rets - rf
    sharpe = float(excess.mean() / excess.std() * np.sqrt(252)) if excess.std() > 0 else 0.0

    started, finished = run["started_at"], run["finished_at"]
    secs = int((finished - started).total_seconds()) if pd.notna(finished) else None
    n_ok = sum(c["ok"] for c in checks["checks"]) if checks else None

    return {
        "run_id": rid,
        "mode": (run["mode"] or "").upper(),
        "broker": "SIM",
        "sleeves_on": bool(cfg_run.get("sleeves_on", False)),
        "regime_run_id": cfg_run.get("regime_run_id"),
        "data_to": last_day.strftime("%Y-%m-%d"),
        "start_year": int(total.index[0].year),
        "end_year": int(last_day.year),
        "last_run": started.strftime("%m-%d %H:%M"),
        "duration_s": secs,
        "nav": float(total.iloc[-1]),
        "start_cash": start_cash,
        "mood": {s: float(now_probs[s]) for s in STATES},
        "trades": trades,
        "trade_count": int(len(fills)),
        "capital": {"from": weekly.index[0].strftime("%b %Y").upper(), "to": last_day.strftime("%b %Y").upper(),
                    "layers": {s: [round(float(v), 4) for v in weekly[s]] for s in SLEEVES},
                    "now": {s: float(alloc_w.loc[:last_day].iloc[-1][s]) for s in SLEEVES}},
        "pnl": {"month": last_day.strftime("%b").upper(),
                "rows": [{"n": s, "today": float(today[s]), "mtd": float(month[s])} for s in PNL_ROWS],
                "cum": cum_pts},
        "breaker": breaker,
        "events": events,
        "growth": {"months": [str(p) for p in m_eq.index], "eq": [round(float(v), 4) for v in m_eq["eq"]],
                   "spy": [round(float(v), 4) for v in m_eq["spy"]], "st": [round(float(v), 2) for v in m_st]},
        "stats": {"worst": _max_dd(total), "spy_worst": _max_dd(spy.dropna()), "sharpe": sharpe,
                  "multiple": float(total.iloc[-1] / start_cash), "spy_multiple": float(spy.iloc[-1])},
        "checks_passed": n_ok,
        "checks_total": len(checks["checks"]) if checks else None,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    checks = None
    if "--no-checks" not in sys.argv:
        print("running tests/system_check.py ...")
        checks = run_system_check()
        (OUT / "checks.json").write_text(json.dumps(checks, indent=1))
    elif (OUT / "checks.json").exists():
        checks = json.loads((OUT / "checks.json").read_text())

    tcon = duckdb.connect(str(TRADING_DB), read_only=True)
    mcon = duckdb.connect(str(MARKET_DB), read_only=True)
    try:
        runs = _q(tcon, "SELECT * FROM runs WHERE run_id LIKE 'backtest_%' AND status = 'finished' "
                        "ORDER BY started_at DESC")
        listed = []
        for run in runs.to_dict("records"):
            data = export_run(tcon, mcon, run, checks)
            (OUT / f"{run['run_id']}.json").write_text(json.dumps(data, separators=(",", ":")))
            listed.append({"run_id": run["run_id"], "notes": run["notes"]})
            print(f"  wrote {run['run_id']}.json")
        (OUT / "runs.json").write_text(json.dumps(listed, indent=1))
    finally:
        tcon.close()
        mcon.close()


if __name__ == "__main__":
    main()
