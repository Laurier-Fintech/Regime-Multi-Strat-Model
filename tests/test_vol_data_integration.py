"""Real access.py queries against the production schema in an in-memory DB.

Only fixture setup writes SQL. The adapter reads through access.py, and the
real local market_data.duckdb/trading.duckdb files are never opened or changed.
"""

from datetime import timedelta
from math import sqrt
from pathlib import Path
import unittest
from unittest.mock import patch

import duckdb

from Data.DataBase import access
from Sleeves.base_sleeve import SleeveContext
from Sleeves.VolSleeve.market_data import DatabaseVolMarketData
from Sleeves.VolSleeve.rv_forecast import HARTrainingExample, HARVolatilityForecaster, RVForecast, RVInputs
from Sleeves.VolSleeve.signal import VolDirection, VolSignalConfig, VolSignalGenerator
from test_vol_market_data import AS_OF, DAY, calendar, config


class DatabaseMetadataIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.con = duckdb.connect(":memory:")
        schema = Path(__file__).resolve().parents[1] / "Data/DataBase/setup_run_once/schema_market.sql"
        self.con.execute(schema.read_text(encoding="utf-8"))
        self.connection_patch = patch.object(access, "_con", self.con)
        self.connection_patch.start()
        for window, value in ((1, 0.10), (5, 0.20), (22, 0.30)):
            feature = f"rv_spy_{window}d"
            self.con.execute("INSERT INTO meta.features VALUES (?, 'test RV', 'spy', 'annualised decimal', NULL)", [feature])
            self.con.execute("INSERT INTO features.series VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)", [feature, DAY, value, DAY])
            # A later correction to the SAME observation date must not leak.
            self.con.execute("INSERT INTO features.series VALUES (?, ?, 0.90, ?, CURRENT_TIMESTAMP)", [feature, DAY, DAY + timedelta(days=1)])
        for tenor, value in ((30, 0.20), (60, 0.30)):
            self.con.execute(
                "INSERT INTO raw.option_iv VALUES ('spx', ?, ?, 'pct_spot', 100, ?, 'bloomberg', ?, CURRENT_TIMESTAMP)",
                [DAY, tenor, value, DAY],
            )
        self.con.execute(
            "INSERT INTO raw.option_iv VALUES ('spx', ?, 30, 'pct_spot', 100, 0.80, 'bloomberg', ?, CURRENT_TIMESTAMP)",
            [DAY, DAY + timedelta(days=1)],
        )
        for known, bid in ((DAY, 10), (DAY + timedelta(days=1), 50)):
            self.con.execute(
                """INSERT INTO raw.option_quotes
                (underlying, obs_date, expiry, strike, call_put, contract_id, bid, ask, source, known_at, fetched_at)
                VALUES ('spx', ?, '2026-12-24', 6000, 'C', 'provider-contract', ?, ?, 'ibkr', ?, CURRENT_TIMESTAMP)""",
                [DAY, bid, bid + 2, known],
            )

    def tearDown(self):
        self.connection_patch.stop()
        self.con.close()

    def test_feature_metadata_mode_preserves_versions_and_legacy_wide_shape(self):
        wide = access.get_features(["rv_spy_1d"], DAY, as_of=DAY)
        self.assertEqual(list(wide.columns), ["rv_spy_1d"])
        self.assertAlmostEqual(wide.iloc[0, 0], 0.1)
        long = access.get_features(["rv_spy_1d"], DAY, as_of=DAY, include_metadata=True)
        self.assertEqual(set(long.columns), {"feature_id", "obs_date", "value", "known_at"})
        self.assertAlmostEqual(long.iloc[0].value, 0.1)
        self.assertEqual(long.iloc[0].known_at.date(), DAY)
        revised = access.get_features(["rv_spy_1d"], DAY, as_of=DAY + timedelta(days=1), include_metadata=True)
        self.assertAlmostEqual(revised.iloc[0].value, 0.9)
        self.assertEqual(revised.iloc[0].known_at.date(), DAY + timedelta(days=1))

    def test_iv_metadata_is_opt_in_and_never_selects_a_future_revision(self):
        legacy = access.get_option_iv("spx", DAY, as_of=DAY)
        self.assertNotIn("known_at", legacy.columns)
        rows = access.get_option_iv("spx", DAY, as_of=DAY, include_metadata=True)
        self.assertEqual(len(rows), 2)
        self.assertAlmostEqual(rows.loc[rows.tenor_days == 30, "iv"].iloc[0], 0.2)
        self.assertEqual(set(rows.known_at.dt.date), {DAY})
        later = access.get_option_iv("spx", DAY, as_of=DAY + timedelta(days=1), include_metadata=True)
        self.assertAlmostEqual(later.loc[later.tenor_days == 30, "iv"].iloc[0], 0.8)

    def test_chain_metadata_keeps_the_same_actual_contract_and_as_of_version(self):
        legacy = access.get_option_chain("spx", as_of=DAY)
        self.assertNotIn("known_at", legacy.columns)
        self.assertEqual(legacy.iloc[0].bid, 10)
        rows = access.get_option_chain("spx", as_of=DAY, include_metadata=True)
        self.assertEqual(rows.iloc[0].known_at.date(), DAY)
        self.assertEqual(rows.iloc[0].contract_id, "provider-contract")
        revised = access.get_option_chain("spx", as_of=DAY + timedelta(days=1), obs_date=DAY, include_metadata=True)
        self.assertEqual(revised.iloc[0].bid, 50)

    def test_filling_and_invalid_metadata_flags_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "forward filling"):
            access.get_features(["rv_spy_1d"], DAY, as_of=DAY, include_metadata=True, ffill_limit=1)
        with self.assertRaisesRegex(TypeError, "must be a bool"):
            access.get_option_iv("spx", DAY, as_of=DAY, include_metadata="yes")

    def test_full_reader_adapter_signal_path_uses_only_known_versions(self):
        adapter = DatabaseVolMarketData(config(), calendar=calendar())
        inputs = adapter.get_rv_inputs("spx", as_of=AS_OF)
        iv = adapter.get_implied_vol("spx", as_of=AS_OF, horizon_trading_days=22)
        chain = adapter.get_option_chain("spx", as_of=AS_OF)
        context = SleeveContext(AS_OF, 10_000, {
            "calm-bull": 0.6, "calm-bear": 0.2, "stressed-bull": 0.1, "stressed-bear": 0.1,
        })
        # Forecast output supplied here; historical HAR fitting is separate work.
        forecast = RVForecast(inputs.underlying, inputs.as_of, 22, 0.15)
        signal = VolSignalGenerator(VolSignalConfig(0.02, 0.5, timedelta(days=2))).generate(context, forecast, iv)
        self.assertAlmostEqual(inputs.rv_1d, 0.1)
        self.assertEqual(inputs.source_underlying, "spy")
        self.assertLess(iv.annualized_vol, 0.3)
        self.assertEqual(chain.iloc[0].bid, 10)
        self.assertEqual(signal.direction, VolDirection.SHORT_VOL)
        self.assertEqual(signal.horizon_trading_days, 22)

    def test_fitted_har_forecast_flows_from_real_reader_inputs_to_a_signal(self):
        examples = []
        for index in range(60):
            stamp = AS_OF - timedelta(days=180 - index)
            a = 0.08 + (index % 5) * 0.02
            b = 0.10 + ((index // 5) % 4) * 0.025
            c = 0.12 + ((index * 7) % 11) * 0.01
            # Synthetic historical outcomes with known variance coefficients.
            inputs = RVInputs("spx", stamp, a, b, c, source_underlying="spy")
            outcome = sqrt(0.002 + 0.2 * a * a + 0.3 * b * b + 0.4 * c * c)
            examples.append(HARTrainingExample(inputs, 22, outcome, stamp + timedelta(days=40)))
        model = HARVolatilityForecaster(min_samples=30)
        model.fit(examples, fitted_as_of=AS_OF - timedelta(days=1))
        adapter = DatabaseVolMarketData(config(), calendar=calendar())
        inputs = adapter.get_rv_inputs("spx", as_of=AS_OF)
        forecast = model.forecast(inputs, horizon_trading_days=22)
        iv = adapter.get_implied_vol("spx", as_of=AS_OF, horizon_trading_days=22)
        context = SleeveContext(AS_OF, 10_000, {
            "calm-bull": 0.6, "calm-bear": 0.2, "stressed-bull": 0.1, "stressed-bear": 0.1,
        })
        signal = VolSignalGenerator(VolSignalConfig(0.01, 0.5, timedelta(days=2))).generate(context, forecast, iv)
        self.assertAlmostEqual(forecast.annualized_vol, sqrt(0.052), places=12)
        self.assertEqual(signal.direction, VolDirection.LONG_VOL)
        self.assertLess(signal.edge, -0.01)

        # Continue through real chain access, exact canonical resolution,
        # whole-contract funding and delta hedging under generate_targets().
        self.con.execute(
            """INSERT INTO raw.option_quotes
            (underlying, obs_date, expiry, strike, call_put, contract_id, bid, ask, source, known_at, fetched_at)
            VALUES ('spx', ?, '2026-12-24', 6000, 'P', 'provider-put', 10, 12, 'ibkr', ?, CURRENT_TIMESTAMP)""",
            [DAY, DAY],
        )
        from Common.targeting import SelectionPolicy, MarketSnapshot, CapitalSnapshot, CapitalModel
        from Sleeves.VolSleeve.structures import StructureConfig, StructureType, OptionStructureBuilder, OptionContractRef
        from Sleeves.VolSleeve.delta_hedge import DeltaHedgeConfig, DeltaSnapshot, DeltaHedger
        from Sleeves.VolSleeve.vol_sleeve import VolSleeve, VolSleeveConfig
        policy = SelectionPolicy('USD', AS_OF.tzinfo, 1.0, .1, 10)
        capital = CapitalModel('USD', lambda i, t: CapitalSnapshot(i, t, 'USD',
            100 if i == 'canonical:hedge' else 1200.1, 100 if i == 'canonical:hedge' else 20000,
            'synthetic gross funding'))
        builder = OptionStructureBuilder(StructureConfig(StructureType.STRADDLE,
            StructureType.STRANGLE, 1, 60, policy),
            lambda r: OptionContractRef('canonical:' + r['call_put'], 100, 'USD', r['underlying'],
                r['expiry'], r['strike'], r['call_put'], 'spx:cash:european:100'),
            market_lookup=lambda u, t: MarketSnapshot(u, t, 'USD', 6000), capital_model=capital)
        hedge = DeltaHedger(DeltaHedgeConfig('USD', {'spx': 'canonical:hedge'}),
            lambda i, t: DeltaSnapshot(i, 'spx', t, 'USD',
                20 if i == 'canonical:hedge' else (500 if i == 'canonical:C' else -300)))
        sleeve = VolSleeve(VolSleeveConfig(('spx',), 22), market_data=adapter,
            forecasters={'spx': model}, signal_generator=VolSignalGenerator(
                VolSignalConfig(.01, .5, timedelta(days=2))), structure_builder=builder, delta_hedger=hedge)
        targets = sleeve.generate_targets(context)
        quantities = {t.instrument_id: t.target_quantity for t in targets}
        self.assertEqual(quantities, {'canonical:C': 2, 'canonical:P': 2, 'canonical:hedge': -20})
        self.assertLessEqual(capital.required(targets, AS_OF), context.capital_budget)


if __name__ == "__main__":
    unittest.main()
