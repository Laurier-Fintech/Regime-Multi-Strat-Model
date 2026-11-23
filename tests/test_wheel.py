"""Wheel decisions from confirmed snapshots; no market data or broker needed."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import unittest

from Sleeves.base_sleeve import SleeveContext
from Sleeves.EquitySleeve.wheel import (
    EquityHolding, EquityInstrument, EquityLifecycleEvent, EquityOpenOrder,
    EquityPortfolioSnapshot, WheelConfig, WheelManager, WheelStage,
)


AS_OF = datetime(2026, 11, 23, 21, tzinfo=timezone.utc)


def context_for(probabilities=(0.60, 0.20, 0.10, 0.10), budget=10_000):
    return SleeveContext(
        AS_OF, budget,
        dict(zip(("calm-bull", "calm-bear", "stressed-bull", "stressed-bear"), probabilities)),
    )


def holding(instrument, quantity, strategy="wheel", group=None):
    return EquityHolding(instrument, quantity, strategy, group)


def order(order_id, instrument, quantity, strategy="wheel"):
    return EquityOpenOrder(order_id, instrument, quantity, strategy)


def snapshot(holdings=(), orders=(), events=(), cash=10_000):
    return EquityPortfolioSnapshot("equity", AS_OF, "USD", cash, holdings, orders, events)


class Instruments:
    """A small test adapter with explicit canonical IDs and deliverables."""

    def __init__(self):
        self.rows = {
            "TQQQ": EquityInstrument("TQQQ", "tqqq", "etf", 1, "USD"),
            "TQQQ_P": EquityInstrument("TQQQ_P", "tqqq", "option", 100, "USD", "P", 100),
            "TQQQ_C": EquityInstrument("TQQQ_C", "tqqq", "option", 100, "USD", "C", 100),
            "TQQQ_C50": EquityInstrument("TQQQ_C50", "tqqq", "option", 100, "USD", "C", 50),
            "SPX_P": EquityInstrument("SPX_P", "spx", "option", 100, "USD", "P"),
        }

    def get_instrument(self, instrument_id):
        return self.rows[instrument_id]


class WheelTests(unittest.TestCase):
    def setUp(self):
        self.instruments = Instruments()
        # Test values only; no production calibration is implied.
        self.config = WheelConfig(
            calm_entry_probability=0.60,
            stress_exit_probability=0.50,
            calm_bull_entry_probability=0.40,
        )
        self.manager = WheelManager(self.config, self.instruments)
        self.context = context_for()

    def inspect(self, book, context=None):
        return self.manager.inspect(context or self.context, "tqqq", book)

    def plan(self, book, context=None):
        context = context or self.context
        return self.manager.plan(context, self.inspect(book, context))


class WheelClassificationTests(WheelTests):
    def test_all_confirmed_stages(self):
        for rows, expected in (
            ((), WheelStage.FLAT),
            ((holding("TQQQ_P", -2),), WheelStage.SHORT_PUTS),
            ((holding("TQQQ", 100),), WheelStage.HOLDING_SHARES),
            ((holding("TQQQ", 100), holding("TQQQ_C", -1)), WheelStage.COVERED_CALLS),
            ((holding("TQQQ", 100), holding("TQQQ_P", -1)), WheelStage.MIXED),
            ((holding("TQQQ", 100), holding("TQQQ_P", -1), holding("TQQQ_C", -1)), WheelStage.MIXED),
        ):
            with self.subTest(stage=expected, holdings=rows):
                self.assertEqual(self.inspect(snapshot(rows)).stage, expected)

    def test_stress_spread_and_other_underlying_do_not_become_wheel_inventory(self):
        rows = (
            holding("TQQQ_P", -1, "stress_put_spread", "spread-1"),
            holding("TQQQ_P", 1, "stress_put_spread", "spread-2"),
            holding("SPX_P", 1, "stress_put_spread"),
        )
        state = self.inspect(snapshot(rows))
        self.assertEqual(state.stage, WheelStage.FLAT)
        self.assertEqual(state.short_put_contracts, 0)

    def test_zero_holding_rows_are_ignored(self):
        self.assertEqual(self.inspect(snapshot((holding("TQQQ_P", 0),))).stage, WheelStage.FLAT)

    def test_multiple_attributed_slices_are_summed(self):
        state = self.inspect(snapshot((holding("TQQQ_P", -1, group="a"), holding("TQQQ_P", -2, group="b"))))
        self.assertEqual(state.short_put_contracts, 3)

    def test_partial_fills_do_not_become_full_fills(self):
        book = snapshot(
            (holding("TQQQ", 200), holding("TQQQ_C", -1)),
            (order("remaining-call", "TQQQ_C", -1),),
        )
        state = self.inspect(book)
        self.assertEqual(state.short_call_contracts, 1)
        self.assertEqual(state.available_call_shares, 0)
        self.assertEqual(state.pending_order_ids, ("remaining-call",))
        self.assertFalse(self.plan(book).allow_covered_calls)

    def test_assignment_and_call_away_are_applied_by_portfolio_only(self):
        event = EquityLifecycleEvent("assignment-1", "TQQQ_P", "assignment", AS_OF - timedelta(hours=1), AS_OF)
        book = snapshot((holding("TQQQ", 100), holding("TQQQ_P", -1)), events=(event,))
        before = book
        first = self.inspect(book)
        self.assertEqual(first.stage, WheelStage.MIXED)
        self.assertEqual(first.share_quantity, 100)
        self.assertEqual(self.inspect(book), first)
        self.assertEqual(book, before)
        called_away = replace(event, event_id="call-away", instrument_id="TQQQ_C")
        self.assertEqual(self.inspect(snapshot(events=(called_away,))).stage, WheelStage.FLAT)

    def test_pending_share_purchase_does_not_create_coverage(self):
        book = snapshot(orders=(order("buy-shares", "TQQQ", 100),))
        state = self.inspect(book)
        self.assertEqual(state.stage, WheelStage.FLAT)
        self.assertEqual(state.available_call_shares, 0)
        self.assertFalse(self.plan(book).allow_new_puts)
        with self.assertRaisesRegex(ValueError, "confirmed share coverage"):
            self.inspect(replace(book, open_orders=book.open_orders + (order("sell-call", "TQQQ_C", -1),)))

    def test_unsupported_wheel_holdings_raise(self):
        for rows in ((holding("TQQQ", -100),), (holding("TQQQ_P", 1),), (holding("TQQQ_C", 1),)):
            with self.subTest(holdings=rows):
                with self.assertRaises(ValueError):
                    self.inspect(snapshot(rows))


class WheelCoverageTests(WheelTests):
    def test_actual_deliverables_determine_coverage_instead_of_assuming_100(self):
        book = snapshot((holding("TQQQ", 150), holding("TQQQ_C50", -2)))
        state = self.inspect(book)
        self.assertEqual(state.call_share_obligation, 100)
        self.assertEqual(state.available_call_shares, 50)
        self.assertTrue(self.plan(book).allow_covered_calls)

    def test_held_and_pending_calls_each_reserve_coverage(self):
        book = snapshot(
            (holding("TQQQ", 300), holding("TQQQ_C", -1)),
            (order("sell-call", "TQQQ_C", -1),),
        )
        self.assertEqual(self.inspect(book).available_call_shares, 100)

    def test_pending_share_sales_reduce_eligible_shares(self):
        book = snapshot((holding("TQQQ", 200),), (order("sell-shares", "TQQQ", -50),))
        self.assertEqual(self.inspect(book).available_call_shares, 150)

    def test_pending_call_buy_does_not_release_existing_coverage(self):
        book = snapshot(
            (holding("TQQQ", 100), holding("TQQQ_C", -1)),
            (order("close-call", "TQQQ_C", 1),),
        )
        self.assertEqual(self.inspect(book).available_call_shares, 0)
        with self.assertRaisesRegex(ValueError, "confirmed share coverage"):
            self.inspect(replace(book, open_orders=book.open_orders + (order("sell-shares", "TQQQ", -100),)))

    def test_uncovered_held_or_pending_calls_are_rejected(self):
        for book in (
            snapshot((holding("TQQQ_C", -1),)),
            snapshot((holding("TQQQ", 99), holding("TQQQ_C", -1))),
            snapshot((holding("TQQQ", 100),), (order("sell-calls", "TQQQ_C", -2),)),
        ):
            with self.subTest(book=book):
                with self.assertRaisesRegex(ValueError, "confirmed share coverage"):
                    self.inspect(book)

    def test_other_strategies_cannot_reuse_physical_shares(self):
        book = snapshot((holding("TQQQ", 100), holding("TQQQ_C", -1, "other")))
        self.assertEqual(self.inspect(book).available_call_shares, 0)
        self.assertFalse(self.plan(book).allow_covered_calls)
        own_and_foreign_shares = replace(book, holdings=book.holdings + (holding("TQQQ", 100, "other"),))
        self.assertEqual(self.inspect(own_and_foreign_shares).available_call_shares, 100)

    def test_other_strategy_pending_sales_reserve_global_shares(self):
        book = snapshot((holding("TQQQ", 100),), (order("other-sale", "TQQQ", -50, "other"),))
        state = self.inspect(book)
        self.assertEqual(state.available_call_shares, 50)
        self.assertEqual(state.wheel_order_ids, ())
        self.assertFalse(self.plan(book).allow_covered_calls)

    def test_unfilled_long_calls_are_not_physical_share_coverage(self):
        book = snapshot((holding("TQQQ_C", 1, "other"), holding("TQQQ_C", -1)))
        with self.assertRaisesRegex(ValueError, "confirmed share coverage"):
            self.inspect(book)

    def test_missing_share_deliverables_and_currency_conversion_are_not_guessed(self):
        for changes in ({"deliverable_shares": None}, {"currency": "CAD"}):
            self.instruments.rows["TQQQ_C"] = replace(Instruments().rows["TQQQ_C"], **changes)
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    self.inspect(snapshot((holding("TQQQ", 100), holding("TQQQ_C", -1))))

    def test_orders_cannot_overshoot_short_option_or_share_inventory(self):
        for book in (
            snapshot(orders=(order("buy-call", "TQQQ_C", 1),)),
            snapshot((holding("TQQQ_P", -1),), (order("buy-put", "TQQQ_P", 2),)),
            snapshot((holding("TQQQ", 50),), (order("sell-shares", "TQQQ", -100),)),
        ):
            with self.subTest(book=book):
                with self.assertRaises(ValueError):
                    self.inspect(book)


class WheelDecisionTests(WheelTests):
    def test_wheel_cycle_waits_for_portfolio_confirmation_at_each_step(self):
        def decision(day, rows=(), orders=(), events=()):
            context = replace(self.context, as_of=AS_OF + timedelta(days=day))
            book = replace(snapshot(rows, orders, events), as_of=context.as_of)
            state = self.inspect(book, context)
            return state, self.manager.plan(context, state)

        _, flat_plan = decision(0)
        self.assertTrue(flat_plan.allow_new_puts)
        pending_put, pending_plan = decision(1, orders=(order("put-entry", "TQQQ_P", -1),))
        self.assertEqual(pending_put.stage, WheelStage.FLAT)
        self.assertFalse(pending_plan.allow_new_puts)
        filled_put, _ = decision(2, (holding("TQQQ_P", -1),))
        self.assertEqual(filled_put.stage, WheelStage.SHORT_PUTS)
        assigned_at = AS_OF + timedelta(days=3)
        assignment = EquityLifecycleEvent("put-assignment", "TQQQ_P", "assignment", assigned_at, assigned_at)
        assigned, call_plan = decision(3, (holding("TQQQ", 100),), events=(assignment,))
        self.assertEqual(assigned.stage, WheelStage.HOLDING_SHARES)
        self.assertEqual(assigned.share_quantity, 100)
        self.assertTrue(call_plan.allow_covered_calls)
        pending_call, _ = decision(4, (holding("TQQQ", 100),), (order("call-entry", "TQQQ_C", -1),))
        self.assertEqual(pending_call.stage, WheelStage.HOLDING_SHARES)
        self.assertEqual(pending_call.available_call_shares, 0)
        covered, _ = decision(5, (holding("TQQQ", 100), holding("TQQQ_C", -1)))
        self.assertEqual(covered.stage, WheelStage.COVERED_CALLS)
        called_at = AS_OF + timedelta(days=6)
        called_away = EquityLifecycleEvent("call-assignment", "TQQQ_C", "assignment", called_at, called_at)
        flat_again, restart = decision(6, events=(called_away,))
        self.assertEqual(flat_again.stage, WheelStage.FLAT)
        self.assertTrue(restart.allow_new_puts)

    def test_flat_calm_bull_book_can_propose_puts(self):
        plan = self.plan(snapshot())
        self.assertTrue(plan.allow_new_puts)
        self.assertFalse(plan.allow_covered_calls)
        self.assertFalse(plan.exit_requested)

    def test_equal_calm_totals_with_different_direction_produce_different_put_decisions(self):
        bullish = context_for((0.60, 0.20, 0.10, 0.10))
        bearish = context_for((0.20, 0.60, 0.10, 0.10))
        self.assertAlmostEqual(bullish.market_regime.calm, bearish.market_regime.calm)
        self.assertTrue(self.plan(snapshot(), bullish).allow_new_puts)
        self.assertFalse(self.plan(snapshot(), bearish).allow_new_puts)

    def test_threshold_equality_is_inclusive(self):
        boundary = context_for((0.40, 0.20, 0.20, 0.20))
        self.assertTrue(self.plan(snapshot(), boundary).allow_new_puts)
        stress_boundary = context_for((0.40, 0.10, 0.25, 0.25))
        self.assertTrue(self.plan(snapshot((holding("TQQQ", 100),)), stress_boundary).exit_requested)

    def test_no_cash_or_capital_blocks_new_puts(self):
        for cash in (0, -100):
            with self.subTest(cash=cash):
                self.assertFalse(self.plan(snapshot(cash=cash)).allow_new_puts)
        self.assertFalse(self.plan(snapshot(), context_for(budget=0)).allow_new_puts)

    def test_existing_puts_are_not_doubled_and_blocked_entries_are_not_exits(self):
        book = snapshot((holding("TQQQ_P", -1),))
        plan = self.plan(book)
        self.assertFalse(plan.allow_new_puts)
        self.assertFalse(plan.exit_requested)
        neutral = context_for((0.30, 0.25, 0.25, 0.20))
        hold_plan = self.plan(snapshot((holding("TQQQ", 100),)), neutral)
        self.assertFalse(hold_plan.allow_covered_calls)
        self.assertFalse(hold_plan.exit_requested)

    def test_confirmed_shares_allow_calls_including_after_partial_assignment(self):
        for rows in (
            (holding("TQQQ", 100),),
            (holding("TQQQ", 100), holding("TQQQ_P", -1)),
        ):
            with self.subTest(holdings=rows):
                plan = self.plan(snapshot(rows))
                self.assertTrue(plan.allow_covered_calls)
                self.assertFalse(plan.allow_new_puts)

    def test_calm_bear_blocks_new_puts_but_can_manage_calls_against_owned_shares(self):
        bearish = context_for((0.20, 0.60, 0.10, 0.10))
        plan = self.plan(snapshot((holding("TQQQ", 100),)), bearish)
        self.assertTrue(plan.allow_covered_calls)
        self.assertFalse(plan.allow_new_puts)
        self.assertFalse(plan.exit_requested)

    def test_pending_orders_pause_entries_without_being_treated_as_fills(self):
        for pending in (order("sell-put", "TQQQ_P", -1), order("other", "TQQQ", 1, "other")):
            with self.subTest(order=pending):
                plan = self.plan(snapshot(orders=(pending,)))
                self.assertFalse(plan.allow_new_puts)
                self.assertFalse(plan.allow_covered_calls)
                self.assertFalse(plan.exit_requested)

    def test_stress_exit_has_priority_and_preserves_closing_orders(self):
        # Deliberately overlapping gates to verify that exit wins.
        manager = WheelManager(WheelConfig(0.2, 0.4, 0.2), self.instruments)
        context = context_for((0.3, 0.2, 0.3, 0.2))
        book = snapshot(
            (holding("TQQQ_P", -2),),
            (order("new-put", "TQQQ_P", -1), order("close-put", "TQQQ_P", 1)),
        )
        state = manager.inspect(context, "tqqq", book)
        plan = manager.plan(context, state)
        self.assertTrue(plan.exit_requested)
        self.assertFalse(plan.allow_new_puts)
        self.assertFalse(plan.allow_covered_calls)
        self.assertEqual(plan.cancel_order_ids, ("new-put",))

    def test_stressed_bull_and_stressed_bear_both_trigger_defensive_exit(self):
        for probabilities in ((0.2, 0.1, 0.6, 0.1), (0.2, 0.1, 0.1, 0.6)):
            with self.subTest(probabilities=probabilities):
                self.assertTrue(self.plan(snapshot((holding("TQQQ", 100),)), context_for(probabilities)).exit_requested)

    def test_zero_budget_requests_exit_and_cancel_pending_entries(self):
        book = snapshot(orders=(order("buy-shares", "TQQQ", 100),))
        plan = self.plan(book, context_for(budget=0))
        self.assertTrue(plan.exit_requested)
        self.assertEqual(plan.cancel_order_ids, ("buy-shares",))
        self.assertFalse(plan.allow_covered_calls)

    def test_stress_with_no_wheel_exposure_does_not_close_another_strategy(self):
        book = snapshot(orders=(order("other-buy", "TQQQ", 100, "other"),))
        plan = self.plan(book, context_for((0.1, 0.1, 0.4, 0.4)))
        self.assertFalse(plan.exit_requested)
        self.assertEqual(plan.cancel_order_ids, ())

    def test_state_cannot_be_forged_or_reused_at_a_different_cutoff(self):
        state = self.inspect(snapshot((holding("TQQQ", 100),)))
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.manager.plan(self.context, replace(state, available_call_shares=1000))
        later = replace(self.context, as_of=AS_OF + timedelta(days=1))
        with self.assertRaisesRegex(ValueError, "as_of exactly"):
            self.manager.plan(later, state)

    def test_decisions_are_deterministic_and_do_not_mutate_the_book(self):
        book = snapshot((holding("TQQQ", 100),))
        state = self.inspect(book)
        plan = self.manager.plan(self.context, state)
        self.assertEqual(self.manager.plan(self.context, state), plan)
        self.assertEqual(state.share_quantity, 100)
        with self.assertRaises(FrozenInstanceError):
            plan.exit_requested = True


class WheelValidationTests(WheelTests):
    def test_snapshot_cutoff_and_sleeve_must_match(self):
        for changes in ({"sleeve_id": "vol"}, {"as_of": AS_OF - timedelta(seconds=1)}, {"as_of": AS_OF + timedelta(seconds=1)}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    self.inspect(replace(snapshot(), **changes))

    def test_future_events_are_rejected(self):
        event = EquityLifecycleEvent("future", "TQQQ_P", "assignment", AS_OF, AS_OF + timedelta(seconds=1))
        with self.assertRaisesRegex(ValueError, "after the decision cutoff"):
            self.inspect(snapshot(events=(event,)))

    def test_duplicate_holdings_orders_and_events_are_rejected(self):
        event = EquityLifecycleEvent("event", "TQQQ_P", "expiry", AS_OF, AS_OF)
        for changes in (
            {"holdings": (holding("TQQQ", 50), holding("TQQQ", 50))},
            {"open_orders": (order("same", "TQQQ_P", -1), order("same", "TQQQ_P", -1))},
            {"lifecycle_events": (event, event)},
        ):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValueError, "Duplicate"):
                    replace(snapshot(), **changes)

    def test_contract_lookup_must_return_exact_identity(self):
        self.instruments.rows["TQQQ"] = replace(self.instruments.rows["TQQQ"], instrument_id="OTHER")
        with self.assertRaisesRegex(ValueError, "exact canonical"):
            self.inspect(snapshot((holding("TQQQ", 100),)))
        with self.assertRaises(KeyError):
            self.inspect(snapshot((holding("MISSING", 100),)))

    def test_invalid_record_metadata_is_rejected(self):
        constructors = (
            lambda: holding("TQQQ", True),
            lambda: holding("TQQQ", 1, strategy=""),
            lambda: order("id", "TQQQ", 0),
            lambda: order("id", "TQQQ", 0.5),
            lambda: replace(snapshot(), as_of=AS_OF.replace(tzinfo=None)),
            lambda: replace(snapshot(), holdings=[]),
            lambda: replace(snapshot(), available_cash=float("nan")),
            lambda: EquityLifecycleEvent("e", "TQQQ", "assignment", AS_OF, AS_OF - timedelta(seconds=1)),
            lambda: EquityInstrument("bad", "tqqq", "option", 100, "USD", "C", 12.5),
        )
        for constructor in constructors:
            with self.subTest(constructor=constructor):
                with self.assertRaises((TypeError, ValueError)):
                    constructor()

    def test_config_requires_valid_explicit_directional_gate(self):
        for value in (0, 1.1, True, float("inf")):
            with self.subTest(value=value):
                with self.assertRaises((TypeError, ValueError)):
                    WheelConfig(0.6, 0.5, value)
        with self.assertRaises(ValueError):
            WheelConfig(0.6, 0.5, 0.4, strategy_id="")
        with self.assertRaises(TypeError):
            WheelManager(self.config, object())

    def test_strategy_id_is_explicitly_configurable(self):
        manager = WheelManager(replace(self.config, strategy_id="tqqq_wheel"), self.instruments)
        book = snapshot((holding("TQQQ_P", -1, "tqqq_wheel"),))
        self.assertEqual(manager.inspect(self.context, "tqqq", book).stage, WheelStage.SHORT_PUTS)


if __name__ == "__main__":
    unittest.main()
