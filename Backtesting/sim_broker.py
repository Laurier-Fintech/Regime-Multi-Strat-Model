# The simulated broker. Follows the Broker template in Portfolio/broker_interface.py,
# so the engine can't tell it apart from IBKR. Fills every order right away, with costs.
import pandas as pd

from Config.settings import load
from Data.DataBase.access import get_prices
from Portfolio.broker_interface import Broker, Fill


class SimBroker(Broker):
    """Fills orders at today's close, plus spread + slippage, minus commission"""

    def __init__(self, book=None):
        self.book = book       # a MarketBook (prices in memory, fast). None = ask the database
        costs = load("backtest.yaml", "costs")
        self.commission_per_share = costs["commission_per_share"]
        self.commission_min = costs["commission_min"]
        self.slippage_bps = costs["slippage_bps"]
        self.half_spread_bps = costs["half_spread_bps"]
        self.rejected = []     # orders we couldn't fill (no price that day)

    def send_orders(self, orders, as_of):
        """Today's orders --> list of fills"""
        if len(orders) == 0:
            return []

        # one price lookup for all of today's orders, only today's close (as_of --> no future)
        ids = sorted(set(order.instrument_id for order in orders))
        if self.book is not None:
            # only a close from TODAY counts, an older one means it didn't trade today
            today = pd.Timestamp(as_of)
            closes = {i: p for i, (p, d) in self.book.last_prices(ids, as_of).items() if d == today}
        else:
            table = get_prices(ids, as_of, as_of, as_of=as_of, field="close")
            closes = {} if table.empty else table.iloc[0].to_dict()

        fills = []
        for order in orders:
            close = closes.get(order.instrument_id)
            if close is None or close != close:
                self.rejected.append(order)
                continue

            cost_bps = self.half_spread_bps + self.slippage_bps
            if order.quantity > 0:
                price = close * (1 + cost_bps / 10000)
            else:
                price = close * (1 - cost_bps / 10000)

            commission = max(self.commission_min, abs(order.quantity) * self.commission_per_share)

            fills.append(Fill(fill_id=f"F-{order.order_id}",
                              order_id=order.order_id,
                              as_of=as_of,
                              sleeve=order.sleeve,
                              instrument_id=order.instrument_id,
                              strategy_id=order.strategy_id,
                              quantity=order.quantity,
                              price=price,
                              commission=commission,
                              group_id=order.group_id))
        return fills

    def open_orders(self):
        return []      

# LATER (options): option prices from the chain mid, or Common/option_pricing when missing
#                  (is_model_priced = True), plus per-contract fees. See README option_history.py
