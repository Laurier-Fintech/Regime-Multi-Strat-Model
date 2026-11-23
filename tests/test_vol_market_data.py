"""Daily market adapter, source identity, tenor alignment and provenance tests."""

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from math import sqrt
import unittest
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pandas as pd

from Common.calendar import SessionCalendar
from Sleeves.VolSleeve.market_data import DatabaseVolMarketData, VolDataConfig, VolMarketSpec


DAY = date(2026, 11, 23)
AS_OF = datetime(2026, 11, 23, 21, tzinfo=timezone.utc)


def calendar():
    start = date(2026, 11, 1)
    holidays = {date(2026, 11, 26), date(2026, 12, 25), date(2027, 1, 1)}
    # Synthetic schedule for tests, with an explicit Thanksgiving closure.
    return SessionCalendar(tuple(
        start + timedelta(days=i) for i in range(110)
        if (start + timedelta(days=i)).weekday() < 5 and start + timedelta(days=i) not in holidays
    ))


def config(**changes):
    base = VolDataConfig(
        markets=(VolMarketSpec("spx", "spy", "spx", "Explicit SPY return-volatility proxy for this SPX research market."),),
        market_timezone=timezone.utc, available_time=time(21),
        max_observation_age=timedelta(days=5), iv_source="bloomberg",
    )
    return replace(base, **changes)


def features(observed=DAY, known=DAY):
    return pd.DataFrame([
        dict(feature_id=f"rv_spy_{n}d", obs_date=observed, known_at=known, value=value)
        for n, value in ((1, 0.10), (5, 0.20), (22, 0.30))
    ])


def iv_rows(observed=DAY, known=DAY, points=((30, 0.20), (60, 0.30))):
    return pd.DataFrame([
        dict(underlying="spx", obs_date=observed, known_at=known, source="bloomberg",
             moneyness_type="pct_spot", moneyness=100.0, tenor_days=tenor, iv=vol)
        for tenor, vol in points
    ])


def quotes():
    return pd.DataFrame([dict(
        underlying="spx", obs_date=DAY, known_at=DAY, source="ibkr",
        expiry=date(2026, 12, 24), strike=6000.0, call_put="C", bid=10.0, ask=12.0,
        contract_id="provider-id-kept-as-is",
    )])


