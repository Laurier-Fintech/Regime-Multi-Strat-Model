"""Quoted same-series bearish put debit spreads with gross funding reserves."""
from dataclasses import dataclass

from Common.targeting import (SelectionPolicy, CapitalModel, MarketLookup, chain_rows,
    market_at, resolved, compatible, require_option_funding, sized, text)
from Sleeves.base_sleeve import SleeveContext, TargetPosition
from Sleeves.EquitySleeve.wheel import EquityInstruments


@dataclass(frozen=True, slots=True)
class StressPutSpreadConfig:
    min_dte_calendar_days: int
    max_dte_calendar_days: int
    selection: SelectionPolicy

    def __post_init__(self):
        if not isinstance(self.selection, SelectionPolicy):
            raise TypeError('selection must be a SelectionPolicy.')
        for v in (self.min_dte_calendar_days, self.max_dte_calendar_days):
            if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
                raise ValueError('DTE bounds must be positive integers.')
        if self.min_dte_calendar_days > self.max_dte_calendar_days:
            raise ValueError('Minimum DTE cannot exceed maximum DTE.')


class StressPutSpreadBuilder:
    @property
    def instruments(self):
        return self._instruments

    def __init__(self, config: StressPutSpreadConfig, instruments: EquityInstruments,
                 *, market_lookup: MarketLookup, capital_model: CapitalModel, strategy_id='stress_put_spread'):
        if not isinstance(config, StressPutSpreadConfig):
            raise TypeError('config must be a StressPutSpreadConfig.')
        text('strategy_id', strategy_id)
        self._config, self._instruments = config, instruments
        self._market_lookup, self.capital_model, self.strategy_id = market_lookup, capital_model, strategy_id
        if capital_model.base_currency != config.selection.base_currency:
            raise ValueError('Selection and capital currencies must match.')

    def build(self, context: SleeveContext, underlying: str, option_chain) -> list[TargetPosition]:
        if context.capital_budget == 0:
            return []
        cfg, policy = self._config, self._config.selection
        spot = market_at(self._market_lookup, underlying, context, policy).spot
        rows = chain_rows(option_chain, underlying, context, policy, cfg.min_dte_calendar_days, cfg.max_dte_calendar_days)
        puts = [r for r in rows if r['call_put'] == 'P' and r['strike'] <= spot]
        pairs = [(a, b) for a in puts for b in puts if a['expiry'] == b['expiry'] and a['strike'] > b['strike']]
        if not pairs:
            raise LookupError('No same-expiry bearish put spread available.')
        long, short = min(pairs, key=lambda p: (p[0]['expiry'], spot - p[0]['strike'], p[0]['strike'] - p[1]['strike']))
        a, b = [resolved(self._instruments.resolve_option, row, policy) for row in (long, short)]
        compatible(a, b)
        if a.deliverable_shares != b.deliverable_shares:
            raise ValueError('Spread deliverables must match.')
        debit = (long['ask'] - short['bid']) * a.multiplier + 2 * policy.fee_per_contract
        width = (long['strike'] - short['strike']) * a.multiplier
        if short['bid'] <= 0 or not 0 < debit < width:
            raise ValueError('Spread must have positive executable-side debit below strike width.')
        for c, r, side in ((a, long, 1), (b, short, -1)):
            require_option_funding(self.capital_model, c, r, side, context, policy)
        group = f'{self.strategy_id}:{underlying}:{a.instrument_id}:{b.instrument_id}'
        lot = [TargetPosition('equity', a.instrument_id, 1, group), TargetPosition('equity', b.instrument_id, -1, group)]
        return sized(context, lot, self.capital_model, policy.max_contracts, unit_floor=debit)
