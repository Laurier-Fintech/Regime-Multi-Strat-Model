"""Pricing benchmarks, arbitrage identities, early exercise and edge cases.

The two Haug cases are also published in QuantLib's europeanoption.cpp:
https://github.com/lballabio/QuantLib/blob/master/test-suite/europeanoption.cpp
The two-step CRR case below is independently worked out with rational numbers.
"""

from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
from math import exp, log, sqrt
import unittest

from Common.option_pricing import (
    ExerciseStyle, OptionInputs, OptionType, PricingModel, price_option,
)


def sample_inputs(**changes):
    inputs = OptionInputs(
        option_type=OptionType.CALL,
        exercise_style=ExerciseStyle.EUROPEAN,
        underlying_price=100.0, strike=100.0, time_to_expiry=1.0,
        volatility=0.20, risk_free_rate=0.05,
    )
    return replace(inputs, **changes)


class EuropeanPricingTests(unittest.TestCase):
    def test_black_scholes_reference_call_and_put(self):
        for option_type, expected in (
            (OptionType.CALL, 10.450583572185565),
            (OptionType.PUT, 5.573526022256971),
        ):
            with self.subTest(option_type=option_type):
                price = price_option(sample_inputs(option_type=option_type), model=PricingModel.BLACK_SCHOLES)
                self.assertAlmostEqual(price, expected, places=11)

    def test_haug_benchmarks_including_dividend_yield(self):
        for option_type, s, k, q, r, t, sigma, expected in (
            (OptionType.CALL, 60, 65, 0, 0.08, 0.25, 0.30, 2.1334),
            (OptionType.PUT, 100, 95, 0.05, 0.10, 0.50, 0.20, 2.4648),
        ):
            with self.subTest(option_type=option_type):
                inputs = sample_inputs(
                    option_type=option_type, underlying_price=s, strike=k,
                    dividend_yield=q, risk_free_rate=r, time_to_expiry=t, volatility=sigma,
                )
                self.assertAlmostEqual(price_option(inputs, model=PricingModel.BLACK_SCHOLES), expected, delta=1e-4)

    def test_black76_at_the_money_reference(self):
        self.assertAlmostEqual(
            price_option(sample_inputs(), model=PricingModel.BLACK_76),
            7.57708214642728, places=11,
        )

    def test_put_call_parity_across_spot_and_futures_models(self):
        for model in (PricingModel.BLACK_SCHOLES, PricingModel.BLACK_76):
            for s in (40, 100, 180):
                for r in (-0.02, 0.05):
                    with self.subTest(model=model, underlying=s, rate=r):
                        q = 0.03 if model == PricingModel.BLACK_SCHOLES else 0.0
                        call = sample_inputs(underlying_price=s, risk_free_rate=r, dividend_yield=q)
                        difference = price_option(call, model=model) - price_option(replace(call, option_type=OptionType.PUT), model=model)
                        expected = (
                            s * exp(-q) - 100 * exp(-r) if model == PricingModel.BLACK_SCHOLES
                            else exp(-r) * (s - 100)
                        )
                        self.assertAlmostEqual(difference, expected, places=11)

    def test_black76_equals_spot_model_when_dividend_yield_equals_rate(self):
        future = sample_inputs(underlying_price=115, strike=98, risk_free_rate=-0.01)
        spot = replace(future, dividend_yield=future.risk_free_rate)
        self.assertAlmostEqual(
            price_option(future, model=PricingModel.BLACK_76),
            price_option(spot, model=PricingModel.BLACK_SCHOLES), places=12,
        )

    def test_higher_volatility_increases_call_and_put_values(self):
        for model in (PricingModel.BLACK_SCHOLES, PricingModel.BLACK_76):
            for option_type in OptionType:
                with self.subTest(model=model, option_type=option_type):
                    inputs = sample_inputs(option_type=option_type)
                    self.assertGreater(
                        price_option(replace(inputs, volatility=0.4), model=model),
                        price_option(inputs, model=model),
                    )

    def test_deep_in_and_out_of_the_money_prices_obey_bounds(self):
        for s in (1, 100, 10_000):
            for option_type in OptionType:
                with self.subTest(underlying=s, option_type=option_type):
                    inputs = sample_inputs(underlying_price=s, option_type=option_type)
                    price = price_option(inputs, model=PricingModel.BLACK_SCHOLES)
                    lower = max(s - 100 * exp(-0.05), 0) if option_type == OptionType.CALL else max(100 * exp(-0.05) - s, 0)
                    upper = s if option_type == OptionType.CALL else 100 * exp(-0.05)
                    self.assertGreaterEqual(price + 1e-12, lower)
                    self.assertLessEqual(price, upper + 1e-12)


