"""System check: do all the v1.0 pieces work? Takes about a minute. Run before a big run:

    .venv/Scripts/python.exe tests/system_check.py

Prints a line per check, then READY TO GO or NOT READY. Never writes to the real trading.duckdb
(the engine check runs on a temporary copy)
"""
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))     # repo root, so imports work

import duckdb
import numpy as np
import pandas as pd

from Config.settings import load, sleeves
from Data.DataBase import db
from Data.DataBase.access import get_prices
from Portfolio.rebalancer import standin_ids

DAY = date(2020, 3, 16)       # a real crisis day with prices for every stand-in ETF


def check_config():
    """Every yaml file loads and the allocator settings pass their own checks"""
    for f in ["configs.yaml", "model.yaml", "backtest.yaml", "risk.yaml"]:
        load(f)
    from ModelHome.allocator import Allocator
    Allocator()
    assert sleeves() == ["vol", "equity", "spread", "reserve"], f"sleeves: {sleeves()}"
    assert load("backtest.yaml", "run")["sleeves_on"] is False, "v1.0 needs sleeves_on: false"


def check_database():
    """market_data has prices for every stand-in ETF, trading.duckdb is on schema v2"""
    etfs = standin_ids(load("backtest.yaml", "standin_etfs"))
    prices = get_prices(etfs + ["spy"], DAY, DAY, as_of=DAY)
    assert prices.notna().all(axis=None), f"missing prices on {DAY}: {prices}"
    con = db.connect_trading(read_only=True)
    version = con.execute("SELECT max(schema_version) FROM schema_version").fetchone()[0]
    con.close()
    assert version == db.TRADING_SCHEMA_VERSION, f"trading.duckdb is schema v{version}, rebuild it (create_databases.py)"


def check_regime_hmm():
    """The HMM finds 2 obvious states in fake data"""
    from ModelHome.RegimeHMM import regime_hmm
    rng = np.random.default_rng(0)
    truth = np.repeat([0, 1, 0, 1], 150)
    X = np.where(truth[:, None] == 0, rng.normal(0, 1, (600, 2)), rng.normal(3, 1, (600, 2)))
    params = regime_hmm.fit(X)
    guess = regime_hmm.filter_all(X, params).argmax(axis=1)
    accuracy = max((guess == truth).mean(), (guess != truth).mean())    # states can come out swapped
    assert accuracy > 0.95, f"only {accuracy:.0%} of days labelled right"


def check_allocator():
    """70% stressed-bear + 30% calm-bull blends right, weights always add to 1"""
    from ModelHome.allocator import Allocator, _blend
    a = Allocator()
    probs = pd.Series({"calm-bull": 0.3, "calm-bear": 0, "stressed-bull": 0, "stressed-bear": 0.7})
    expected = 0.3 * a.mixes.loc["calm-bull"] + 0.7 * a.mixes.loc["stressed-bear"]
    assert np.allclose(_blend(probs, a.mixes), expected), "blend is wrong"
    assert a.update(None) is None, "warm-up should give None"
    for _ in range(5):
        w = a.update(probs)
        assert abs(w.sum() - 1) < 1e-9 and (w >= 0).all(), f"bad weights {w.to_dict()}"


def check_positions():
    """Average cost: add, reduce, flip long --> short"""
    from Portfolio.broker_interface import Fill
    from Portfolio.positions import Positions
    p = Positions()
    steps = [(10, 100.0, 10, 100.0), (10, 110.0, 20, 105.0), (-5, 120.0, 15, 105.0), (-20, 90.0, -5, 90.0)]
    for qty, price, want_qty, want_cost in steps:
        p.apply_fill(Fill("f", None, DAY, "equity", "qqq", "etf_standin", qty, price, 0.0))
        h = p.holdings[("equity", "qqq", "etf_standin", None)]
        assert (h["quantity"], round(h["avg_cost"], 6)) == (want_qty, want_cost), f"got {h}"


