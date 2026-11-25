from datetime import datetime

import pandas as pd

from Config.settings import load
from Data.DataBase.access import get_dividends, get_series
from Data.DataBase.db import append_rows
from ModelHome.allocator import Allocator
from ModelHome.RegimeHMM.regime_model import RegimeModel
from ModelHome.RegimeHMM.regime_store import load_regime_probs
from Portfolio import rebalancer, valuation
from Portfolio.ledger import Ledger
from Portfolio.positions import Positions
from RiskManagement.circuit_breaker import VixBreaker

# The daily loop. The SAME loop runs a backtest (SimBroker + past days) and live (IBKR + today).
# Only the broker and the list of days change.
# Sleeves OFF (backtest.yaml) --> buy the stand-in ETFs at the allocator's weights
# Sleeves ON                  --> Jacob's sleeves turn their budgets into option positions (not wired yet)

LOOKBACK_DAYS = load("configs.yaml", "portfolio")["price_lookback_days"]


class Engine:
    """Runs one day at a time. A class because it holds the book, the models and their memory"""

    def __init__(self, broker, settings, run_id, con):
        """
        Keyword arguments:
        broker -- SimBroker or the live broker, the engine doesn't care which
        settings -- backtest.yaml as a dict
        run_id -- from runs.start_run
        con -- open trading.duckdb connection (one writer for the whole run)
        """
        run = settings["run"]
        if run["sleeves_on"]:
            raise NotImplementedError("Sleeves ON isn't wired yet (Jacob's sleeves plug in here). Use sleeves_on: false.")

        self.broker = broker
        self.run_id = run_id
        self.con = con
        self.standin_etfs = settings["standin_etfs"]
        self.min_trade_value = settings["rebalance"]["min_trade_value"]

        # regime: a saved run is fast, the live model is slow (20+ min from 1995)
        if run["regime_run_id"]:
            self.saved_probs = load_regime_probs(run["regime_run_id"])
            self.regime = None
        else:
            self.saved_probs = None
            self.regime = RegimeModel()

        self.allocator = Allocator()
        self.breaker = VixBreaker()
        self.positions = Positions()
        self.ledger = Ledger(run["starting_cash"], pd.Timestamp(run["start"]).date())
        self.yesterday_nav = None
        self.saved = {}       # table name --> list of daily DataFrames, written once at the end

        # every ETF the stand-ins can hold ("cash" isn't an ETF)
        self.etfs = sorted({etf for etfs in self.standin_etfs.values() for etf in etfs if etf != "cash"})

    def _save(self, table, rows):
        """Keeps today's rows for one table, written to the database in flush()"""
        if rows is not None and len(rows) > 0:
            self.saved.setdefault(table, []).append(pd.DataFrame(rows))

    def flush(self):
        """Writes everything kept so far to trading.duckdb (one write per table, much faster than daily)"""
        for table, frames in self.saved.items():
            append_rows(self.con, table, pd.concat(frames, ignore_index=True))
        self.saved = {}

    def _regime(self, day):
        """Today's 4 mood probabilities, or None while the regime warms up"""
        if self.saved_probs is not None:
            stamp = pd.Timestamp(day)
            return self.saved_probs.loc[stamp] if stamp in self.saved_probs.index else None
        return self.regime.update(day)

    def _start_of_day(self, day):
        """Money that arrives before we trade: dividends on what we held overnight, one day of T-bill interest"""
        held = self.positions.held()
        if len(held) > 0:
            dividends = get_dividends(sorted(held["instrument_id"].unique()), day, day, as_of=day)
            for _, d in dividends.iterrows():
                for _, h in held[held["instrument_id"] == d["series_id"]].iterrows():
                    self.ledger.record_dividend(day, h["sleeve"], d["series_id"], h["quantity"], d["dividend"])

        start = pd.Timestamp(day) - pd.Timedelta(days=LOOKBACK_DAYS)
        rate = get_series("tbill_3m", start, day, as_of=day)["tbill_3m"].dropna()
        if len(rate) > 0:
            self.ledger.record_interest(day, rate.iloc[-1])

    def step(self, day):
        """One trading day: regime --> allocate --> breaker --> wanted --> orders --> broker --> book --> save"""
        self._start_of_day(day)

        # 1. Regime: 4 mood probabilities
        probs = self._regime(day)

        # 2. Allocate: weight per sleeve + reserve (None while warming up --> hold cash, no trades)
        weights = self.allocator.update(probs)

        held_ids = list(self.positions.held()["instrument_id"].unique())
        prices, stale = valuation.price_holdings(sorted(set(self.etfs) | set(held_ids)), day)

        if weights is not None:
            # 3. VIX breaker: trims short-vol weight on a VIX jump
            weights, events = self.breaker.apply(weights, day)

            # 4. Money per sleeve
            nav_total = valuation.nav(self.positions, self.ledger, prices).loc["total", "nav"]

            # 5. What we want to hold (sleeves off --> stand-in ETFs)
            wanted = rebalancer.weights_to_wanted(weights, nav_total, self.standin_etfs, prices)

            # 6. Risk: pass-through for v1.0 (exposure caps come later)
            approved = wanted

            # 7. Orders --> broker --> fills --> the book
            orders = rebalancer.make_orders(approved, self.positions, day, prices, self.min_trade_value)
            fills = self.broker.send_orders(orders, day)
            for fill in fills:
                self.positions.apply_fill(fill)
                self.ledger.record_fill(fill)

            self._save_trading(day, probs, weights, nav_total, events, approved, orders, fills)

        # 8. End of day: NAV and P&L
        nav_table = valuation.nav(self.positions, self.ledger, prices)
        pnl = valuation.daily_pnl(nav_table, self.yesterday_nav, self.ledger, day)
        self.yesterday_nav = nav_table

        # 9. Save the book
        self._save("positions", self.positions.to_rows(self.run_id, day, prices))
        self._save("cash_ledger", self.ledger.to_rows(self.run_id))
        self._save("nav", valuation.to_rows(self.run_id, day, nav_table, pnl))

    def _save_trading(self, day, probs, weights, nav_total, events, approved, orders, fills):
        """Today's decisions --> rows for regime_probs, allocations, risk_events, target_positions, orders, fills"""
        rid = self.run_id
        self._save("regime_probs", [{"run_id": rid, "as_of": day, "state": s, "probability": p}
                                    for s, p in probs.items()])
        self._save("allocations", [{"run_id": rid, "as_of": day, "sleeve": s, "target_weight": w,
                                    "capital": w * nav_total} for s, w in weights.items()])
        self._save("risk_events", [{"run_id": rid, "as_of": day, "event_no": i, "instrument_id": None, **e}
                                   for i, e in enumerate(events, start=1)])
        self._save("target_positions", [{"run_id": rid, "as_of": day, "sleeve": w["sleeve"],
                                         "instrument_id": w["instrument_id"], "strategy_id": w["strategy_id"],
                                         "group_id": w["group_id"] or "", "wanted_quantity": w["target_quantity"],
                                         "approved_quantity": w["target_quantity"]} for w in approved])
        filled = {f.order_id for f in fills}
        now = datetime.now()
        self._save("orders", [{"run_id": rid, "order_id": o.order_id, "as_of": day, "sleeve": o.sleeve,
                               "instrument_id": o.instrument_id, "strategy_id": o.strategy_id,
                               "group_id": o.group_id or "", "quantity": o.quantity, "order_type": o.order_type,
                               "status": "filled" if o.order_id in filled else "rejected", "created_at": now}
                              for o in orders])
        self._save("fills", [{"run_id": rid, "fill_id": f.fill_id, "order_id": f.order_id, "as_of": day,
                              "sleeve": f.sleeve, "instrument_id": f.instrument_id, "strategy_id": f.strategy_id,
                              "group_id": f.group_id or "", "quantity": f.quantity, "price": f.price,
                              "commission": f.commission, "fees": f.fees, "fill_type": f.fill_type,
                              "is_model_priced": f.is_model_priced, "filled_at": now} for f in fills])

    def run(self, days):
        """Every day in order, then write it all to the database"""
        for day in days:
            self.step(day)
        self.flush()
