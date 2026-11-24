# Runs a backtest: read the settings, plug the SimBroker into the engine, run every day, save.
# Kept long-term: every future backtest (sleeves off or on) starts here
# Settings come from Config/backtest.yaml


def run_backtest(settings_file="Config/backtest.yaml", notes=None):
    settings = load backtest.yaml, check them (start < end, starting_cash > 0, stand-in shares add up per sleeve)

    con = connect_trading()
    run_id = start a row in "runs" (mode="backtest", git commit, settings as text, dates, notes)
             # same idea as regime_store.start_run --> share one helper

    days = trading days between start and end (SPY's dates)
    engine = Engine(broker=SimBroker(), settings, run_id)

    try:
        engine.run(days)
        mark the run "finished"
    except:
        mark the run "failed", then re-raise the error
    finally:
        close the connection

    return run_id


if run from the terminal:
    print("saved run:", run_backtest())