def check_ledger_and_valuation():
    """Buying is 0 P&L except the commission, NAV = cash + holdings"""
    from Portfolio.broker_interface import Fill
    from Portfolio.ledger import Ledger
    from Portfolio.positions import Positions
    from Portfolio import valuation
    pos, led = Positions(), Ledger(100_000, DAY)
    prices, _ = valuation.price_holdings(["qqq"], DAY)
    fill = Fill("f1", "o1", DAY, "equity", "qqq", "etf_standin", 100, float(prices["qqq"]), 1.0)
    pos.apply_fill(fill)
    led.record_fill(fill)
    nav = valuation.nav(pos, led, prices)
    assert abs(nav.loc["total", "nav"] - (100_000 - 1.0)) < 1e-6, f"nav {nav.loc['total', 'nav']}"
    pnl = valuation.daily_pnl(nav, None, led, DAY)
    assert abs(pnl["equity"] + 1.0) < 1e-6 and abs(pnl["total"] + 1.0) < 1e-6, f"pnl {pnl.to_dict()}"


def check_rebalancer_and_broker():
    """Weights --> shares --> orders (sells first) --> fills with costs"""
    from Backtesting.sim_broker import SimBroker
    from Portfolio import rebalancer, valuation
    from Portfolio.positions import Positions
    standins = load("backtest.yaml", "standin_etfs")
    weights = pd.Series({"vol": 0.25, "equity": 0.25, "spread": 0.25, "reserve": 0.25})
    ids = rebalancer.standin_ids(standins)
    prices, _ = valuation.price_holdings(ids, DAY)
    wanted = rebalancer.weights_to_wanted(weights, 1_000_000, standins, prices, p_stressed=0.5)
    vol_ids = {w["instrument_id"] for w in wanted if w["sleeve"] == "vol"}
    assert vol_ids == {"putw_index", "vixy"}, f"vol stand-in at 50% stressed should hold both, got {vol_ids}"
    early = rebalancer.weights_to_wanted(weights, 1_000_000, standins, prices.drop("vixy"), p_stressed=1.0)
    assert not any(w["sleeve"] == "vol" and w["target_quantity"] != 0 for w in early), "no vixy price (pre-2011) should leave vol in cash"
    orders = rebalancer.make_orders(wanted, Positions(), DAY, prices, 1000)
    assert len(orders) > 0, "no orders"
    sides = [o.quantity > 0 for o in orders]
    assert sides == sorted(sides), "sells must come before buys"
    broker = SimBroker()
    for fill in broker.send_orders(orders, DAY):
        close = prices[fill.instrument_id]
        assert (fill.price > close) if fill.quantity > 0 else (fill.price < close), "costs not charged"
        assert fill.commission > 0, "no commission"
    assert broker.send_orders(orders[:1], date(2020, 12, 25)) == [], "should not fill on a holiday"


def check_vix_breaker():
    """Quiet at VIX 18 (Jan 2020), fires on the Covid jump (24 Feb 2020)"""
    from RiskManagement.circuit_breaker import VixBreaker
    weights = pd.Series({"vol": 0.35, "equity": 0.35, "spread": 0.2, "reserve": 0.1})
    _, events = VixBreaker().apply(weights, date(2020, 1, 27))
    assert events == [], "fired on a small VIX move"
    new, events = VixBreaker().apply(weights, date(2020, 2, 24))
    assert len(events) > 0 and abs(new.sum() - 1) < 1e-9 and new["vol"] < weights["vol"], "didn't fire on Covid"


def check_engine():
    """Two weeks of the full daily loop on a temporary copy of trading.duckdb, books add up"""
    from Backtesting.sim_broker import SimBroker
    from ModelHome.engine import Engine
    temp = Path(tempfile.mkdtemp()) / "trading_check.duckdb"
    shutil.copy(db.trading_db_path(), temp)
    con = duckdb.connect(str(temp))
    try:
        settings = load("backtest.yaml")
        settings["run"]["start"] = "2020-02-18"
        days = [d.date() for d in get_prices("spy", "2020-02-18", "2020-03-03", as_of="2020-03-03").index]
        engine = Engine(SimBroker(), settings, "system_check", con)
        # fake regime (calm-bull every day), so this doesn't wait for real HMM fits
        moods = load("model.yaml", "moods")
        engine.saved_probs = pd.DataFrame([[1.0 if m == "calm-bull" else 0.0 for m in moods]] * len(days),
                                          index=pd.to_datetime(days), columns=moods)
        engine.run(days)

        # only this check's rows (the copy also holds your real runs)
        q = lambda sql: con.execute(sql.replace("WHERE", "WHERE run_id = 'system_check' AND")).fetchone()[0]
        last = q("SELECT max(as_of) FROM nav WHERE TRUE")
        nav = q(f"SELECT nav FROM nav WHERE sleeve = 'total' AND as_of = '{last}'")
        cash = q("SELECT sum(amount) FROM cash_ledger WHERE TRUE")
        held = q(f"SELECT sum(market_value) FROM positions WHERE as_of = '{last}'")
        assert abs(nav - (cash + held)) < 0.01, f"nav {nav} != cash {cash} + holdings {held}"
        assert q("SELECT count(*) FROM fills WHERE TRUE") > 0, "no trades"
        assert q("SELECT count(*) FROM risk_events WHERE TRUE") > 0, "breaker never fired in late Feb 2020"
    finally:
        con.close()
        shutil.rmtree(temp.parent, ignore_errors=True)