class BinomialPricingTests(unittest.TestCase):
    def test_two_step_american_put_matches_hand_calculation(self):
        # u=6/5, d=5/6, per-step growth=21/20, hence p=13/22.
        # At S=250/3, immediate put exercise (50/3) beats continuation.
        inputs = sample_inputs(
            option_type=OptionType.PUT, exercise_style=ExerciseStyle.AMERICAN,
            volatility=log(1.2) * sqrt(2), risk_free_rate=2 * log(1.05),
        )
        expected_american = float(Fraction(20, 21) * Fraction(9, 22) * Fraction(50, 3))
        expected_european = float(Fraction(20, 21) ** 2 * Fraction(9, 22) ** 2 * Fraction(275, 9))
        american = price_option(inputs, model=PricingModel.CRR, tree_steps=2)
        european = price_option(replace(inputs, exercise_style=ExerciseStyle.EUROPEAN), model=PricingModel.CRR, tree_steps=2)
        self.assertAlmostEqual(american, expected_american, places=11)
        self.assertAlmostEqual(european, expected_european, places=11)
        self.assertGreater(american, european)

    def test_european_tree_converges_toward_analytic_prices(self):
        for option_type in OptionType:
            with self.subTest(option_type=option_type):
                inputs = sample_inputs(option_type=option_type, dividend_yield=0.02)
                expected = price_option(inputs, model=PricingModel.BLACK_SCHOLES)
                coarse = price_option(inputs, model=PricingModel.CRR, tree_steps=51)
                fine = price_option(inputs, model=PricingModel.CRR, tree_steps=1001)
                self.assertLess(abs(fine - expected), abs(coarse - expected))
                self.assertAlmostEqual(fine, expected, delta=0.003)

    def test_non_dividend_american_call_equals_european_tree(self):
        inputs = sample_inputs()
        european = price_option(inputs, model=PricingModel.CRR)
        american = price_option(replace(inputs, exercise_style=ExerciseStyle.AMERICAN), model=PricingModel.CRR)
        self.assertAlmostEqual(european, american, places=11)

    def test_american_put_premium_and_immediate_exercise_bound(self):
        inputs = sample_inputs(option_type=OptionType.PUT, underlying_price=90)
        european = price_option(inputs, model=PricingModel.CRR)
        american = price_option(replace(inputs, exercise_style=ExerciseStyle.AMERICAN), model=PricingModel.CRR)
        self.assertGreater(american, european)
        self.assertGreaterEqual(american, 10)
        self.assertLessEqual(american, 100)

    def test_deep_itm_put_and_high_dividend_call_exercise_immediately(self):
        for inputs, expected in (
            (sample_inputs(option_type=OptionType.PUT, underlying_price=20, strike=40, risk_free_rate=0.10, volatility=0.15), 20),
            (sample_inputs(underlying_price=160, dividend_yield=0.30, volatility=0.10, risk_free_rate=0.01), 60),
        ):
            with self.subTest(option_type=inputs.option_type):
                american = replace(inputs, exercise_style=ExerciseStyle.AMERICAN)
                self.assertAlmostEqual(price_option(american, model=PricingModel.CRR), expected, places=10)

    def test_invalid_risk_neutral_probability_raises_instead_of_clipping(self):
        inputs = sample_inputs(volatility=0.0001, risk_free_rate=0.50)
        with self.assertRaisesRegex(ValueError, "increase tree_steps"):
            price_option(inputs, model=PricingModel.CRR, tree_steps=2)


