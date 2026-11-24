# NAV = cash + what everything we hold is worth today. Total and per sleeve.
# Prices come through access.py with as_of, so no peeking at the future


def price_holdings(holdings, as_of):
    # ETFs / shares --> today's close from get_prices(..., as_of=as_of)
    # options       --> market mid if we have one, else Common/option_pricing (is_model_priced = True)
    #                   (options come later, when Jacob's sleeves go on)
    # no price today (holiday, gap) --> use the last known price, flag it
    return price per instrument, is_model_priced per instrument


def nav(positions, ledger, as_of):
    prices = price_holdings(positions.held(), as_of)
    market_value = quantity * price * multiplier, for every slice

    per sleeve: nav = that sleeve's market_value + that sleeve's cash
    total:      nav = all market_value + all cash
    return table: sleeve, nav, cash


def daily_pnl(today_nav, yesterday_nav, today_flows):
    # P&L = change in NAV, minus money that just moved in or out (deposits, sleeve transfers)
    # otherwise moving $100 into a sleeve would look like $100 profit
    return today_nav - yesterday_nav - today_flows, per sleeve and total


def to_rows(run_id, as_of, nav_table, pnl):
    # rows for trading.duckdb "nav": sleeve, nav, cash, pnl_day (+ one "total" row)
    return table
