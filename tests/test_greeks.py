"""Independent price-bump checks of analytic Greeks and tree convergence."""

from dataclasses import FrozenInstanceError, replace
from math import exp
import unittest

from Common.greeks import calculate_greeks, cash_delta_for_one_percent_move
from Common.option_pricing import ExerciseStyle, OptionInputs, OptionType, PricingModel, price_option


def sample_inputs(**changes):
    inputs = OptionInputs(
        option_type=OptionType.CALL, exercise_style=ExerciseStyle.EUROPEAN,
        underlying_price=100, strike=100, time_to_expiry=1,
        volatility=0.2, risk_free_rate=0.05,
    )
    return replace(inputs, **changes)


class AnalyticGreekTests(unittest.TestCase):
    def test_black_scholes_reference_greeks(self):
        greeks = calculate_greeks(sample_inputs(), model=PricingModel.BLACK_SCHOLES)
        for name, expected in (
            ("delta", 0.6368306511756191), ("gamma", 0.018762017345846895),
            ("vega", 37.52403469169379), ("theta", -6.414027546438197),
            ("rho", 53.232481545376345),
        ):
            with self.subTest(greek=name):
                self.assertAlmostEqual(getattr(greeks, name), expected, places=10)

    def test_analytic_greeks_match_independent_price_bumps(self):
        for model in (PricingModel.BLACK_SCHOLES, PricingModel.BLACK_76):
            for option_type in OptionType:
                with self.subTest(model=model, option_type=option_type):
                    inputs = sample_inputs(
                        option_type=option_type, underlying_price=103, strike=97,
                        time_to_expiry=0.7, risk_free_rate=-0.01,
                        dividend_yield=0.02 if model == PricingModel.BLACK_SCHOLES else 0,
                    )
                    greeks = calculate_greeks(inputs, model=model)
                    base_price = price_option(inputs, model=model)

                    def bump(field, amount):
                        return price_option(replace(inputs, **{field: getattr(inputs, field) + amount}), model=model)

                    ds = 0.001
                    up, down = bump("underlying_price", ds), bump("underlying_price", -ds)
                    self.assertAlmostEqual(greeks.delta, (up - down) / (2 * ds), delta=1e-7)
                    self.assertAlmostEqual(greeks.gamma, (up + down - 2 * base_price) / ds ** 2, delta=1e-6)
                    for greek, field, sign in (("vega", "volatility", 1), ("rho", "risk_free_rate", 1), ("theta", "time_to_expiry", -1)):
                        step = 1e-5
                        expected = sign * (bump(field, step) - bump(field, -step)) / (2 * step)
                        self.assertAlmostEqual(getattr(greeks, greek), expected, delta=1e-6)

    def test_call_put_greek_parity_with_dividends(self):
        inputs = sample_inputs(dividend_yield=0.03)
        call = calculate_greeks(inputs, model=PricingModel.BLACK_SCHOLES)
        put = calculate_greeks(replace(inputs, option_type=OptionType.PUT), model=PricingModel.BLACK_SCHOLES)
        self.assertAlmostEqual(call.delta - put.delta, exp(-0.03), places=12)
        self.assertAlmostEqual(call.gamma, put.gamma, places=12)
        self.assertAlmostEqual(call.vega, put.vega, places=12)
        self.assertAlmostEqual(call.rho - put.rho, 100 * exp(-0.05), places=10)

    def test_black76_rho_holds_futures_fixed(self):
        inputs = sample_inputs()
        price = price_option(inputs, model=PricingModel.BLACK_76)
        greeks = calculate_greeks(inputs, model=PricingModel.BLACK_76)
        self.assertAlmostEqual(greeks.rho, -inputs.time_to_expiry * price, places=12)
        self.assertLess(greeks.rho, 0)

    def test_reporting_units_and_immutability(self):
        greeks = calculate_greeks(sample_inputs(), model=PricingModel.BLACK_SCHOLES)
        self.assertAlmostEqual(greeks.vega_per_vol_point, 0.3752403469169379)
        self.assertAlmostEqual(greeks.theta_per_calendar_day, greeks.theta / 365)
        self.assertAlmostEqual(greeks.rho_per_rate_point, greeks.rho * 0.01)
        self.assertEqual(greeks.model, PricingModel.BLACK_SCHOLES)
        with self.assertRaises(FrozenInstanceError):
            greeks.delta = 0


