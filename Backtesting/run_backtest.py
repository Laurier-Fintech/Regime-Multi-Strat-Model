import json

from Backtesting.sim_broker import SimBroker
from Config.settings import load
from Data.DataBase import runs
from Data.DataBase.access import get_prices
from Data.DataBase.db import connect_trading
from ModelHome.engine import Engine

# Runs a backtest: read the settings, plug the SimBroker into the engine, run every day, save.
# Kept long-term: every future backtest (sleeves off or on) starts here


def run_backtest(settings=None, notes=None):
    """
    Keyword arguments:
    settings -- backtest.yaml as a dict (None = read Config/backtest.yaml)
    Return: run_id
    """
    if settings is None:
        settings = load("backtest.yaml")
    start, end = settings["run"]["start"], settings["run"]["end"]

    # trading days = the days SPY traded
    days = [d.date() for d in get_prices("spy", start, end, as_of=end).index]

    con = connect_trading()
    try:
        run_id = runs.start_run(con, "backtest", start, end, json.dumps(settings, default=str), notes=notes)
        try:
            Engine(SimBroker(), settings, run_id, con).run(days)
        except Exception:
            runs.finish_run(con, run_id, "failed")
            raise
        runs.finish_run(con, run_id)
        return run_id
    finally:
        con.close()


if __name__ == "__main__":
    print("saved run:", run_backtest())
