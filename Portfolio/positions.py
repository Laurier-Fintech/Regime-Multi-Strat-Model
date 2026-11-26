import pandas as pd


class Positions:
    """The holdings book. A class because it remembers what we hold from day to day"""

    def __init__(self):
        # key = (sleeve, instrument_id, strategy_id, group_id) --> {"quantity", "avg_cost", "multiplier"}
        self.holdings = {}

    def apply_fill(self, fill, multiplier=1):
        """Updates one slice with a fill. multiplier: 1 for ETFs / shares, 100 for a US option"""
        key = (fill.sleeve, fill.instrument_id, fill.strategy_id, fill.group_id)
        if key not in self.holdings:
            self.holdings[key] = {"quantity": 0, "avg_cost": 0.0, "multiplier": multiplier}

        old_qty = self.holdings[key]["quantity"]
        old_cost = self.holdings[key]["avg_cost"]
        new_qty = old_qty + fill.quantity

        if old_qty == 0 or old_qty * fill.quantity > 0:
            # opening, or adding to the same side --> avg cost moves toward the fill price
            avg_cost = (old_qty * old_cost + fill.quantity * fill.price) / new_qty
        elif old_qty * new_qty < 0:
            # flipped through zero (long --> short) --> the new side started at this price
            avg_cost = fill.price
        else:
            # reducing --> avg cost stays, the profit / loss shows up in cash
            avg_cost = old_cost

        if new_qty == 0:
            del self.holdings[key]
        else:
            self.holdings[key]["quantity"] = new_qty
            self.holdings[key]["avg_cost"] = avg_cost

    def apply_split(self, instrument_id, ratio):
        """A split: every slice of that instrument gets shares x ratio, avg cost / ratio (value unchanged)

        ratio: new shares per old share, e.g. 2.0 for a 2-for-1, 0.25 for a 1-for-4 reverse split
        """
        for (sleeve, iid, strategy_id, group_id), h in self.holdings.items():
            if iid == instrument_id:
                h["quantity"] = h["quantity"] * ratio
                h["avg_cost"] = h["avg_cost"] / ratio

    def quantity(self, sleeve, instrument_id, strategy_id, group_id=None):
        """How much of one slice we hold (0 if none)"""
        key = (sleeve, instrument_id, strategy_id, group_id)
        if key not in self.holdings:
            return 0
        return self.holdings[key]["quantity"]

    def held(self, sleeve=None):
        """The holdings as a table, optionally for one sleeve only"""
        rows = []
        for (s, instrument_id, strategy_id, group_id), h in self.holdings.items():
            if sleeve is None or s == sleeve:
                rows.append({"sleeve": s, "instrument_id": instrument_id, "strategy_id": strategy_id,
                             "group_id": group_id, **h})
        columns = ["sleeve", "instrument_id", "strategy_id", "group_id", "quantity", "avg_cost", "multiplier"]
        return pd.DataFrame(rows, columns=columns)

    def net_by_instrument(self):
        """Slices added up per instrument --> what the broker actually sees"""
        return self.held().groupby("instrument_id")["quantity"].sum()

    def to_rows(self, run_id, as_of, prices):
        """End-of-day rows for trading.duckdb "positions"

        Keyword arguments:
        prices -- today's price per instrument_id (from valuation.price_holdings)
        """
        rows = self.held()
        rows["market_price"] = rows["instrument_id"].map(prices)
        rows["market_value"] = rows["quantity"] * rows["market_price"] * rows["multiplier"]
        rows["group_id"] = rows["group_id"].fillna("")     # the database uses "" for no group
        rows["run_id"] = run_id
        rows["as_of"] = as_of
        return rows.drop(columns="multiplier")
