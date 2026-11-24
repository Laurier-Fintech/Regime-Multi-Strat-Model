"""PSEUDOCODE (not real code yet), kept in a string so the team test run skips it.

# The ETF test: the first full run of v1.0, sleeves OFF.
# Checks the regime + allocator + breaker + portfolio + broker all work together on plain ETFs,
# before any options are involved. Uses a saved regime run so it doesn't take 20+ minutes


def setup():
    # a short window first (e.g. 2019-2021, includes Covid) so it runs fast
    # run_backtest with sleeves_on = false and a saved regime_run_id
    run_id = run_backtest(test settings)
    load its tables back: nav, positions, fills, cash_ledger, allocations


# --- Does the bookkeeping add up? ---

def test_weights_add_to_one():
    every day's allocations add up to 1, none below 0

def test_cash_reconciles():
    ledger cash at the end == starting cash + sum of every cash_ledger row

def test_positions_match_fills():
    for every instrument: final quantity == sum of all fill quantities

def test_nav_adds_up():
    every day: total nav == sum of the sleeve navs
    every day: nav == cash + sum of market_value

def test_costs_charged():
    every fill has commission > 0 and a price worse than the close (buy above, sell below)


# --- Does it behave sensibly? ---

def test_nav_never_negative():
    total nav > 0 every day

def test_breaker_fires_in_covid():
    at least one "vix_circuit_breaker" risk_event in Feb-Mar 2020

def test_not_overtrading():
    average number of trades per month is below a sane limit (number TBD)


# --- The result (looked at by eye, not pass/fail) ---

def report():
    chart: our NAV vs SPY buy-and-hold, same starting money
    print: total return, yearly vol, worst drop (max drawdown), turnover
"""
