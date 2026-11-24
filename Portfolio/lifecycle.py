# LATER (when Jacob's sleeves go on). Not needed for the ETF test.
# Things that change what we hold WITHOUT a trade. Each one becomes a Fill with a fill_type,
# then goes through positions.apply_fill and ledger.record_fill like any trade


def check_expiries(positions, as_of, prices):
    for every option we hold whose expiry is today:
        in the money  --> exercise / assignment (below)
        out of money  --> Fill(fill_type="expiry", quantity = -held, price = 0)


def assignment(option_slice, underlying_price):
    # short put assigned  --> we BUY 100 shares per contract at the strike (the wheel's next step)
    # short call assigned --> we SELL 100 shares per contract at the strike
    return two fills: the option closing (fill_type="assignment") + the shares (at the strike)
    # the new shares keep the same strategy_id / group_id so the wheel knows they're its own


def splits_and_dividends(positions, as_of):
    # dividends --> ledger.record_dividend
    # splits    --> quantity * ratio, avg_cost / ratio (clean.prices is already "as traded")
    pass


def events_applied(as_of):
    # list of what happened, for snapshots.py (Jacob's EquityLifecycleEvent)
    return events
