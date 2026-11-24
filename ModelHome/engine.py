# The daily loop. The SAME loop runs a backtest (fake clock + SimBroker) and live (real clock + IBKR).
# Only the broker and the list of days change.
# If sleeves are OFF (backtest.yaml) --> buy the stand-in ETFs at the allocator's weights
# If sleeves are ON                  --> Jacob's sleeves turn their budgets into option positions


class Engine:
    def __init__(self, broker, settings, run_id):
        # settings = backtest.yaml (or a live config later)
        broker = broker                     # SimBroker or LiveBroker, engine doesn't care which
        regime = saved run (regime_store.load_regime_probs) if settings.regime_run_id
                 else RegimeModel()         # live / slow path
        allocator = Allocator()
        breaker = VixBreaker()
        positions = Positions()
        ledger = Ledger(settings.starting_cash)
        sleeves = None if sleeves off, else {"vol": VolSleeve(...), "equity": EquitySleeve(...)}   # Jacob's
        con = connect_trading()             # one writer for the whole run
        yesterday_nav = None

    def step(self, day):
        # 1. Regime: 4 mood probabilities (None while warming up)
        probs = saved row for day, or regime.update(day)

        # 2. Allocate: weight per sleeve + reserve
        weights = allocator.update(probs)
        if weights is None --> just value the book and save the day (hold cash), return

        # 3. VIX breaker: trim short-vol weight on a VIX jump
        weights, risk_events = breaker.apply(weights, day)

        # 4. Money per sleeve
        nav_today = valuation.nav(positions, ledger, day) total
        budgets = weights * nav_today

        # 5. What we want to hold
        if sleeves off:
            wanted = rebalancer.weights_to_wanted(weights, nav_today, standin_etfs, prices)
        else:
            for each sleeve: context = SleeveContext(as_of=day + market close time, capital_budget=budgets[sleeve],
                                                     regime_probabilities=probs)
                             wanted += sleeve.generate_targets(context)

        # 6. Risk: pass-through for v1.0 (exposure caps come later), save wanted vs approved
        approved = wanted

        # 7. Orders, send to the broker, apply the fills
        orders = rebalancer.make_orders(approved, positions, day, min_trade_value, prices)
        fills = broker.send_orders(orders, day)
        for each fill: positions.apply_fill(fill), ledger.record_fill(fill)

        # 8. End of day: interest on cash, dividends, then NAV and P&L
        ledger.record_interest(...), ledger.record_dividend(...) for anything paying today
        nav_table = valuation.nav(positions, ledger, day)
        pnl = valuation.daily_pnl(nav_table, yesterday_nav, today's deposits/transfers)
        yesterday_nav = nav_table

        # 9. Save the day to trading.duckdb
        append_rows: regime_probs, allocations, risk_events, target_positions,
                     orders, fills, positions, cash_ledger, nav

    def run(self, days):
        for day in days: step(day)
        # trading days = SPY's dates (like RegimeModel.run). Live: one call per day at the close
