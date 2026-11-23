"""Synthetic contracts, funding, hedges and both public sleeve pipelines.

No provider ID is treated as a canonical ID. Reserves deliberately use gross
funding and no offsets. These fixtures are not a trading/backtest data set.
"""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import unittest
from unittest.mock import Mock

import pandas as pd

from Common.targeting import (SelectionPolicy, MarketSnapshot, CapitalSnapshot,
    CapitalModel, chain_rows, combine)
from Sleeves.base_sleeve import SleeveContext, TargetPosition
from Sleeves.EquitySleeve.wheel import (EquityInstrument, EquityHolding,
    EquityOpenOrder, EquityPortfolioSnapshot, WheelConfig, WheelManager)
from Sleeves.EquitySleeve.calm_premium import CalmPremiumConfig, CalmPremiumBuilder, PendingOrdersError
from Sleeves.EquitySleeve.stress_put_spreads import StressPutSpreadConfig, StressPutSpreadBuilder
from Sleeves.EquitySleeve.equity_sleeve import EquitySleeve, EquitySleeveConfig
from Sleeves.VolSleeve.structures import StructureConfig, StructureType, OptionStructureBuilder, OptionContractRef
from Sleeves.VolSleeve.delta_hedge import DeltaHedgeConfig, DeltaSnapshot, DeltaHedger
from Sleeves.VolSleeve.signal import VolDirection, VolSignal, VolSignalConfig, VolSignalGenerator, ImpliedVolSnapshot
from Sleeves.VolSleeve.rv_forecast import RVInputs, RVForecast, RVForecaster
from Sleeves.VolSleeve.vol_sleeve import VolSleeveConfig, VolSleeve

AS_OF = datetime(2026, 11, 23, 21, tzinfo=timezone.utc)
DAY, END = AS_OF.date(), date(2026, 12, 24)
POLICY = SelectionPolicy('USD', timezone.utc, 1.0, 0.1, 20)


def context(budget=10000, states=(.8, .1, .05, .05)):
    return SleeveContext(AS_OF, budget, dict(zip(
        ('calm-bull', 'calm-bear', 'stressed-bull', 'stressed-bear'), states)))


def chain(underlying='x', expiry=END):
    rows = []
    for k in (90, 95, 100, 105, 110):
        for cp in ('P', 'C'):
            bid = {90: 1., 95: 2., 100: 5., 105: 7., 110: 10.}[k] if cp == 'P' else {
                90: 10., 95: 7., 100: 5., 105: 2., 110: 1.}[k]
            rows.append(dict(underlying=underlying, expiry=expiry, strike=float(k), call_put=cp,
                bid=bid, ask=bid + 1, obs_date=DAY, known_at=DAY, source='synthetic-test',
                contract_id=f'provider:{underlying}:{expiry}:{cp}:{k}'))
    return pd.DataFrame(rows)


class Instruments:
    def __init__(self, markets=('x',)):
        self.rows, self.contracts = {}, {}
        for u in markets:
            self.contracts[f'{u}:shares'] = EquityInstrument(f'{u}:shares', u, 'etf', 1, 'USD')
            for row in chain(u).to_dict('records'):
                identity = f"canonical:{u}:{row['expiry']}:{row['call_put']}:{int(row['strike'])}"
                self.rows[identity] = row
                self.contracts[identity] = EquityInstrument(identity, u, 'option', 10, 'USD',
                    row['call_put'], 10, row['expiry'], row['strike'], f'{u}:american:physical:10')

    def resolve_option(self, row):
        matches = [c for c in self.contracts.values() if c.asset_type == 'option' and
            (c.underlying, c.expiry, c.strike, c.call_put) ==
            (row['underlying'], row['expiry'], row['strike'], row['call_put'])]
        if len(matches) != 1:
            raise LookupError('No exact canonical contract.')
        return matches[0]

    def get_instrument(self, instrument_id):
        return self.contracts[instrument_id]

    def option(self, cp, strike, u='x'):
        return self.resolve_option(dict(underlying=u, expiry=END, strike=float(strike), call_put=cp))


