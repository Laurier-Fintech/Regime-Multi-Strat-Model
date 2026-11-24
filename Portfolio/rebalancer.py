# Wanted - held = orders. Sleeves (or the ETF stand-ins) say what they WANT to hold,
# this works out what to TRADE. Gets the whole book at once, after RiskManagement approves it


def make_orders(wanted, positions, as_of, min_trade_value, prices):
    # wanted: one row per sleeve + instrument + strategy + group, with target_quantity
    #         anything we hold that is NOT in wanted --> target 0 (close it)
    held = positions.held()

    line up wanted and held on (sleeve, instrument_id, strategy_id, group_id)
    missing on either side --> 0
    change = target_quantity - held quantity

    drop rows where change == 0
    drop rows where |change * price * multiplier| < min_trade_value   # tiny trades cost more than they're worth
    # (never drop a trade that fully CLOSES a slice, or leftovers pile up)

    turn each remaining row into an Order (order_id, as_of, sleeve, instrument, strategy, group, quantity=change)
    sells first, then buys     # frees up cash before spending it
    return orders


def weights_to_wanted(weights, nav, standin_etfs, prices):
    # sleeves OFF only (the ETF test): sleeve weight --> shares of its stand-in ETF
    # e.g. equity 35% of $1M NAV, stand-in QQQ at $500 --> 700 shares
    for each sleeve:
        dollars = weights[sleeve] * nav
        shares = whole number of (dollars / price of that sleeve's ETF)
        wanted row: sleeve, instrument = ETF, strategy = "etf_standin", group = None, target = shares
    return wanted
