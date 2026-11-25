from dataclasses import dataclass
from abc import ABC, abstractmethod
from datetime import date


@dataclass(frozen=True)
class Order:
    """One instruction to trade, made by rebalancer.py"""
    order_id: str          # unique id, e.g. "2026-11-24-0001"
    as_of: date            # the day the order was made
    sleeve: str            # vol / equity / spread / reserve
    instrument_id: str     # e.g. "qqq", later "TQQQ 2027-01-15 P 50"
    strategy_id: str       # e.g. "etf_standin", Jacob's "wheel" / "stress_put_spread"
    quantity: int          # signed: + = buy, - = sell
    # defaults go last
    group_id: str | None = None    # links option legs together (None for ETFs)
    order_type: str = "market"     # "market" / "limit" (the only two the database accepts)


@dataclass(frozen=True)
class Fill:
    """What actually happened to an order, given back by the broker"""
    fill_id: str
    order_id: str | None   # None for expiry / assignment (lifecycle.py)
    as_of: date
    sleeve: str
    instrument_id: str
    strategy_id: str
    quantity: int          # signed: + = bought, - = sold (can be less than ordered)
    price: float           # per share / contract
    commission: float
    # defaults go last
    group_id: str | None = None
    fees: float = 0.0
    fill_type: str = "trade"        # "trade" / "expiry" / "assignment" / "exercise"
    is_model_priced: bool = False   # True if the price came from a model, not the market


class Broker(ABC):
    """The plug. SimBroker and the live IBKR broker both fill this in"""

    @abstractmethod
    def send_orders(self, orders, as_of):
        """Take today's orders, return the list of fills"""

    @abstractmethod
    def open_orders(self):
        """Orders sent but not filled yet (sim broker: always empty)"""
