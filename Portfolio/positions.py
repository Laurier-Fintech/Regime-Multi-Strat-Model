# What we hold right now. One row ("slice") per sleeve + instrument + strategy + group,
# so we always know which strategy owns what (Jacob's sleeves need this)


class Positions:
    def __init__(self):
        holdings = empty table
        # columns: sleeve, instrument_id, strategy_id, group_id, quantity, avg_cost, multiplier
        # multiplier: 1 for ETFs / shares, 100 for a US option

    def apply_fill(self, fill, multiplier):
        # find the slice this fill belongs to (sleeve, instrument, strategy, group)
        # if no slice yet --> add one with quantity 0
        old_qty, old_cost = that slice's quantity and avg_cost
        new_qty = old_qty + fill.quantity

        if buying more of a long (or selling more of a short):
            # average cost moves toward the fill price
            avg_cost = (old_qty * old_cost + fill.quantity * fill.price) / new_qty
        else:
            # reducing a holding: avg_cost stays the same (the profit/loss is realised in cash)
            avg_cost = old_cost
        if crossing through zero (long --> short):
            avg_cost = fill.price for the new side

        if new_qty == 0 --> remove the slice
        else --> save new_qty, avg_cost

    def held(self, sleeve=None):
        # the holdings table, optionally for one sleeve only
        return holdings (filtered)

    def net_by_instrument(self):
        # add slices together per instrument --> what the broker actually sees
        # e.g. two sleeves both holding SPY --> one SPY number
        return quantity summed by instrument_id

    def to_rows(self, run_id, as_of, prices):
        # end-of-day rows for trading.duckdb "positions"
        # adds market_price and market_value = quantity * price * multiplier
        return table
