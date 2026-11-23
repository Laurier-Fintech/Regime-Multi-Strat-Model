"""Cash-secured puts, covered calls and staged wheel exits."""
from dataclasses import dataclass, replace

from Common.targeting import (SelectionPolicy, CapitalModel, MarketLookup, chain_rows,
    market_at, resolved, require_option_funding, sized, positive, text)
from Sleeves.base_sleeve import SleeveContext, TargetPosition
from Sleeves.EquitySleeve.wheel import EquityInstruments, WheelPlan, WheelStage


@dataclass(frozen=True, slots=True)
class CalmPremiumConfig:
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


class PendingOrdersError(RuntimeError):
    """No book issued until pending work resolves; cancellation is intent only."""
    def __init__(self, pending_order_ids, cancel_order_ids=()):
        self.pending_order_ids = tuple(sorted(pending_order_ids))
        self.cancel_order_ids = tuple(sorted(cancel_order_ids))
        super().__init__(f'Await confirmed fills/cancellations: {self.pending_order_ids}; '
                         f'cancel entry intent: {self.cancel_order_ids}')


class CalmPremiumBuilder:
    @property
    def instruments(self):
        return self._instruments

    def __init__(self, config: CalmPremiumConfig, instruments: EquityInstruments,
                 *, market_lookup: MarketLookup, capital_model: CapitalModel, strategy_id='wheel'):
        if not isinstance(config, CalmPremiumConfig):
            raise TypeError('config must be a CalmPremiumConfig.')
        text('strategy_id', strategy_id)
        self._config, self._instruments = config, instruments
        self._market_lookup, self.capital_model = market_lookup, capital_model
        self.strategy_id = strategy_id
        if capital_model.base_currency != config.selection.base_currency:
            raise ValueError('Selection and capital currencies must match.')

    def retained(self, context, plan):
        if not isinstance(plan, WheelPlan) or plan.state.portfolio_snapshot.as_of != context.as_of:
            raise ValueError('Wheel plan must match the decision timestamp.')
        if plan.state.portfolio_snapshot.base_currency != self._config.selection.base_currency:
            raise ValueError('Portfolio currency must match selection currency.')
        result = []
        for holding in plan.state.portfolio_snapshot.holdings:
            contract = self._instruments.get_instrument(holding.instrument_id)
            if contract.instrument_id != holding.instrument_id:
                raise ValueError('Canonical holding lookup returned the wrong ID.')
            if holding.strategy_id != self.strategy_id or contract.underlying != plan.state.underlying:
                continue
            # Close options first; retain shares until call closes are confirmed.
            if plan.exit_requested:
                if contract.asset_type == 'option' or plan.state.short_call_contracts == 0:
                    continue
            elif contract.asset_type == 'option' and contract.call_put == 'P' and holding.quantity < 0:
                positive('retained put strike', contract.strike)
                collateral = contract.strike * contract.deliverable_shares + self._config.selection.fee_per_contract
                if self.capital_model.unit(contract.instrument_id, -1, context.as_of) < collateral:
                    raise ValueError('Retained put reserve must cover full assignment cash plus fees.')
            if holding.quantity:
                result.append(TargetPosition('equity', holding.instrument_id, holding.quantity, holding.group_id))
        return result

    def build(self, context: SleeveContext, plan: WheelPlan, option_chain) -> list[TargetPosition]:
        if not isinstance(context, SleeveContext) or not isinstance(plan, WheelPlan):
            raise TypeError('A SleeveContext and WheelManager plan are required.')
        if plan.allow_new_puts and plan.state.stage != WheelStage.FLAT:
            raise ValueError('New wheel puts require a flat confirmed wheel.')
        if plan.state.pending_order_ids:
            raise PendingOrdersError(plan.state.pending_order_ids, plan.cancel_order_ids)
        held = self.retained(context, plan)
        if plan.exit_requested or not (plan.allow_new_puts or plan.allow_covered_calls):
            return held
        policy, cfg = self._config.selection, self._config
        remaining = context.capital_budget - self.capital_model.required(held, context.as_of)
        if remaining <= 0:
            return held
        spot = market_at(self._market_lookup, plan.state.underlying, context, policy).spot
        rows = chain_rows(option_chain, plan.state.underlying, context, policy,
                          cfg.min_dte_calendar_days, cfg.max_dte_calendar_days)
        cp = 'P' if plan.allow_new_puts else 'C'
        candidates = [r for r in rows if r['call_put'] == cp and r['bid'] > 0 and
                      (r['strike'] < spot if cp == 'P' else r['strike'] > spot)]
        if not candidates:
            raise LookupError('No quoted OTM wheel contract meets policy.')
        row = min(candidates, key=lambda r: (r['expiry'], abs(r['strike'] - spot)))
        contract = resolved(self._instruments.resolve_option, row, policy)
        if contract.deliverable_shares is None or contract.deliverable_shares != contract.multiplier:
            raise ValueError('Wheel entry requires a pure share deliverable equal to the quote multiplier.')
        positive('deliverable shares', contract.deliverable_shares)
        if contract.deliverable_shares % 1:
            raise ValueError('Fractional share deliverables are unsupported.')
        require_option_funding(self.capital_model, contract, row, -1, context, policy)
        group = f'{self.strategy_id}:{plan.state.underlying}:{contract.instrument_id}'
        lot = [TargetPosition('equity', contract.instrument_id, -1, group)]
        if cp == 'P':
            collateral = row['strike'] * contract.deliverable_shares + policy.fee_per_contract
            floor_cost = max(collateral, self.capital_model.required(lot, context.as_of))
            if self.capital_model.required(lot, context.as_of) < collateral:
                raise ValueError('Put reserve must include full strike-based assignment cash plus fees.')
            remaining = min(remaining, max(0, plan.state.portfolio_snapshot.available_cash))
            cap = policy.max_contracts
        else:
            floor_cost = policy.fee_per_contract
            cap = min(policy.max_contracts, int(plan.state.available_call_shares // contract.deliverable_shares))
        new = sized(replace(context, capital_budget=remaining), lot, self.capital_model, cap, unit_floor=floor_cost)
        return held + new