class FixedForecast(RVForecaster):
    def forecast(self, inputs, *, horizon_trading_days):
        return RVForecast(inputs.underlying, inputs.as_of, horizon_trading_days, .2)


class Setup(unittest.TestCase):
    def setUp(self):
        self.instruments = Instruments(('x', 'y'))
        self.capital = CapitalModel('USD', self.capital_lookup)
        self.wheel = WheelManager(WheelConfig(.6, .5, .4), self.instruments)
        args = dict(market_lookup=self.market, capital_model=self.capital)
        self.calm = CalmPremiumBuilder(CalmPremiumConfig(1, 60, POLICY), self.instruments, **args)
        self.stress = StressPutSpreadBuilder(StressPutSpreadConfig(1, 60, POLICY), self.instruments, **args)
        self.structures = OptionStructureBuilder(StructureConfig(StructureType.STRADDLE,
            StructureType.STRANGLE, 1, 60, POLICY), self.vol_contract, **args)
        self.hedger = DeltaHedger(DeltaHedgeConfig('USD', {'x': 'x:shares', 'y': 'y:shares'}), self.delta)
        self.data = Mock()
        self.data.get_option_chain.side_effect = lambda u, **kw: chain(u)
        self.data.get_rv_inputs.side_effect = lambda u, **kw: RVInputs(u, kw['as_of'], .1, .2, .3)
        self.iv_value = .1
        self.data.get_implied_vol.side_effect = lambda u, **kw: ImpliedVolSnapshot(
            u, AS_OF, AS_OF, kw['horizon_trading_days'], self.iv_value, horizon_end=END)

    def market(self, u, as_of):
        return MarketSnapshot(u, as_of, 'USD', 100.)

    def capital_lookup(self, instrument_id, as_of):
        c = self.instruments.get_instrument(instrument_id)
        if c.asset_type == 'etf':
            long, short = 100., 150.
        else:
            long = self.instruments.rows[instrument_id]['ask'] * c.multiplier + POLICY.fee_per_contract
            short = (c.strike * c.multiplier if c.call_put == 'P' else 100.) + POLICY.fee_per_contract
        return CapitalSnapshot(instrument_id, as_of, 'USD', long, short, 'synthetic gross funding policy')

    def vol_contract(self, row):
        c = self.instruments.resolve_option(row)
        return OptionContractRef(c.instrument_id, c.multiplier, c.currency, c.underlying,
            c.expiry, c.strike, c.call_put, c.series_id)

    def delta(self, instrument_id, as_of):
        c = self.instruments.get_instrument(instrument_id)
        d = 1. if c.asset_type == 'etf' else (50. if c.call_put == 'C' else -30.)
        return DeltaSnapshot(instrument_id, c.underlying, as_of, 'USD', d)

    def snapshot(self, holdings=(), orders=(), cash=10000):
        return EquityPortfolioSnapshot('equity', AS_OF, 'USD', cash, tuple(holdings), tuple(orders), ())

    def plan(self, ctx=None, snapshot=None):
        ctx = ctx or context()
        return self.wheel.plan(ctx, self.wheel.inspect(ctx, 'x', snapshot or self.snapshot()))

    def signal(self, direction=VolDirection.LONG_VOL):
        return VolSignal('x', AS_OF, 22, direction, -.1, 'synthetic comparison')

    def build_vol(self, **kwargs):
        return self.structures.build(kwargs.pop('ctx', context()), kwargs.pop('signal', self.signal()),
            kwargs.pop('quotes', chain()), horizon_end=kwargs.pop('horizon_end', END), **kwargs)

    def vol(self, markets=('x',)):
        return VolSleeve(VolSleeveConfig(markets, 22), market_data=self.data,
            forecasters={u: FixedForecast() for u in markets},
            signal_generator=VolSignalGenerator(VolSignalConfig(.02, .5, timedelta(days=1))),
            structure_builder=self.structures, delta_hedger=self.hedger)

    def equity(self, snapshot=None, premium=('x',), stress=('y',)):
        portfolio = Mock()
        portfolio.get_snapshot.return_value = snapshot or self.snapshot()
        return EquitySleeve(EquitySleeveConfig(stress, premium, .5), market_data=self.data,
            portfolio=portfolio, wheel_manager=self.wheel, stress_builder=self.stress, calm_builder=self.calm)


