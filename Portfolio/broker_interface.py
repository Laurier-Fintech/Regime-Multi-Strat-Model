# The plug. Every broker (simulated in Backtesting, IBKR in Execution) follows these rules,
# so swapping the broker is the ONLY difference between a backtest and live trading


class Order:
    # one instruction to trade, made by rebalancer.py
    order_id        # unique id, e.g. "2026-11-24-0001"
    as_of           # the day the order was made
    sleeve          # vol / equity / spread / reserve
    instrument_id   # e.g. "SPY", later "TQQQ 2027-01-15 P 50"
    strategy_id     # e.g. "etf_standin", Jacob's "wheel" / "stress_put_spread"
    group_id        # links option legs together (None for ETFs)
    quantity        # signed: + = buy, - = sell
    order_type      # "market" for v1.0 ("limit" later)


class Fill:
    # what actually happened to an order, given back by the broker
    fill_id
    order_id        # None for expiry / assignment (lifecycle.py)
    as_of
    sleeve, instrument_id, strategy_id, group_id    # copied from the order
    quantity        # signed: + = bought, - = sold (can be less than ordered)
    price           # per share / contract
    commission
    fees
    fill_type       # "trade" / "expiry" / "assignment" / "exercise"
    is_model_priced # True if the price came from a model, not the market


class Broker:
    # the template. sim_broker.py and live_broker.py each fill this in

    def send_orders(self, orders, as_of):
        # take today's orders, return the list of fills
        # must be written by each real broker, the template just raises an error
        raise NotImplementedError

    def open_orders(self):
        # orders sent but not filled yet (sim broker: always empty, it fills right away)
        raise NotImplementedError
