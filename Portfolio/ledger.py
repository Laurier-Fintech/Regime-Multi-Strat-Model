# Cash. Every movement of money gets one row, nothing is ever edited.
# Cash balance = the sum of all rows (total, or per sleeve)


class Ledger:
    def __init__(self, starting_cash):
        entries = empty table
        # columns: entry_id, as_of, sleeve, amount (+ = cash in), kind, ref
        add a "deposit" entry for starting_cash (sleeve = None, the unassigned pool)

    def record_fill(self, fill, multiplier):
        # buying costs cash, selling brings cash in
        add "trade" entry:      amount = -fill.quantity * fill.price * multiplier, ref = fill_id
        add "commission" entry: amount = -fill.commission
        add "fee" entry:        amount = -fill.fees           (skip if 0)

    def record_dividend(self, as_of, sleeve, instrument_id, quantity, dividend_per_share):
        add "dividend" entry: amount = quantity * dividend_per_share
        # short positions PAY the dividend --> negative automatically because quantity < 0

    def record_interest(self, as_of, cash_balance, tbill_rate):
        # idle cash earns the T-bill rate, one day's worth
        add "interest" entry: amount = cash_balance * tbill_rate / 252

    def cash(self, sleeve=None):
        return sum of amount (for one sleeve, or all)

    def to_rows(self, run_id):
        # rows for trading.duckdb "cash_ledger" (only the new ones since last save)
        return table