def check_regime_zscores():
    """z-scored features never use the future: the value on a past day is the same whether we look then or now"""
    from ModelHome.RegimeHMM.regime_model import _load
    feats = load("model.yaml", "regime_model")["stress_features"]
    then = _load(feats, "2008-01-01", "2008-10-15")
    now = _load(feats, "2008-01-01", "2026-11-11")
    same = now.loc[then.index]
    assert np.allclose(then.values, same.values, atol=1e-9), "z-scores changed when later data was added (look-ahead)"
    assert abs(then["log_vix"].loc["2008-10"].mean()) > 1, "Oct 2008 VIX should be far above its last year"


def check_splits():
    """A 1-for-4 reverse split: shares x 0.25, avg cost x 4, value unchanged"""
    from Portfolio.broker_interface import Fill
    from Portfolio.positions import Positions
    p = Positions()
    p.apply_fill(Fill("f", None, DAY, "vol", "vixy", "etf_standin", 400, 10.0, 0.0))
    p.apply_split("vixy", 0.25)
    h = p.holdings[("vol", "vixy", "etf_standin", None)]
    assert (h["quantity"], h["avg_cost"]) == (100, 40.0), f"got {h}"


def check_market_book():
    """The speed-up (prices in memory) gives exactly what the database gives, day by day, no future"""
    from Data.DataBase.access import get_dividends, get_series
    from Data.DataBase.market_book import MarketBook
    from Portfolio import valuation
    etfs = standin_ids(load("backtest.yaml", "standin_etfs"))
    book = MarketBook(etfs, ["vix", "tbill_3m"], date(2020, 1, 2), date(2020, 12, 31))
    for day in [date(2020, 3, 2), date(2020, 3, 16), date(2020, 3, 20), date(2020, 7, 3), date(2020, 12, 25)]:
        a, stale_a = valuation.price_holdings(etfs, day)
        b, stale_b = valuation.price_holdings(etfs, day, book)
        assert a.round(8).equals(b[a.index].round(8)) and stale_a == stale_b, f"prices differ on {day}"
        for sid in ["vix", "tbill_3m"]:
            start = pd.Timestamp(day) - pd.Timedelta(days=load("configs.yaml", "portfolio")["price_lookback_days"])
            direct = get_series(sid, start, day, as_of=day)[sid].dropna()
            assert np.allclose(direct.values, book.series(sid, day).values), f"{sid} differs on {day}"
        direct = get_dividends(etfs, day, day, as_of=day)
        assert dict(zip(direct["series_id"], direct["dividend"])) == book.dividends(etfs, day), f"dividends differ on {day}"


CHECKS = [check_config, check_database, check_regime_hmm, check_allocator, check_positions,
          check_ledger_and_valuation, check_rebalancer_and_broker, check_vix_breaker, check_regime_zscores, check_splits, check_market_book,
          check_engine]


if __name__ == "__main__":
    failed = 0
    for check in CHECKS:
        name = check.__name__.replace("check_", "")
        try:
            check()
            print(f"  OK    {name}")
        except Exception as e:
            failed += 1
            print(f"  FAIL  {name}: {type(e).__name__}: {e}")
    print("\nREADY TO GO" if failed == 0 else f"\nNOT READY ({failed} failed)")
    sys.exit(1 if failed else 0)
