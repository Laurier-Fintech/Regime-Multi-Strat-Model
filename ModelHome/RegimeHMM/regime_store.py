"""Saves the regime's daily output to trading.duckdb so backtests can reuse it.

A full regime run from 1995 takes 20+ minutes (all the quarterly refits).
Run it once, save it here, and every backtest after that just reads the table.

    run_id = save_regime_run("1995-01-01", "2026-11-20")   # slow, once
    probs = load_regime_probs(run_id)                        # fast, every backtest

Table used (see Data/DataBase/setup_run_once/schema_trading.sql):
    runs          one row per run: dates, git commit, settings, status
    regime_probs  run_id, as_of, state, probability  (4 rows per day, one per mood)
"""

import json

import numpy as np
import pandas as pd

from Data.DataBase.access import get_trading_records
from Data.DataBase import runs
from Data.DataBase.db import append_rows, connect_trading
from Data.DataBase.runs import finish_run
from ModelHome.RegimeHMM import regime_model
from Config.settings import load

MOODS = load("model.yaml", "moods")


def _settings():
    """The regime settings used for this run, saved as text in runs.config_snapshot"""
    return json.dumps({
        "model": "regime",
        "stress_features": regime_model.STRESS_FEATURES,
        "direction_features": regime_model.DIRECTION_FEATURES,
        "first_date": regime_model.FIRST_DATE,
        "refit_every_months": regime_model.REFIT_EVERY_MONTHS,
        "min_history_days": regime_model.MIN_HISTORY_DAYS,
        "zscore_features": regime_model.ZSCORE_FEATURES,
        "zscore_window": regime_model.ZSCORE_WINDOW,
    })


def start_run(con, start, end, mode="backtest", notes=None):
    """Adds a regime run to "runs" --> run_id e.g. 'regime_20261123_143005'"""
    return runs.start_run(con, "regime", start, end, _settings(), mode, notes)


def write_regime_probs(con, run_id, probs):
    """Saves the daily mood probabilities for one run

    Keyword arguments:
    con -- open connection from connect_trading()
    run_id -- from start_run()
    probs -- table from RegimeModel.run(): one row per day, one column per mood
    Return: number of rows written (4 per day)
    """
    # Checks: the 4 moods, numbers between 0 and 1, each day sums to 1
    missing = [m for m in MOODS if m not in probs.columns]
    if missing:
        raise ValueError(f"probs is missing moods: {missing}")
    probs = probs[MOODS].astype(float)
    if probs.isna().any().any():
        raise ValueError("probs has missing values")
    if ((probs < 0) | (probs > 1)).any().any():
        raise ValueError("probs must be between 0 and 1")
    if not np.allclose(probs.sum(axis=1), 1.0, atol=1e-6):
        raise ValueError("each day's probabilities must sum to 1")

    # Wide (one column per mood) --> long (one row per day per mood), the table's shape
    long = probs.rename_axis("as_of").reset_index().melt(
        id_vars="as_of", var_name="state", value_name="probability")
    long["as_of"] = pd.to_datetime(long["as_of"]).dt.date
    long["run_id"] = run_id
    long["probability"] = long["probability"].clip(0, 1)   # tiny rounding like 1.0000000002

    return append_rows(con, "regime_probs", long[["run_id", "as_of", "state", "probability"]])


def load_regime_probs(run_id, con=None):
    """Reads a saved run back in the same shape RegimeModel.run() gives

    Keyword arguments:
    run_id -- which run to load
    con -- an already-open trading.duckdb connection (the engine passes its own,
           DuckDB won't open a second one to the same file). None = open read-only
    Return: table, one row per day (date index), one column per mood
    """
    if con is None:
        long = get_trading_records("regime_probs", run_id)
    else:
        long = con.execute("SELECT * FROM regime_probs WHERE run_id = ?", [run_id]).df()
    if long.empty:
        raise ValueError(f"no regime_probs saved for run_id {run_id}")
    wide = long.pivot(index="as_of", columns="state", values="probability")
    wide.index = pd.to_datetime(wide.index)
    wide.columns.name = None
    return wide[MOODS].sort_index()


def list_regime_runs():
    """All saved regime runs, newest first, so you can pick a run_id"""
    runs = get_trading_records("runs")
    runs = runs[runs["run_id"].str.startswith("regime_")]
    return runs.sort_values("started_at", ascending=False)[
        ["run_id", "status", "start_date", "end_date", "git_commit", "notes", "started_at"]]


def save_regime_run(start, end, notes=None):
    """Runs the regime day by day and saves it. The slow one: 20+ minutes from 1995

    The run is marked 'failed' if anything breaks, so half-done runs are easy to spot.

    Keyword arguments:
    start, end -- days to run
    notes -- free text saved with the run
    Return: run_id
    """
    con = connect_trading()
    try:
        run_id = start_run(con, start, end, notes=notes)
        try:
            probs = regime_model.RegimeModel().run(start, end)
            write_regime_probs(con, run_id, probs)
        except Exception:
            finish_run(con, run_id, "failed")
            raise
        finish_run(con, run_id)
        return run_id
    finally:
        con.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the regime once and save it to trading.duckdb")
    parser.add_argument("start")
    parser.add_argument("end")
    parser.add_argument("--notes", default=None)
    args = parser.parse_args()
    print("saved run:", save_regime_run(args.start, args.end, args.notes))
