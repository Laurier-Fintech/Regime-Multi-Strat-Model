"""Regime boundary checks; run with unittest discovery from the repo root."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from math import fsum
import unittest
from unittest.mock import Mock

from Sleeves.base_sleeve import SleeveContext
from Sleeves.regime_inputs import REGIME_STATES, RegimeProbabilities
from Sleeves.EquitySleeve.equity_sleeve import EquitySleeve, EquitySleeveConfig
from Sleeves.VolSleeve.rv_forecast import RVForecaster
from Sleeves.VolSleeve.vol_sleeve import VolSleeve, VolSleeveConfig


def model_output():
    # Deliberately not an independent stress/direction distribution: summing
    # joint cells must work without making any additional independence claim.
    return dict(zip(REGIME_STATES, (0.10, 0.20, 0.30, 0.40)))


def context_for(probabilities):
    return SleeveContext(
        as_of=datetime(2026, 11, 23, 21, tzinfo=timezone.utc),
        capital_budget=10_000,
        regime_probabilities=probabilities,
    )


class RegimeProbabilitiesTests(unittest.TestCase):
    def test_joint_states_produce_correct_stress_and_direction_totals(self):
        regime = RegimeProbabilities.from_mapping(model_output())
        self.assertAlmostEqual(regime.calm, 0.30)
        self.assertAlmostEqual(regime.stressed, 0.70)
        self.assertAlmostEqual(regime.bull, 0.40)
        self.assertAlmostEqual(regime.bear, 0.60)
        self.assertAlmostEqual(regime.calm + regime.stressed, 1.0)
        self.assertAlmostEqual(regime.bull + regime.bear, 1.0)

    def test_labels_determine_values_regardless_of_insertion_order(self):
        expected = RegimeProbabilities.from_mapping(model_output())
        reordered = dict(reversed(list(model_output().items())))
        self.assertEqual(RegimeProbabilities.from_mapping(reordered), expected)

    def test_each_certain_state_including_zero_probabilities_is_valid(self):
        for state in REGIME_STATES:
            with self.subTest(state=state):
                probabilities = {name: int(name == state) for name in REGIME_STATES}
                regime = RegimeProbabilities.from_mapping(probabilities)
                self.assertEqual(regime.calm, float(state.startswith("calm-")))
                self.assertEqual(regime.stressed, float(state.startswith("stressed-")))
                self.assertEqual(regime.bull, float(state.endswith("-bull")))
                self.assertEqual(regime.bear, float(state.endswith("-bear")))

    def test_missing_state_is_rejected_even_if_remaining_mass_is_one(self):
        probabilities = dict(zip(REGIME_STATES[:3], (0.2, 0.3, 0.5)))
        with self.assertRaisesRegex(ValueError, "missing=.*stressed-bear"):
            RegimeProbabilities.from_mapping(probabilities)

    def test_unexpected_and_legacy_labels_are_rejected(self):
        for probabilities in (
            {},
            {"calm": 0.3, "stress": 0.7},
            {**model_output(), "stress": 0.0},
            {**model_output(), 1: 0.0},
        ):
            with self.subTest(probabilities=probabilities):
                with self.assertRaisesRegex(ValueError, "Expected exactly"):
                    RegimeProbabilities.from_mapping(probabilities)

    def test_unavailable_warmup_result_has_explicit_error(self):
        with self.assertRaisesRegex(ValueError, "warming up"):
            RegimeProbabilities.from_mapping(None)

    def test_non_mapping_inputs_are_rejected(self):
        for probabilities in ([], list(model_output().items()), "calm-bull"):
            with self.subTest(probabilities=probabilities):
                with self.assertRaisesRegex(TypeError, "must be a mapping"):
                    RegimeProbabilities.from_mapping(probabilities)

    def test_non_numeric_and_boolean_probabilities_are_rejected(self):
        for value in (True, False, "0.1", None, 0.1 + 0j):
            with self.subTest(value=value):
                probabilities = model_output()
                probabilities["calm-bull"] = value
                with self.assertRaisesRegex(TypeError, "must be a real number"):
                    RegimeProbabilities.from_mapping(probabilities)

    def test_non_finite_and_out_of_range_probabilities_are_rejected(self):
        for value in (float("nan"), float("inf"), -float("inf"), -0.1, 1.1):
            with self.subTest(value=value):
                probabilities = model_output()
                probabilities["calm-bull"] = value
                with self.assertRaisesRegex(ValueError, "finite and in"):
                    RegimeProbabilities.from_mapping(probabilities)

    def test_materially_wrong_totals_are_never_normalized(self):
        for values in ((0, 0, 0, 0), (0.1, 0.2, 0.3, 0.3), (0.25,) * 3 + (0.2500001,)):
            with self.subTest(values=values):
                with self.assertRaisesRegex(ValueError, "sum to 1"):
                    RegimeProbabilities(*values)

    def test_rounding_error_is_normalized_in_both_directions(self):
        for rounding_error in (-5e-9, 5e-9):
            with self.subTest(rounding_error=rounding_error):
                regime = RegimeProbabilities(0.4, 0.6 + rounding_error, 0.0, 0.0)
                self.assertAlmostEqual(fsum(regime.as_mapping().values()), 1.0)
                self.assertTrue(0 <= regime.calm <= 1)
                self.assertEqual(regime.stressed, 0.0)

    def test_direct_construction_also_validates_and_is_immutable(self):
        with self.assertRaises(TypeError):
            RegimeProbabilities(True, 0, 0, 0)
        regime = RegimeProbabilities.from_mapping(model_output())
        with self.assertRaises(FrozenInstanceError):
            regime.calm_bull = 0.9
        exported = regime.as_mapping()
        exported["calm-bull"] = 0.9
        self.assertAlmostEqual(regime.calm_bull, 0.1)


class SleeveContextIntegrationTests(unittest.TestCase):
    def test_context_exposes_matching_joint_and_marginal_views(self):
        context = context_for(model_output())
        self.assertEqual(dict(context.regime_probabilities), context.market_regime.as_mapping())
        self.assertAlmostEqual(context.market_regime.calm, 0.3)
        self.assertAlmostEqual(context.market_regime.stressed, 0.7)

    def test_original_mapping_cannot_change_a_decision(self):
        probabilities = model_output()
        context = context_for(probabilities)
        probabilities["calm-bull"] = 0.9
        self.assertAlmostEqual(context.regime_probabilities["calm-bull"], 0.1)
        self.assertAlmostEqual(context.market_regime.calm, 0.3)
        with self.assertRaises(TypeError):
            context.regime_probabilities["calm-bull"] = 0.9
        with self.assertRaises(FrozenInstanceError):
            context.market_regime = RegimeProbabilities(1, 0, 0, 0)

    def test_context_rejects_invalid_regimes_at_construction(self):
        for probabilities in (None, {"calm": 1.0}, {**model_output(), "unused": 0.0}):
            with self.subTest(probabilities=probabilities):
                with self.assertRaises(ValueError):
                    context_for(probabilities)

    def test_existing_timestamp_and_budget_checks_still_apply(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            SleeveContext(datetime(2026, 11, 23), 100, model_output())
        for budget in (-1, float("inf"), float("nan")):
            with self.subTest(budget=budget):
                with self.assertRaisesRegex(ValueError, "capital_budget"):
                    SleeveContext(datetime.now(timezone.utc), budget, model_output())
        self.assertEqual(
            SleeveContext(datetime.now(timezone.utc), 0, model_output()).capital_budget, 0
        )

    def test_equity_config_uses_universes_without_legacy_regime_settings(self):
        config = EquitySleeveConfig(("spx",), ("tqqq",), 0.5)
        self.assertEqual(config.premium_underlying_ids, ("tqqq",))
        for universes in (((), ("tqqq",)), (("spx",), ("tqqq", "tqqq"))):
            with self.subTest(universes=universes):
                with self.assertRaises(ValueError):
                    EquitySleeveConfig(*universes, 0.5)

    def test_equity_direction_gate_requires_a_valid_joint_probability(self):
        for value in (0, -1, 1.1, True, float('nan')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                EquitySleeveConfig(('spx',), ('tqqq',), value)

    def test_vol_zero_budget_requests_flatten_without_data_reads(self):
        builder = Mock()
        builder.capital_model.base_currency = 'USD'
        hedger = Mock()
        hedger.base_currency = 'USD'
        vol = VolSleeve(
            VolSleeveConfig(("spx",), 22),
            market_data=Mock(), forecasters={"spx": Mock(spec=RVForecaster)},
            signal_generator=Mock(), structure_builder=builder, delta_hedger=hedger,
        )
        context = SleeveContext(datetime.now(timezone.utc), 0, model_output())
        self.assertEqual(vol.generate_targets(context), [])
        vol._market_data.get_rv_inputs.assert_not_called()


if __name__ == "__main__":
    unittest.main()
