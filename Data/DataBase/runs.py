import subprocess
from datetime import datetime

import pandas as pd

from Data.DataBase.db import REPO_ROOT, append_rows

# One row in trading.duckdb "runs" per run (a regime run, a backtest, a live session).
# Shared by regime_store.py and run_backtest.py


def git_commit():
    """The current git commit, so we know which code made a run (None if git isn't there)"""
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
                             capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def start_run(con, prefix, start, end, settings_text, mode="backtest", notes=None):
    """Adds a row to "runs" and gives back its run_id, e.g. 'backtest_20261125_143005'

    Keyword arguments:
    prefix -- "regime" / "backtest", so runs are easy to tell apart
    settings_text -- the settings used, as text (saved with the run)
    """
    run_id = f"{prefix}_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    row = pd.DataFrame([{
        "run_id": run_id,
        "mode": mode,
        "git_commit": git_commit(),
        "config_snapshot": settings_text,
        "start_date": pd.Timestamp(start).date(),
        "end_date": pd.Timestamp(end).date(),
        "started_at": datetime.now(),
        "status": "running",
        "notes": notes,
    }])
    append_rows(con, "runs", row)
    return run_id


def finish_run(con, run_id, status="finished"):
    """Marks a run as 'finished' or 'failed' and stamps the time"""
    con.execute("UPDATE runs SET status = ?, finished_at = ? WHERE run_id = ?",
                [status, datetime.now(), run_id])