class VolMarketAdapterTests(unittest.TestCase):
    def setUp(self):
        self.reader = Mock()
        self.reader.get_features.return_value = features()
        self.reader.get_option_iv.return_value = iv_rows()
        self.reader.get_option_chain.return_value = quotes()
        self.adapter = DatabaseVolMarketData(config(), calendar=calendar(), reader=self.reader)

    def test_rv_reads_exact_features_and_retains_explicit_proxy_provenance(self):
        inputs = self.adapter.get_rv_inputs("spx", as_of=AS_OF)
        self.assertEqual((inputs.rv_1d, inputs.rv_5d, inputs.rv_22d), (0.1, 0.2, 0.3))
        self.assertEqual(inputs.underlying, "spx")
        self.assertEqual(inputs.source_underlying, "spy")
        self.assertEqual(inputs.observed_at, AS_OF)
        self.assertEqual(inputs.known_at, AS_OF)
        args, kwargs = self.reader.get_features.call_args
        self.assertEqual(args[0], ["rv_spy_1d", "rv_spy_5d", "rv_spy_22d"])
        self.assertEqual(kwargs, {"as_of": DAY, "include_metadata": True})

    def test_latest_rv_row_must_be_complete_without_mixing_observation_dates(self):
        older = features(date(2026, 11, 20), date(2026, 11, 20))
        self.reader.get_features.return_value = pd.concat([older, features().iloc[:1]])
        with self.assertRaisesRegex(ValueError, "all three features"):
            self.adapter.get_rv_inputs("spx", as_of=AS_OF)

    def test_rv_records_the_latest_actual_availability_among_inputs(self):
        rows = features(date(2026, 11, 20), date(2026, 11, 20))
        rows.loc[1, "known_at"] = DAY
        self.reader.get_features.return_value = rows
        inputs = self.adapter.get_rv_inputs("spx", as_of=AS_OF)
        self.assertEqual(inputs.observed_at.date(), date(2026, 11, 20))
        self.assertEqual(inputs.known_at, AS_OF)

    def test_iv_interpolates_total_variance_to_the_actual_session_horizon(self):
        iv = self.adapter.get_implied_vol("spx", as_of=AS_OF, horizon_trading_days=22)
        self.assertEqual(iv.horizon_end, date(2026, 12, 24))
        # 22 sessions span 31 calendar days here, including the supplied holiday.
        expected = sqrt(((29 / 30) * (0.20 ** 2 * 30) + (1 / 30) * (0.30 ** 2 * 60)) / 31)
        self.assertAlmostEqual(iv.annualized_vol, expected, places=12)
        self.assertEqual(iv.tenor_days_used, (30, 60))
        self.assertEqual(iv.source_underlying, "spx")
        self.assertEqual(iv.source, "bloomberg")
        self.assertTrue(self.reader.get_option_iv.call_args.kwargs["include_metadata"])

    def test_stale_but_allowed_quote_is_shifted_to_the_forward_window(self):
        self.reader.get_option_iv.return_value = iv_rows(date(2026, 11, 20), DAY)
        iv = self.adapter.get_implied_vol("spx", as_of=AS_OF, horizon_trading_days=22)
        # Quote is 3 days old. End is 34 days from it, window length still 31.
        end_variance = 0.20 ** 2 * 30 * (26 / 30) + 0.30 ** 2 * 60 * (4 / 30)
        start_variance = 0.20 ** 2 * 3  # explicit zero-to-first-tenor anchor
        self.assertAlmostEqual(iv.annualized_vol, sqrt((end_variance - start_variance) / 31), places=12)
        self.assertEqual(iv.observed_at.date(), date(2026, 11, 20))
        self.assertEqual(iv.known_at.date(), DAY)

    def test_flat_curve_stays_flat_and_exact_tenor_needs_no_extra_node(self):
        self.reader.get_option_iv.return_value = iv_rows(points=((31, 0.25),))
        iv = self.adapter.get_implied_vol("spx", as_of=AS_OF, horizon_trading_days=22)
        self.assertAlmostEqual(iv.annualized_vol, 0.25)
        self.assertEqual(iv.tenor_days_used, (31,))

    def test_holiday_calendar_changes_horizon_without_a_252_to_365_shortcut(self):
        self.reader.get_option_iv.return_value = iv_rows(points=((1, 0.2), (10, 0.2)))
        iv = self.adapter.get_implied_vol("spx", as_of=AS_OF, horizon_trading_days=3)
        self.assertEqual(iv.horizon_end, date(2026, 11, 27))
        self.assertAlmostEqual(iv.annualized_vol, 0.2)

    def test_horizon_extrapolation_and_incomplete_calendars_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "no extrapolation"):
            self.adapter.get_implied_vol("spx", as_of=AS_OF, horizon_trading_days=3)
        with self.assertRaisesRegex(ValueError, "no extrapolation"):
            self.adapter.get_implied_vol("spx", as_of=AS_OF, horizon_trading_days=50)
        short = DatabaseVolMarketData(config(), calendar=SessionCalendar((DAY,)), reader=self.reader)
        with self.assertRaisesRegex(ValueError, "does not cover"):
            short.get_implied_vol("spx", as_of=AS_OF, horizon_trading_days=22)

    def test_invalid_or_decreasing_iv_curves_are_rejected(self):
        for points in (((30, 0.5), (60, 0.1)), ((30, -0.2),), ((30, float("nan")),), ((30.5, 0.2),), ((30, 0.2), (30, 0.3))):
            self.reader.get_option_iv.return_value = iv_rows(points=points)
            with self.subTest(points=points):
                with self.assertRaises(ValueError):
                    self.adapter.get_implied_vol("spx", as_of=AS_OF, horizon_trading_days=22)

    def test_latest_iv_date_requires_atm_and_must_not_mix_sources(self):
        for field, value in (("moneyness", 95), ("moneyness_type", "delta"), ("source", "other"), ("underlying", "ndx")):
            rows = iv_rows()
            rows[field] = value
            self.reader.get_option_iv.return_value = rows
            with self.subTest(field=field):
                with self.assertRaises((ValueError, LookupError)):
                    self.adapter.get_implied_vol("spx", as_of=AS_OF, horizon_trading_days=22)

    def test_known_at_metadata_is_required_not_invented_from_obs_date(self):
        for name, frame, call in (
            ("get_features", features(), lambda: self.adapter.get_rv_inputs("spx", as_of=AS_OF)),
            ("get_option_iv", iv_rows(), lambda: self.adapter.get_implied_vol("spx", as_of=AS_OF, horizon_trading_days=22)),
        ):
            getattr(self.reader, name).return_value = frame.drop(columns="known_at")
            with self.subTest(reader=name):
                with self.assertRaisesRegex(ValueError, "actual known_at"):
                    call()

    def test_reader_cannot_leak_future_versions_or_future_observations(self):
        for observed, known in ((DAY, DAY + timedelta(days=1)), (DAY + timedelta(days=1), DAY + timedelta(days=1))):
            self.reader.get_option_iv.return_value = iv_rows(observed, known)
            with self.subTest(observed=observed, known=known):
                with self.assertRaisesRegex(ValueError, "as-of window"):
                    self.adapter.get_implied_vol("spx", as_of=AS_OF, horizon_trading_days=22)

    def test_early_day_weekend_and_unknown_market_do_not_trigger_reads(self):
        for stamp in (AS_OF - timedelta(minutes=1), AS_OF - timedelta(days=1)):
            with self.subTest(stamp=stamp):
                with self.assertRaises(ValueError):
                    self.adapter.get_rv_inputs("spx", as_of=stamp)
        with self.assertRaises(KeyError):
            self.adapter.get_rv_inputs("ndx", as_of=AS_OF)
        self.reader.get_features.assert_not_called()

    def test_market_timezone_controls_the_date_instead_of_utc_date(self):
        eastern = timezone(timedelta(hours=-5))  # fixed November offset for this test
        adapter = DatabaseVolMarketData(config(market_timezone=eastern, available_time=time(16)), calendar=calendar(), reader=self.reader)
        later_utc = datetime(2026, 11, 24, 1, tzinfo=timezone.utc)
        inputs = adapter.get_rv_inputs("spx", as_of=later_utc)
        self.assertEqual(inputs.observed_at.date(), DAY)
        self.assertEqual(self.reader.get_features.call_args.kwargs["as_of"], DAY)

    def test_observation_age_is_not_reset_by_a_new_revision(self):
        adapter = DatabaseVolMarketData(config(max_observation_age=timedelta(days=2)), calendar=calendar(), reader=self.reader)
        self.reader.get_option_iv.return_value = iv_rows(date(2026, 11, 20), DAY)
        with self.assertRaisesRegex(ValueError, "stale"):
            adapter.get_implied_vol("spx", as_of=AS_OF, horizon_trading_days=22)

    def test_adapter_age_uses_elapsed_time_across_daylight_saving(self):
        earlier = date(2026, 10, 30)
        schedule = SessionCalendar((earlier,) + calendar().session_dates)
        adapter = DatabaseVolMarketData(config(
            market_timezone=ZoneInfo("America/New_York"), available_time=time(16),
            max_observation_age=timedelta(hours=72),
        ), calendar=schedule, reader=self.reader)
        self.reader.get_features.return_value = features(earlier, earlier)
        stamp = datetime(2026, 11, 2, 16, tzinfo=ZoneInfo("America/New_York"))
        with self.assertRaisesRegex(ValueError, "stale"):
            adapter.get_rv_inputs("spx", as_of=stamp)

    def test_empty_reads_raise_instead_of_supplying_zero_values(self):
        self.reader.get_features.return_value = features().iloc[:0]
        self.reader.get_option_iv.return_value = iv_rows().iloc[:0]
        self.reader.get_option_chain.return_value = quotes().iloc[:0]
        for call in (
            lambda: self.adapter.get_rv_inputs("spx", as_of=AS_OF),
            lambda: self.adapter.get_implied_vol("spx", as_of=AS_OF, horizon_trading_days=22),
            lambda: self.adapter.get_option_chain("spx", as_of=AS_OF),
        ):
            with self.assertRaises(LookupError):
                call()

    def test_actual_chain_is_copied_with_metadata_and_provider_ids_preserved(self):
        original = quotes()
        self.reader.get_option_chain.return_value = original
        result = self.adapter.get_option_chain("spx", as_of=AS_OF)
        self.assertEqual(result.iloc[0].contract_id, "provider-id-kept-as-is")
        self.assertIn("known_at", result.columns)
        result.loc[0, "bid"] = 0
        self.assertEqual(original.iloc[0].bid, 10)

    def test_bad_contract_quotes_and_duplicate_contracts_are_rejected(self):
        for field, value in (("bid", -1), ("ask", 9), ("strike", 0), ("call_put", "X"), ("underlying", "spy"), ("source", None), ("expiry", date(2026, 11, 20))):
            rows = quotes()
            rows[field] = value
            self.reader.get_option_chain.return_value = rows
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    self.adapter.get_option_chain("spx", as_of=AS_OF)
        self.reader.get_option_chain.return_value = pd.concat([quotes(), quotes()])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.adapter.get_option_chain("spx", as_of=AS_OF)

    def test_proxy_mapping_and_daily_configuration_must_be_explicit(self):
        with self.assertRaisesRegex(ValueError, "proxy_reason"):
            VolMarketSpec("spx", "spy", "spx")
        for changes in ({"markets": ()}, {"markets": config().markets * 2}, {"available_time": time(21, tzinfo=timezone.utc)}, {"max_observation_age": timedelta(days=-1)}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    config(**changes)


class SessionCalendarTests(unittest.TestCase):
    def test_dates_are_sorted_unique_immutable_inputs(self):
        for dates in ((), (DAY, DAY), (DAY + timedelta(days=1), DAY)):
            with self.subTest(dates=dates):
                with self.assertRaises(ValueError):
                    SessionCalendar(dates)
        with self.assertRaises(TypeError):
            SessionCalendar((AS_OF,))

    def test_session_count_and_decision_session_are_required(self):
        for count in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                calendar().next_sessions(DAY, count)
        with self.assertRaises(ValueError):
            calendar().next_sessions(date(2026, 11, 26), 1)


if __name__ == "__main__":
    unittest.main()
