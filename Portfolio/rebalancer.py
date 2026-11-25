from Portfolio.broker_interface import Order
from Config.settings import load

STANDIN_STRATEGY = load("backtest.yaml", "standin_strategy_id")

# Wanted - held = orders. Sleeves (or the ETF stand-ins) say what they WANT to hold,
# this works out what to TRADE. Gets the whole book at once


def weights_to_wanted(weights, nav, standin_etfs, prices):
    """Sleeves OFF only: sleeve weight --> whole shares of its stand-in ETFs

    e.g. equity 35% of $1M, stand-in qqq at $500 --> 700 shares

    Keyword arguments:
    weights -- the allocator's weight per sleeve
    nav -- total NAV today
    standin_etfs -- from backtest.yaml, e.g. {"equity": {"qqq": 1.0}, "reserve": {"cash": 0.5, "gld": 0.5}}
    prices -- today's price per instrument_id
    Return: list of wanted rows (sleeve, instrument_id, strategy_id, group_id, target_quantity)
    """
    wanted = []
    for sleeve, etfs in standin_etfs.items():
        for etf, share in etfs.items():
            if etf == "cash":       # cash isn't bought, it just stays in the ledger
                continue
            dollars = weights[sleeve] * nav * share
            shares = int(dollars / prices[etf])      # int() rounds toward 0, works for shorts too
            wanted.append({"sleeve": sleeve, "instrument_id": etf, "strategy_id": STANDIN_STRATEGY,
                           "group_id": None, "target_quantity": shares})
    return wanted


def make_orders(wanted, positions, as_of, prices, min_trade_value):
    """Wanted - held = orders, skipping tiny trades. Sells first so they free up cash before buys

    Keyword arguments:
    wanted -- list of wanted rows (anything we hold that isn't in here --> target 0, close it)
    positions -- the Positions book
    prices -- today's price per instrument_id
    min_trade_value -- skip trades smaller than this many dollars
    Return: list of Orders
    """
    # every slice we want OR hold
    targets = {}
    for w in wanted:
        key = (w["sleeve"], w["instrument_id"], w["strategy_id"], w["group_id"])
        targets[key] = targets.get(key, 0) + w["target_quantity"]
    for key in positions.holdings:
        if key not in targets:
            targets[key] = 0

    trades = []
    for key, target in targets.items():
        sleeve, instrument_id, strategy_id, group_id = key
        held = positions.quantity(sleeve, instrument_id, strategy_id, group_id)
        change = target - held
        if change == 0:
            continue

        multiplier = positions.holdings[key]["multiplier"] if key in positions.holdings else 1
        trade_value = abs(change * prices[instrument_id] * multiplier)
        closing = target == 0
        if trade_value < min_trade_value and not closing:    # never skip a close, or leftovers pile up
            continue

        trades.append((key, change))

    # sells first (change < 0), then number them
    trades.sort(key=lambda t: t[1] > 0)
    orders = []
    for i, ((sleeve, instrument_id, strategy_id, group_id), change) in enumerate(trades, start=1):
        orders.append(Order(order_id=f"{as_of}-{i:04d}", as_of=as_of, sleeve=sleeve,
                            instrument_id=instrument_id, strategy_id=strategy_id,
                            quantity=change, group_id=group_id))
    return orders
