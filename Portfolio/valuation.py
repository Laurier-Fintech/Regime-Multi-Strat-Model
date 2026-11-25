import pandas as pd

from Data.DataBase.access import get_prices
from Config.settings import load

# NAV = cash + what everything we hold is worth today.
# Prices come through access.py with as_of, so no peeking at the future

LOOKBACK_DAYS = load("configs.yaml", "portfolio")["price_lookback_days"]


def price_holdings(instrument_ids, as_of):
    """Today's close for each instrument, or the last known one if there's none today

    Return: prices (Series by instrument_id), stale (list of ids priced from an older day)
    """
    if len(instrument_ids) == 0:
        return pd.Series(dtype=float), []

    start = pd.Timestamp(as_of) - pd.Timedelta(days=LOOKBACK_DAYS)
    table = get_prices(list(instrument_ids), start, as_of, as_of=as_of, field="close")

    prices = {}
    stale = []
    for instrument_id in instrument_ids:
        known = table[instrument_id].dropna()
        if known.empty:
            raise ValueError(f"No price for {instrument_id} in the {LOOKBACK_DAYS} days up to {as_of}.")
        prices[instrument_id] = known.iloc[-1]
        if known.index[-1] < pd.Timestamp(as_of):
            stale.append(instrument_id)
    # options (later): market mid if we have one, else Common/option_pricing (is_model_priced)
    return pd.Series(prices), stale


def nav(positions, ledger, prices):
    """NAV per sleeve and total

    sleeve rows: value of that sleeve's holdings
    total row:   all holdings + all cash
    Return: table with sleeve, nav, cash
    """
    held = positions.held()
    held["market_value"] = held["quantity"] * held["instrument_id"].map(prices) * held["multiplier"]

    rows = []
    for sleeve in sorted(held["sleeve"].unique()):
        value = held.loc[held["sleeve"] == sleeve, "market_value"].sum()
        rows.append({"sleeve": sleeve, "nav": value, "cash": None})

    cash = ledger.cash()
    rows.append({"sleeve": "total", "nav": held["market_value"].sum() + cash, "cash": cash})
    return pd.DataFrame(rows).set_index("sleeve")


def daily_pnl(today, yesterday, ledger, as_of):
    """Today's profit / loss per sleeve and total

    sleeve: change in holdings value + that sleeve's cash flows today (buys are -, sells +, costs -)
            --> buying $100 of QQQ is 0 P&L, not +$100
    total:  change in NAV - money deposited today
    Return: Series by sleeve, including "total"
    """
    pnl = {}
    for sleeve in today.index.union(yesterday.index if yesterday is not None else []):
        now = today["nav"].get(sleeve, 0.0)
        before = 0.0 if yesterday is None else yesterday["nav"].get(sleeve, 0.0)
        if sleeve == "total":
            pnl[sleeve] = now - before - ledger.flows(as_of, kinds=["deposit", "withdrawal"])
        else:
            pnl[sleeve] = now - before + ledger.flows(as_of, sleeve=sleeve)
    return pd.Series(pnl)


def to_rows(run_id, as_of, nav_table, pnl):
    """Rows for trading.duckdb "nav": sleeve, nav, cash, pnl_day"""
    rows = nav_table.reset_index()
    rows["pnl_day"] = rows["sleeve"].map(pnl)
    rows["run_id"] = run_id
    rows["as_of"] = as_of
    return rows
