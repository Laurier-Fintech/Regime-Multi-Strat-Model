# LATER (when Jacob's sleeves go on). Not needed for the ETF test.
# Jacob's equity sleeve reads the portfolio as an EquityPortfolioSnapshot (Sleeves/EquitySleeve/wheel.py).
# This file builds that from our positions, ledger and broker, so his code works unchanged


def equity_snapshot(positions, ledger, broker, lifecycle, as_of, base_currency):
    holdings        = positions.held(sleeve="equity") --> list of EquityHolding
                      (instrument_id, quantity, strategy_id, group_id)
    open_orders     = broker.open_orders() for the equity sleeve --> list of EquityOpenOrder
    events          = lifecycle events already applied (assignments, expiries) --> EquityLifecycleEvent
    available_cash  = ledger.cash(sleeve="equity")  # can be negative, Jacob's code handles that

    return EquityPortfolioSnapshot(sleeve_id="equity", as_of, base_currency,
                                   available_cash, holdings, open_orders, events)