class TreeGreekTests(unittest.TestCase):
    def test_european_tree_greeks_converge_to_analytic_values(self):
        for option_type in OptionType:
            with self.subTest(option_type=option_type):
                inputs = sample_inputs(option_type=option_type, dividend_yield=0.02)
                expected = calculate_greeks(inputs, model=PricingModel.BLACK_SCHOLES)
                tree = calculate_greeks(inputs, model=PricingModel.CRR, tree_steps=1001)
                for name, tolerance in (("delta", 0.001), ("gamma", 0.0001), ("vega", 0.05), ("theta", 0.03), ("rho", 0.05)):
                    with self.subTest(greek=name):
                        self.assertAlmostEqual(getattr(tree, name), getattr(expected, name), delta=tolerance)

    def test_american_put_has_sensible_signs_and_converging_exposure(self):
        inputs = sample_inputs(option_type=OptionType.PUT, exercise_style=ExerciseStyle.AMERICAN, underlying_price=95)
        coarse = calculate_greeks(inputs, model=PricingModel.CRR, tree_steps=301)
        fine = calculate_greeks(inputs, model=PricingModel.CRR, tree_steps=601)
        self.assertTrue(-1 <= fine.delta <= 0)
        self.assertGreater(fine.gamma, 0)
        self.assertGreater(fine.vega, 0)
        self.assertLess(fine.rho, 0)
        self.assertAlmostEqual(coarse.delta, fine.delta, delta=0.01)
        self.assertAlmostEqual(coarse.gamma, fine.gamma, delta=0.001)

    def test_immediate_exercise_greeks_match_intrinsic_payoff(self):
        inputs = sample_inputs(
            option_type=OptionType.PUT, exercise_style=ExerciseStyle.AMERICAN,
            underlying_price=20, strike=40, risk_free_rate=0.10, volatility=0.15,
        )
        greeks = calculate_greeks(inputs, model=PricingModel.CRR, tree_steps=101)
        self.assertAlmostEqual(greeks.delta, -1, places=10)
        for name in ("gamma", "theta", "vega", "rho"):
            self.assertAlmostEqual(getattr(greeks, name), 0, places=8)

    def test_small_volatility_caps_the_bump_without_crossing_zero(self):
        inputs = sample_inputs(volatility=0.00005, risk_free_rate=0)
        greeks = calculate_greeks(inputs, model=PricingModel.CRR, tree_steps=31)
        self.assertGreater(greeks.vega, 0)


class GreekBoundaryAndExposureTests(unittest.TestCase):
    def test_expiry_and_zero_volatility_raise_instead_of_fabricating_greeks(self):
        for model in PricingModel:
            for changes in ({"time_to_expiry": 0}, {"volatility": 0}):
                with self.subTest(model=model, changes=changes):
                    with self.assertRaisesRegex(ValueError, "positive time_to_expiry and volatility"):
                        calculate_greeks(sample_inputs(**changes), model=model)

    def test_tree_bumps_must_be_finite_positive_and_representable(self):
        for field in ("volatility_bump", "rate_bump"):
            for value in (0, -0.1, True, float("nan"), 1e-300):
                with self.subTest(field=field, value=value):
                    with self.assertRaises((TypeError, ValueError)):
                        calculate_greeks(sample_inputs(), model=PricingModel.CRR, **{field: value})

    def test_cash_delta_includes_explicit_multiplier_and_fx(self):
        # Per contract: delta .5 * price 80 * 1% * multiplier 50 * FX 1.35.
        amount = cash_delta_for_one_percent_move(0.5, 80, multiplier=50, fx_rate=1.35)
        self.assertAlmostEqual(amount, 27)
        self.assertAlmostEqual(-3 * amount, -81)  # three short contracts
        self.assertAlmostEqual(cash_delta_for_one_percent_move(-0.5, 80, multiplier=50), -20)
        self.assertEqual(cash_delta_for_one_percent_move(0, 80, multiplier=50), 0)

    def test_cash_delta_matches_a_small_reprice_to_first_order(self):
        inputs = sample_inputs()
        greeks = calculate_greeks(inputs, model=PricingModel.BLACK_SCHOLES)
        predicted_one_percent = cash_delta_for_one_percent_move(greeks.delta, 100, multiplier=100)
        change = 0.0001
        exact = 100 * (
            price_option(replace(inputs, underlying_price=100 * (1 + change)), model=PricingModel.BLACK_SCHOLES)
            - price_option(inputs, model=PricingModel.BLACK_SCHOLES)
        )
        self.assertAlmostEqual(exact, predicted_one_percent * change / 0.01, delta=0.0002)

    def test_cash_delta_rejects_invalid_units(self):
        for changes in (
            {"delta": True}, {"delta": float("nan")}, {"underlying_price": 0},
            {"multiplier": 0}, {"multiplier": -100}, {"fx_rate": -1},
        ):
            arguments = dict(delta=0.5, underlying_price=100, multiplier=100, fx_rate=1)
            arguments.update(changes)
            with self.subTest(changes=changes):
                with self.assertRaises((ValueError, TypeError)):
                    cash_delta_for_one_percent_move(**arguments)


if __name__ == "__main__":
    unittest.main()
