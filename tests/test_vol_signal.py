"""Volatility signal policy and rejection of unavailable/misaligned inputs."""

from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
import unittest
from zoneinfo import ZoneInfo

from Sleeves.base_sleeve import SleeveContext
from Sleeves.VolSleeve.rv_forecast import RVForecast, RVInputs
from Sleeves.VolSleeve.signal import ImpliedVolSnapshot, VolDirection, VolSignalConfig, VolSignalGenerator


AS_OF = datetime(2026, 11, 23, 21, tzinfo=timezone.utc)


def context_for(probabilities=(0.6, 0.2, 0.1, 0.1)):
    return SleeveContext(AS_OF, 10_000, dict(zip(
        ("calm-bull", "calm-bear", "stressed-bull", "stressed-bear"), probabilities,
    )))


class VolSignalTests(unittest.TestCase):
    def setUp(self):
        self.context = context_for()
        self.forecast = RVForecast("spx", AS_OF, 22, 0.20)
        self.iv = ImpliedVolSnapshot("spx", AS_OF, AS_OF, 22, 0.25)
        self.config = VolSignalConfig(0.02, 0.5, timedelta(days=3))
        self.generator = VolSignalGenerator(self.config)

    def test_rich_cheap_and_neutral_edges(self):
        for implied, expected in ((0.25, VolDirection.SHORT_VOL), (0.15, VolDirection.LONG_VOL), (0.21, VolDirection.NEUTRAL)):
            with self.subTest(implied=implied):
                signal = self.generator.generate(self.context, self.forecast, replace(self.iv, annualized_vol=implied))
                self.assertEqual(signal.direction, expected)
                self.assertAlmostEqual(signal.edge, implied - 0.20)
                self.assertEqual(signal.underlying, "spx")
                self.assertEqual(signal.as_of, AS_OF)
                self.assertTrue(signal.reason)

    def test_inclusive_thresholds_handle_subtraction_roundoff(self):
        for implied, direction in ((0.22, VolDirection.SHORT_VOL), (0.18, VolDirection.LONG_VOL)):
            with self.subTest(implied=implied):
                signal = self.generator.generate(self.context, self.forecast, replace(self.iv, annualized_vol=implied))
                self.assertEqual(signal.direction, direction)

    def test_tiny_positive_threshold_does_not_turn_zero_edge_into_a_trade(self):
        generator = VolSignalGenerator(replace(self.config, min_edge=1e-14))
        signal = generator.generate(self.context, self.forecast, replace(self.iv, annualized_vol=0.20))
        self.assertEqual(signal.direction, VolDirection.NEUTRAL)

    def test_stress_veto_is_inclusive_and_keeps_observed_edge(self):
        signal = self.generator.generate(context_for((0.4, 0.1, 0.3, 0.2)), self.forecast, self.iv)
        self.assertEqual(signal.direction, VolDirection.NEUTRAL)
        self.assertAlmostEqual(signal.edge, 0.05)
        self.assertIn("vetoed", signal.reason)

    def test_both_stress_directions_count_for_a_volatility_veto(self):
        for probabilities in ((0.1, 0.1, 0.7, 0.1), (0.1, 0.1, 0.1, 0.7)):
            with self.subTest(probabilities=probabilities):
                self.assertEqual(self.generator.generate(context_for(probabilities), self.forecast, self.iv).direction, VolDirection.NEUTRAL)

    def test_stress_does_not_force_long_vol_but_does_not_block_a_cheap_signal(self):
        stressed = context_for((0.1, 0.1, 0.4, 0.4))
        for implied, expected in ((0.20, VolDirection.NEUTRAL), (0.25, VolDirection.NEUTRAL), (0.15, VolDirection.LONG_VOL)):
            with self.subTest(implied=implied):
                self.assertEqual(self.generator.generate(stressed, self.forecast, replace(self.iv, annualized_vol=implied)).direction, expected)

    def test_calm_direction_does_not_change_a_non_directional_vol_signal(self):
        bullish = self.generator.generate(context_for((0.6, 0.2, 0.1, 0.1)), self.forecast, self.iv)
        bearish = self.generator.generate(context_for((0.2, 0.6, 0.1, 0.1)), self.forecast, self.iv)
        self.assertEqual(bullish.direction, bearish.direction)

    def test_market_horizon_and_decision_time_must_match(self):
        for changes in ({"underlying": "ndx"}, {"horizon_trading_days": 5}, {"as_of": AS_OF - timedelta(days=1)}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    self.generator.generate(self.context, replace(self.forecast, **changes), self.iv)

    def test_future_known_or_future_observed_iv_is_rejected(self):
        for iv in (
            replace(self.iv, known_at=AS_OF + timedelta(seconds=1)),
            replace(self.iv, observed_at=AS_OF + timedelta(seconds=1), known_at=AS_OF + timedelta(seconds=1)),
        ):
            with self.subTest(iv=iv):
                with self.assertRaisesRegex(ValueError, "not available"):
                    self.generator.generate(self.context, self.forecast, iv)

    def test_freshness_uses_observation_age_not_revision_date(self):
        old = replace(self.iv, observed_at=AS_OF - timedelta(days=4), known_at=AS_OF)
        with self.assertRaisesRegex(ValueError, "stale"):
            self.generator.generate(self.context, self.forecast, old)
        boundary = replace(self.iv, observed_at=AS_OF - timedelta(days=3))
        self.assertEqual(self.generator.generate(self.context, self.forecast, boundary).direction, VolDirection.SHORT_VOL)

    def test_elapsed_horizon_end_is_rejected(self):
        old = replace(self.iv, observed_at=AS_OF - timedelta(days=1), horizon_end=AS_OF.date())
        with self.assertRaisesRegex(ValueError, "end after"):
            self.generator.generate(self.context, self.forecast, old)

    def test_freshness_measures_elapsed_hours_across_daylight_saving(self):
        eastern = ZoneInfo("America/New_York")
        stamp = datetime(2026, 11, 1, 16, tzinfo=eastern)
        observed = datetime(2026, 10, 30, 16, tzinfo=eastern)
        context = replace(self.context, as_of=stamp)
        forecast = replace(self.forecast, as_of=stamp)
        iv = replace(self.iv, observed_at=observed, known_at=observed)
        generator = VolSignalGenerator(replace(self.config, max_iv_age=timedelta(hours=48)))
        # The fall clock change makes this 49 elapsed hours, not 48.
        with self.assertRaisesRegex(ValueError, "stale"):
            generator.generate(context, forecast, iv)

    def test_invalid_iv_records_and_configuration_fail_at_construction(self):
        for changes in (
            {"annualized_vol": -0.1}, {"annualized_vol": float("nan")},
            {"observed_at": AS_OF.replace(tzinfo=None)},
            {"known_at": AS_OF - timedelta(seconds=1)}, {"horizon_trading_days": True},
            {"horizon_end": datetime(2026, 12, 1)}, {"source": ""},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises((TypeError, ValueError)):
                    replace(self.iv, **changes)
        for changes in (
            {"min_edge": 0}, {"min_edge": True}, {"stress_block_short_probability": 0},
            {"stress_block_short_probability": float("nan")},
            {"max_iv_age": timedelta(days=-1)}, {"max_iv_age": 3},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises((TypeError, ValueError)):
                    replace(self.config, **changes)

    def test_invalid_input_types_and_immutable_decisions(self):
        for inputs in ((None, self.forecast, self.iv), (self.context, None, self.iv), (self.context, self.forecast, None)):
            with self.subTest(inputs=inputs):
                with self.assertRaises(TypeError):
                    self.generator.generate(*inputs)
        signal = self.generator.generate(self.context, self.forecast, self.iv)
        with self.assertRaises(FrozenInstanceError):
            signal.edge = 0

    def test_rv_provenance_is_optional_but_consistent_when_supplied(self):
        legacy = RVInputs("spx", AS_OF, 0.2, 0.2, 0.2)
        sourced = replace(legacy, source_underlying="spy", observed_at=AS_OF - timedelta(days=3), known_at=AS_OF)
        self.assertEqual(sourced.source_underlying, "spy")
        for changes in ({"known_at": None}, {"known_at": AS_OF + timedelta(seconds=1)}, {"known_at": AS_OF - timedelta(days=4)}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    replace(sourced, **changes)


if __name__ == "__main__":
    unittest.main()
