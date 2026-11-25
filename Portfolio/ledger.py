import pandas as pd

from Config.settings import load

# Cash. Every movement of money is one entry, nothing is ever edited.
# Cash balance = the sum of the entries (total, or per sleeve)

TRADING_DAYS = load("configs.yaml", "trading_days_per_year")


class Ledger:
    """The cash book. A class because it keeps every entry from day to day"""

    def __init__(self, starting_cash, as_of):
        self.entries = []      # one dict per cash movement
        self.saved = 0         # how many entries are already in the database
        self._add(as_of, None, starting_cash, "deposit", None)   # sleeve None = the shared pool

    def _add(self, as_of, sleeve, amount, kind, ref):
        """Adds one entry. amount: + = cash in, - = cash out"""
        self.entries.append({"entry_id": f"{as_of}-{len(self.entries) + 1:05d}", "as_of": as_of,
                             "sleeve": sleeve, "amount": amount, "kind": kind, "ref": ref})

    def record_fill(self, fill, multiplier=1):
        """Buying costs cash, selling brings cash in, commission and fees always cost"""
        self._add(fill.as_of, fill.sleeve, -fill.quantity * fill.price * multiplier, "trade", fill.fill_id)
        self._add(fill.as_of, fill.sleeve, -fill.commission, "commission", fill.fill_id)
        if fill.fees != 0:
            self._add(fill.as_of, fill.sleeve, -fill.fees, "fee", fill.fill_id)

    def record_dividend(self, as_of, sleeve, instrument_id, quantity, dividend_per_share):
        """Dividend in. A short position PAYS it --> negative because quantity < 0"""
        self._add(as_of, sleeve, quantity * dividend_per_share, "dividend", instrument_id)

    def record_interest(self, as_of, tbill_rate_pct):
        """One day of T-bill interest on the cash we hold. tbill_rate_pct: 4.5 = 4.5%"""
        amount = self.cash() * tbill_rate_pct / 100 / TRADING_DAYS
        self._add(as_of, None, amount, "interest", None)

    def cash(self, sleeve="all"):
        """Cash balance: "all" = everything, or one sleeve's own flows"""
        total = 0.0
        for e in self.entries:
            if sleeve == "all" or e["sleeve"] == sleeve:
                total += e["amount"]
        return total

    def flows(self, as_of, sleeve="all", kinds=None):
        """Sum of one day's entries, e.g. kinds=["deposit"] for money added that day"""
        total = 0.0
        for e in self.entries:
            if e["as_of"] != as_of:
                continue
            if sleeve != "all" and e["sleeve"] != sleeve:
                continue
            if kinds is not None and e["kind"] not in kinds:
                continue
            total += e["amount"]
        return total

    def to_rows(self, run_id):
        """The NEW entries since the last save, for trading.duckdb "cash_ledger" """
        rows = pd.DataFrame(self.entries[self.saved:])
        self.saved = len(self.entries)
        rows["run_id"] = run_id
        return rows