class PricingBoundaryTests(unittest.TestCase):
    def test_expiry_returns_intrinsic_for_all_supported_models(self):
        for model in PricingModel:
            for option_type in OptionType:
                for s in (80, 100, 120):
                    with self.subTest(model=model, option_type=option_type, underlying=s):
                        inputs = sample_inputs(time_to_expiry=0, underlying_price=s, option_type=option_type)
                        expected = max(s - 100, 0) if option_type == OptionType.CALL else max(100 - s, 0)
                        self.assertEqual(price_option(inputs, model=model), expected)

    def test_zero_volatility_matches_discounted_deterministic_payoff(self):
        for option_type in OptionType:
            for model in PricingModel:
                with self.subTest(model=model, option_type=option_type):
                    inputs = sample_inputs(volatility=0, underlying_price=110, option_type=option_type)
                    expected_call = 10 * exp(-0.05) if model == PricingModel.BLACK_76 else 110 - 100 * exp(-0.05)
                    expected_put = 0.0
                    self.assertAlmostEqual(price_option(inputs, model=model), expected_call if option_type == OptionType.CALL else expected_put, places=11)

    def test_zero_volatility_american_put_can_exercise_now(self):
        inputs = sample_inputs(
            option_type=OptionType.PUT, exercise_style=ExerciseStyle.AMERICAN,
            underlying_price=80, volatility=0,
        )
        self.assertEqual(price_option(inputs, model=PricingModel.CRR), 20)

    def test_invalid_model_exercise_and_carry_are_rejected_even_at_expiry(self):
        for t in (0, 1):
            for model in (PricingModel.BLACK_SCHOLES, PricingModel.BLACK_76):
                with self.subTest(model=model, time=t):
                    with self.assertRaisesRegex(ValueError, "American exercise"):
                        price_option(sample_inputs(exercise_style=ExerciseStyle.AMERICAN, time_to_expiry=t), model=model)
            with self.assertRaisesRegex(ValueError, "carry is already"):
                price_option(sample_inputs(dividend_yield=0.01, time_to_expiry=t), model=PricingModel.BLACK_76)

    def test_invalid_numeric_inputs_are_rejected(self):
        for field in ("underlying_price", "strike", "time_to_expiry", "volatility", "risk_free_rate", "dividend_yield"):
            for value in (True, "0.2", None, float("nan"), float("inf")):
                with self.subTest(field=field, value=value):
                    with self.assertRaises((TypeError, ValueError)):
                        sample_inputs(**{field: value})
        for field, value in (("strike", 0), ("underlying_price", -1), ("time_to_expiry", -1), ("volatility", -0.01)):
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    sample_inputs(**{field: value})

    def test_explicit_enums_input_record_and_grid_are_required(self):
        with self.assertRaises(TypeError):
            sample_inputs(option_type="C")
        with self.assertRaises(TypeError):
            sample_inputs(exercise_style="american")
        with self.assertRaises(TypeError):
            price_option({}, model=PricingModel.BLACK_SCHOLES)
        with self.assertRaises(TypeError):
            price_option(sample_inputs(), model="black_scholes")
        for steps in (True, 2.5, 0, 1):
            with self.subTest(steps=steps):
                with self.assertRaises((TypeError, ValueError)):
                    price_option(sample_inputs(), model=PricingModel.CRR, tree_steps=steps)

    def test_extreme_exponents_raise_clear_errors(self):
        with self.assertRaisesRegex(ValueError, "floating-point range"):
            price_option(sample_inputs(risk_free_rate=-1000), model=PricingModel.BLACK_SCHOLES)
        with self.assertRaisesRegex(ValueError, "underflowed"):
            price_option(sample_inputs(risk_free_rate=1000), model=PricingModel.BLACK_76)

    def test_inputs_are_immutable(self):
        inputs = sample_inputs()
        with self.assertRaises(FrozenInstanceError):
            inputs.volatility = 0.9


if __name__ == "__main__":
    unittest.main()