class ContractSelectionTests(Setup):
    def test_long_straddle_nearest_atm_whole_contracts_and_canonical_ids(self):
        targets = self.build_vol()
        self.assertEqual([t.target_quantity for t in targets], [20, 20])
        self.assertEqual(len({t.group_id for t in targets}), 1)
        for t in targets:
            self.assertIn(t.instrument_id, self.instruments.contracts)
            self.assertEqual(self.instruments.get_instrument(t.instrument_id).strike, 100)

    def test_short_strangle_selects_nearest_otm_and_margin_limits_size(self):
        targets = self.build_vol(signal=self.signal(VolDirection.SHORT_VOL), ctx=context(2200))
        self.assertEqual([t.target_quantity for t in targets], [-2, -2])
        self.assertEqual([self.instruments.get_instrument(t.instrument_id).strike for t in targets], [95, 105])
        self.assertLessEqual(self.capital.required(targets, AS_OF), 2200)

    def test_no_exact_forecast_expiry_raises_instead_of_using_nearby_expiry(self):
        with self.assertRaises(LookupError):
            self.build_vol(horizon_end=END + timedelta(days=1))

    def test_missing_horizon_end_raises(self):
        with self.assertRaises(ValueError):
            self.build_vol(horizon_end=None)

    def test_incomplete_pair_raises(self):
        with self.assertRaises(LookupError):
            self.build_vol(quotes=chain().query("call_put == 'P'"))

    def test_zero_budget_and_neutral_are_explicit_flatten(self):
        self.assertEqual(self.build_vol(ctx=context(0)), [])
        self.assertEqual(self.build_vol(signal=self.signal(VolDirection.NEUTRAL), quotes=None), [])

    def test_below_one_lot_does_not_create_fractional_position(self):
        self.assertEqual(self.build_vol(ctx=context(100)), [])

    def test_resolver_must_return_exact_terms(self):
        self.structures._contract_lookup = lambda r: replace(self.vol_contract(r), strike=r['strike'] + 1)
        with self.assertRaisesRegex(ValueError, 'strike'):
            self.build_vol()

    def test_mismatched_series_or_multiplier_rejected(self):
        for field, value in (('series_id', 'different-settlement'), ('multiplier', 50)):
            def wrong(row):
                c = self.vol_contract(row)
                return replace(c, **{field: value}) if row['call_put'] == 'C' else c
            self.structures._contract_lookup = wrong
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.build_vol()

    def test_wrong_spot_timestamp_rejected(self):
        self.structures._market_lookup = lambda u, t: MarketSnapshot(u, t - timedelta(days=1), 'USD', 100)
        with self.assertRaisesRegex(ValueError, 'Market lookup'):
            self.build_vol()

    def test_long_funding_below_ask_and_fees_rejected(self):
        self.capital.lookup = lambda i, t: CapitalSnapshot(i, t, 'USD', 1, 1, 'bad test reserve')
        with self.assertRaisesRegex(ValueError, 'premium'):
            self.build_vol()


