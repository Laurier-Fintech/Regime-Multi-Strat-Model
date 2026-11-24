# The simulated broker. Follows the Broker template in Portfolio/broker_interface.py,
# so the engine can't tell it apart from IBKR. Fills every order right away, with costs.
# Settings come from Config/backtest.yaml (section "costs")


class SimBroker(Broker):
    def __init__(self):
        costs = load the "costs" section of backtest.yaml
        # commission_per_share, commission_min, slippage_bps, half_spread_bps
        fill_count = 0

    def send_orders(self, orders, as_of):
        fills = []
        for each order:
            close = today's close for order.instrument_id, from get_prices(..., as_of=as_of)
            if no price today --> reject the order (can't trade what isn't trading), log it

            # we pay up when buying and get less when selling
            cost_bps = half_spread_bps + slippage_bps
            if buying:  price = close * (1 + cost_bps / 10000)
            if selling: price = close * (1 - cost_bps / 10000)

            commission = max(commission_min, |quantity| * commission_per_share)

            fills.append(Fill(fill_id, order_id, as_of, sleeve, instrument, strategy, group,
                              quantity = order.quantity, price, commission, fees = 0,
                              fill_type = "trade", is_model_priced = False))
        return fills

    def open_orders(self):
        return []      # everything fills straight away in the simulation


# LATER (options): option prices from the chain mid, or Common/option_pricing when missing
#                  (is_model_priced = True), plus per-contract fees. See README option_history.py