class QuoteAndFundingTests(Setup):
    def test_stale_future_missing_duplicate_and_mixed_chain_rejected(self):
        cases = []
        for field, value in (('obs_date', DAY - timedelta(days=1)),
                             ('known_at', DAY + timedelta(days=1)), ('bid', 1000.), ('ask', float('nan'))):
            rows = chain(); rows.loc[0, field] = value; cases.append(rows)
        cases += [chain().drop(columns='known_at'), pd.concat([chain(), chain().iloc[:1]])]
        rows = chain(); rows.loc[0, 'source'] = 'other'; cases.append(rows)
        for rows in cases:
            with self.subTest(rows=rows.iloc[0].to_dict()), self.assertRaises(ValueError):
                self.build_vol(quotes=rows)

    def test_spread_filter_leaves_no_suitable_pair(self):
        self.structures._config = replace(self.structures._config, selection=replace(POLICY, max_relative_spread=.001))
        with self.assertRaises(LookupError):
            self.build_vol()

    def test_capital_lookup_identity_timestamp_and_currency_checked(self):
        good = self.capital_lookup('x:shares', AS_OF)
        for row in (replace(good, instrument_id='wrong'), replace(good, currency='CAD'),
                    replace(good, as_of=AS_OF - timedelta(seconds=1))):
            self.capital.lookup = lambda i, t: row
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.capital.unit('x:shares', 1, AS_OF)

    def test_invalid_reserves_rejected(self):
        for value in (0, -1, True, float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                CapitalSnapshot('id', AS_OF, 'USD', value, 1, 'test')

    def test_combination_preserves_groups_and_rejects_opposing_attribution(self):
        a = TargetPosition('vol', 'id', 2, 'a'); b = replace(a, group_id='b')
        self.assertEqual(len(combine([a, b], 'vol')), 2)
        self.assertEqual(combine([a, a], 'vol')[0].target_quantity, 4)
        with self.assertRaises(ValueError):
            combine([a, replace(b, target_quantity=-2)], 'vol')
        with self.assertRaises(ValueError):
            combine([replace(a, sleeve_id='equity')], 'vol')


class DeltaHedgeTests(Setup):
    def test_hedges_complete_desired_option_book_not_incremental_trades(self):
        legs = self.build_vol(ctx=context(150))
        hedge = self.hedger.build(context(), legs)
        self.assertEqual([(t.instrument_id, t.target_quantity, t.group_id) for t in hedge],
                         [('x:shares', -20, 'vol:hedge:x')])
        self.assertEqual(self.hedger.build(context(), []), [])

    def test_rounding_ties_away_from_zero_and_residual_half_unit(self):
        option = self.instruments.option('C', 100).instrument_id
        for delta, expected in ((2.5, -3), (-2.5, 3), (.4, 0)):
            self.hedger._delta_lookup = lambda i, t: DeltaSnapshot(i, 'x', t, 'USD', 1 if i == 'x:shares' else delta)
            targets = self.hedger.build(context(), [TargetPosition('vol', option, 1, 'test')])
            qty = targets[0].target_quantity if targets else 0
            self.assertEqual(qty, expected)
            self.assertLessEqual(abs(delta + qty), .5)

    def test_hedge_rejects_stale_wrong_currency_wrong_factor_and_zero_delta(self):
        option = self.instruments.option('C', 100).instrument_id
        for changes in ({'as_of': AS_OF - timedelta(days=1)}, {'currency': 'CAD'},
                        {'risk_factor_id': 'wrong'}, {'cash_delta_per_unit': 0}):
            self.hedger._delta_lookup = lambda i, t: replace(self.delta(i, t), **changes) if i == 'x:shares' else self.delta(i, t)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.hedger.build(context(), [TargetPosition('vol', option, 1)])

    def test_hedge_mapping_required_and_nonfinite_delta_rejected(self):
        option = self.instruments.option('C', 100, 'y').instrument_id
        hedger = DeltaHedger(DeltaHedgeConfig('USD', {'x': 'x:shares'}), self.delta)
        with self.assertRaises(ValueError):
            hedger.build(context(), [TargetPosition('vol', option, 1)])
        with self.assertRaises(ValueError):
            DeltaSnapshot('id', 'x', AS_OF, 'USD', float('nan'))


class EquityBuilderTests(Setup):
    def test_puts_cash_secured_by_strike_not_premium(self):
        targets = self.calm.build(context(2000), self.plan(context(2000)), chain())
        self.assertEqual(targets[0].target_quantity, -2)
        self.assertEqual(self.instruments.get_instrument(targets[0].instrument_id).strike, 95)
        self.assertLessEqual(self.capital.required(targets, AS_OF), 2000)

    def test_puts_also_limited_by_confirmed_available_cash(self):
        plan = self.plan(snapshot=self.snapshot(cash=960))
        self.assertEqual(self.calm.build(context(), plan, chain())[0].target_quantity, -1)

    def test_put_collateral_floor_rejects_under_reserved_adapter(self):
        self.capital.lookup = lambda i, t: CapitalSnapshot(i, t, 'USD', 100, 100, 'under-reserved')
        with self.assertRaisesRegex(ValueError, 'assignment cash'):
            self.calm.build(context(), self.plan(), chain())

    def test_retained_puts_keep_full_assignment_cash_floor(self):
        put = self.instruments.option('P', 95).instrument_id
        snapshot = self.snapshot([EquityHolding(put, -1, 'wheel', 'original')])
        self.capital.lookup = lambda i, t: CapitalSnapshot(i, t, 'USD', 100, 100, 'under-reserved')
        with self.assertRaisesRegex(ValueError, 'Retained put reserve'):
            self.equity(snapshot).generate_targets(context())

    def test_forged_put_entry_on_nonflat_wheel_is_rejected(self):
        plan = self.plan(snapshot=self.snapshot([EquityHolding('x:shares', 20, 'wheel')]))
        with self.assertRaisesRegex(ValueError, 'flat confirmed wheel'):
            self.calm.build(context(), replace(plan, allow_new_puts=True), chain())

    def test_calls_use_actual_deliverables_and_keep_shares(self):
        holding = EquityHolding('x:shares', 25, 'wheel', 'assignment')
        targets = self.calm.build(context(), self.plan(snapshot=self.snapshot([holding])), chain())
        self.assertIn(TargetPosition('equity', 'x:shares', 25, 'assignment'), targets)
        self.assertEqual([t.target_quantity for t in targets if t.instrument_id != 'x:shares'], [-2])

    def test_existing_calls_reserve_shares_before_new_calls(self):
        call = self.instruments.option('C', 105).instrument_id
        holdings = [EquityHolding('x:shares', 25, 'wheel'), EquityHolding(call, -1, 'wheel', 'old')]
        targets = self.calm.build(context(), self.plan(snapshot=self.snapshot(holdings)), chain())
        self.assertEqual(sum(t.target_quantity for t in targets if t.instrument_id == call), -2)

    def test_blocked_entries_retain_existing_holdings_without_chain(self):
        ctx = context(states=(.2, .35, .2, .25))
        targets = self.calm.build(ctx, self.plan(ctx, self.snapshot([EquityHolding('x:shares', 20, 'wheel')])), None)
        self.assertEqual(targets, [TargetPosition('equity', 'x:shares', 20)])

    def test_stress_exit_closes_calls_before_shares_and_waits_for_confirmation(self):
        call = self.instruments.option('C', 105).instrument_id
        ctx = context(states=(0, 0, 0, 1))
        shares = EquityHolding('x:shares', 20, 'wheel', 'assignment')
        snapshot = self.snapshot([shares, EquityHolding(call, -2, 'wheel', 'covered')])
        self.assertEqual(self.calm.build(ctx, self.plan(ctx, snapshot), None),
                         [TargetPosition('equity', 'x:shares', 20, 'assignment')])
        self.assertEqual(self.calm.build(ctx, self.plan(ctx, self.snapshot([shares])), None), [])

    def test_pending_entries_raise_with_cancellation_intent(self):
        put = self.instruments.option('P', 95).instrument_id
        ctx = context(states=(0, 0, 0, 1))
        plan = self.plan(ctx, self.snapshot(orders=[EquityOpenOrder('entry', put, -1, 'wheel')]))
        with self.assertRaises(PendingOrdersError) as error:
            self.calm.build(ctx, plan, None)
        self.assertEqual(error.exception.cancel_order_ids, ('entry',))

    def test_put_spread_long_higher_short_lower_same_expiry_group(self):
        targets = self.stress.build(context(), 'x', chain())
        self.assertEqual([self.instruments.get_instrument(t.instrument_id).strike for t in targets], [100, 95])
        self.assertGreater(targets[0].target_quantity, 0)
        self.assertEqual(targets[0].target_quantity, -targets[1].target_quantity)
        self.assertEqual(targets[0].group_id, targets[1].group_id)
        self.assertLessEqual(self.capital.required(targets, AS_OF), context().capital_budget)

    def test_bad_spread_debit_rejected(self):
        quotes = chain(); quotes.loc[(quotes.call_put == 'P') & (quotes.strike == 100), 'ask'] = 8.
        with self.assertRaises(ValueError):
            self.stress.build(context(), 'x', quotes)


class SleevePipelineTests(Setup):
    def test_vol_full_forecast_signal_options_hedge_pipeline(self):
        result = self.vol().generate_targets(context())
        options = [t for t in result if t.instrument_id != 'x:shares']
        self.assertEqual([t.target_quantity for t in options], [3, 3])
        self.assertIn(TargetPosition('vol', 'x:shares', -60, 'vol:hedge:x'), result)
        self.assertLessEqual(self.capital.required(result, AS_OF), 10000)
        # Options alone could fit 20 lots; integrated hedge funding cuts to 3.
        self.assertEqual(abs(sum(t.target_quantity * self.delta(t.instrument_id, AS_OF).cash_delta_per_unit for t in result)), 0)

    def test_vol_short_pipeline_and_stress_veto_flatten(self):
        self.iv_value = .3
        result = self.vol().generate_targets(context())
        self.assertTrue(any(t.target_quantity < 0 and 'canonical' in t.instrument_id for t in result))
        self.assertLessEqual(self.capital.required(result, AS_OF), 10000)
        self.assertEqual(self.vol().generate_targets(context(states=(0, 0, 1, 0))), [])

    def test_vol_neutral_skips_chain_and_flattens(self):
        self.iv_value = .2
        self.assertEqual(self.vol().generate_targets(context()), [])
        self.data.get_option_chain.assert_not_called()

    def test_vol_multi_market_budget_is_not_reused(self):
        result = self.vol(('x', 'y')).generate_targets(context())
        for u in ('x', 'y'):
            market = [t for t in result if self.instruments.get_instrument(t.instrument_id).underlying == u]
            self.assertTrue(market)
            self.assertLessEqual(self.capital.required(market, AS_OF), 5000)
        self.assertLessEqual(self.capital.required(result, AS_OF), 10000)

    def test_vol_insufficient_hedge_funding_yields_no_position(self):
        self.assertEqual(self.vol().generate_targets(context(200)), [])

    def test_combined_rounding_cannot_overdraw_shared_factor_hedge_budget(self):
        def delta(i, t):
            c = self.instruments.get_instrument(i)
            value = 1. if c.asset_type == 'etf' else (.4 if c.call_put == 'C' else 0.)
            return DeltaSnapshot(i, 'shared', t, 'USD', value)
        self.hedger = DeltaHedger(DeltaHedgeConfig('USD', {'shared': 'x:shares'}), delta)
        targets = self.vol(('x', 'y')).generate_targets(context(300))
        self.assertEqual(len(targets), 2)
        self.assertLessEqual(self.capital.required(targets, AS_OF), 300)

    def test_reduced_allocation_unwinds_oversized_wheel(self):
        snapshot = self.snapshot([EquityHolding('x:shares', 20, 'wheel')])
        self.assertEqual(self.equity(snapshot).generate_targets(context(100)), [])
        self.data.get_option_chain.assert_not_called()

    def test_full_wheel_pipeline_after_confirmed_assignment_and_callaway(self):
        put_targets = self.equity().generate_targets(context(1000))
        self.assertEqual(put_targets[0].target_quantity, -1)
        # Fill/assignment is supplied by Portfolio, never invented by a sleeve.
        snapshot = self.snapshot([EquityHolding('x:shares', 10, 'wheel', 'assignment')])
        call_targets = self.equity(snapshot).generate_targets(context(2000))
        self.assertIn(TargetPosition('equity', 'x:shares', 10, 'assignment'), call_targets)
        self.assertEqual(sum(t.target_quantity for t in call_targets if t.instrument_id != 'x:shares'), -1)
        restarted = self.equity(self.snapshot()).generate_targets(context(1000))
        self.assertEqual(restarted, put_targets)

    def test_vol_data_error_propagates_does_not_flatten(self):
        self.data.get_rv_inputs.side_effect = LookupError('missing observation')
        with self.assertRaises(LookupError):
            self.vol().generate_targets(context())

    def test_equity_flat_calm_pipeline_only_sells_cash_secured_put(self):
        targets = self.equity().generate_targets(context())
        self.assertEqual(len(targets), 1)
        c = self.instruments.get_instrument(targets[0].instrument_id)
        self.assertEqual((c.underlying, c.call_put, c.strike), ('x', 'P', 95))
        self.assertLessEqual(self.capital.required(targets, AS_OF), 10000)

    def test_stressed_bull_exits_wheel_without_bearish_spreads(self):
        targets = self.equity(self.snapshot([EquityHolding('x:shares', 20, 'wheel')])).generate_targets(
            context(states=(0, 0, 1, 0)))
        self.assertEqual(targets, [])
        self.data.get_option_chain.assert_not_called()

    def test_stressed_bear_builds_spreads_and_preserves_staged_wheel_shares(self):
        call = self.instruments.option('C', 105).instrument_id
        snapshot = self.snapshot([EquityHolding('x:shares', 20, 'wheel'), EquityHolding(call, -2, 'wheel')])
        targets = self.equity(snapshot).generate_targets(context(states=(0, 0, 0, 1)))
        self.assertIn(TargetPosition('equity', 'x:shares', 20), targets)
        self.assertFalse(any(t.instrument_id == call for t in targets))
        self.assertTrue(any(self.instruments.get_instrument(t.instrument_id).underlying == 'y' for t in targets))
        self.assertLessEqual(self.capital.required(targets, AS_OF), 10000)

    def test_multi_market_put_entries_share_cash_once(self):
        targets = self.equity(self.snapshot(cash=2000), premium=('x', 'y')).generate_targets(context())
        self.assertEqual(len(targets), 2)
        self.assertTrue(all(t.target_quantity == -1 for t in targets))
        self.assertLessEqual(self.capital.required(targets, AS_OF), 2000)

    def test_removed_wheel_market_is_unwound_not_forgotten(self):
        targets = self.equity(self.snapshot([EquityHolding('y:shares', 20, 'wheel')])).generate_targets(context())
        self.assertFalse(any(t.instrument_id == 'y:shares' for t in targets))

    def test_zero_budget_call_unwind_retains_shares_then_requests_flatten(self):
        call = self.instruments.option('C', 105).instrument_id
        snapshot = self.snapshot([EquityHolding('x:shares', 20, 'wheel'), EquityHolding(call, -2, 'wheel')])
        self.assertEqual(self.equity(snapshot).generate_targets(context(0)), [TargetPosition('equity', 'x:shares', 20)])
        self.assertEqual(self.equity(self.snapshot([EquityHolding('x:shares', 20, 'wheel')])).generate_targets(context(0)), [])

    def test_unknown_strategy_and_stale_snapshot_raise(self):
        for snapshot in (self.snapshot([EquityHolding('x:shares', 20, 'unknown')]),
                         replace(self.snapshot(), as_of=AS_OF - timedelta(days=1))):
            with self.subTest(snapshot=snapshot), self.assertRaises(ValueError):
                self.equity(snapshot).generate_targets(context())

    def test_pending_work_never_returns_misleading_flatten(self):
        put = self.instruments.option('P', 95).instrument_id
        snapshot = self.snapshot(orders=[EquityOpenOrder('open', put, -1, 'wheel')])
        with self.assertRaises(PendingOrdersError):
            self.equity(snapshot).generate_targets(context())

    def test_inactive_stress_holdings_target_zero(self):
        put = self.instruments.option('P', 100, 'y').instrument_id
        snapshot = self.snapshot([EquityHolding(put, 1, 'stress_put_spread', 'old-spread')])
        targets = self.equity(snapshot).generate_targets(context())
        self.assertFalse(any(t.instrument_id == put for t in targets))


if __name__ == '__main__':
    unittest.main()
