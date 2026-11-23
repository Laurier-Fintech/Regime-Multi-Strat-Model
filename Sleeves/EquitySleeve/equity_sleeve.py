"""Sleeve B's complete wheel/spread targets with confirmed holdings and budgets."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from Sleeves.base_sleeve import BaseSleeve, SleeveContext, TargetPosition
from Sleeves.EquitySleeve.wheel import EquityPortfolio, EquityPortfolioSnapshot, WheelManager
from Sleeves.EquitySleeve.stress_put_spreads import StressPutSpreadBuilder
from Sleeves.EquitySleeve.calm_premium import CalmPremiumBuilder, PendingOrdersError
from Common.targeting import combine, positive

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True, slots=True)
class EquitySleeveConfig:
    """Entry universes supplied by configuration.

    Regime labels belong to the shared model contract, not sleeve settings.
    Wheel gates live in WheelConfig; bearish spreads have a joint-state gate.
    """

    stress_underlying_ids: tuple[str, ...]
    premium_underlying_ids: tuple[str, ...]
    stressed_bear_entry_probability: float

    def __post_init__(self) -> None:
        positive('stressed_bear_entry_probability', self.stressed_bear_entry_probability)
        if self.stressed_bear_entry_probability > 1:
            raise ValueError('stressed_bear_entry_probability must be in (0, 1].')
        for name in ("stress_underlying_ids", "premium_underlying_ids"):
            ids = getattr(self, name)

            if not isinstance(ids, tuple):
                raise TypeError(f"{name} must be a tuple.")

            if not ids or any(
                not isinstance(value, str) or not value.strip()
                for value in ids
            ):
                raise ValueError(f"{name} must contain nonempty string IDs.")

            if len(set(ids)) != len(ids):
                raise ValueError(f"{name} must contain unique IDs.")


class EquityMarketData(Protocol):
    """Read-only adapter over Data/DataBase/access.py."""

    def get_option_chain(
        self,
        underlying: str,
        *,
        as_of: datetime,
    ) -> pd.DataFrame:
        # The adapter enforces the daily cutoff convention and quote metadata.
        raise NotImplementedError


class EquitySleeve(BaseSleeve):
    """Return Sleeve B's complete desired option AND share holdings."""

    SLEEVE_ID = "equity"

    def __init__(
        self,
        config: EquitySleeveConfig,
        *,
        market_data: EquityMarketData,
        portfolio: EquityPortfolio,
        wheel_manager: WheelManager,
        stress_builder: StressPutSpreadBuilder,
        calm_builder: CalmPremiumBuilder,
    ) -> None:
        if not isinstance(config, EquitySleeveConfig):
            raise TypeError("config must be an EquitySleeveConfig.")

        self._config = config
        self._market_data = market_data
        self._portfolio = portfolio
        self._wheel_manager = wheel_manager
        self._stress_builder = stress_builder
        self._calm_builder = calm_builder
        if stress_builder.capital_model is not calm_builder.capital_model:
            raise ValueError('Equity builders must share one capital model.')
        if calm_builder.instruments is not wheel_manager.instruments or stress_builder.instruments is not wheel_manager.instruments:
            raise ValueError('Equity builders and wheel manager must share one instrument adapter.')
        if wheel_manager.strategy_id != calm_builder.strategy_id or stress_builder.strategy_id == calm_builder.strategy_id:
            raise ValueError('Strategy IDs must match the wheel and distinguish stress spreads.')

    def generate_targets(self, context: SleeveContext) -> list[TargetPosition]:
        if not isinstance(context, SleeveContext):
            raise TypeError('context must be a SleeveContext.')
        snapshot = self._portfolio.get_snapshot(sleeve_id=self.SLEEVE_ID, as_of=context.as_of)
        if not isinstance(snapshot, EquityPortfolioSnapshot) or snapshot.sleeve_id != self.SLEEVE_ID or snapshot.as_of != context.as_of:
            raise ValueError('Portfolio must supply an exact equity decision snapshot.')
        capital = self._calm_builder.capital_model
        if snapshot.base_currency != capital.base_currency:
            raise ValueError('Portfolio and capital currencies must match.')
        instruments = self._wheel_manager.instruments
        wheel_markets = set(self._config.premium_underlying_ids)
        strategies = {self._calm_builder.strategy_id, self._stress_builder.strategy_id}
        attribution = {}
        for row in snapshot.holdings + snapshot.open_orders:
            if row.strategy_id not in strategies:
                raise ValueError('Unknown strategy attribution; refusing to omit unmanaged holdings/orders.')
            contract = instruments.get_instrument(row.instrument_id)
            if contract.instrument_id != row.instrument_id:
                raise ValueError('Canonical lookup returned the wrong instrument ID.')
            key = row.instrument_id, row.group_id
            if key in attribution and attribution[key] != row.strategy_id:
                raise ValueError('Strategy attribution collides for one instrument/group.')
            attribution[key] = row.strategy_id
            if row.strategy_id == self._calm_builder.strategy_id:
                wheel_markets.add(contract.underlying)
        plans, retained = {}, []
        for underlying in sorted(wheel_markets):
            state = self._wheel_manager.inspect(context, underlying, snapshot)
            plan = self._wheel_manager.plan(context, state)
            if underlying not in self._config.premium_underlying_ids:
                plan = replace(plan, allow_new_puts=False, allow_covered_calls=False,
                               exit_requested=True, cancel_order_ids=state.entry_order_ids,
                               reason='Removed from wheel universe: staged unwind.')
            plans[underlying] = plan
            retained.extend(self._calm_builder.retained(context, plan))
        if snapshot.open_orders:
            raise PendingOrdersError([o.order_id for o in snapshot.open_orders],
                [i for plan in plans.values() for i in plan.cancel_order_ids])
        if capital.required(retained, context.as_of) > context.capital_budget:
            # A smaller allocation is an exit instruction rather than license
            # to retain an oversized wheel indefinitely. Call coverage still
            # takes priority until closing fills are confirmed.
            plans = {u: replace(p, allow_new_puts=False, allow_covered_calls=False,
                               exit_requested=True, reason='Wheel book exceeds reduced capital allocation.')
                     for u, p in plans.items()}
            retained = [t for p in plans.values() for t in self._calm_builder.retained(context, p)]
        # Stress-spread policy is directional: stressed-bull alone never opens
        # bearish spreads. Inactive and removed stress markets target zero.
        stress_active = (context.capital_budget > 0 and context.market_regime.stressed_bear >=
                         self._config.stressed_bear_entry_probability)
        routes = [('wheel', u) for u, p in plans.items() if not p.exit_requested and
                  (p.allow_new_puts or p.allow_covered_calls)]
        if stress_active:
            routes += [('stress', u) for u in self._config.stress_underlying_ids]
        base_requirement = capital.required(retained, context.as_of)
        free = max(0.0, min(context.capital_budget - base_requirement, snapshot.available_cash))
        slice_budget = free / len(routes) if routes else 0.0
        result = list(retained)
        for route, underlying in routes:
            if slice_budget <= 0:
                continue
            chain = self._market_data.get_option_chain(underlying, as_of=context.as_of)
            if route == 'wheel':
                plan = plans[underlying]
                baseline = self._calm_builder.retained(context, plan)
                local = replace(context, capital_budget=capital.required(baseline, context.as_of) + slice_budget)
                built = self._calm_builder.build(local, plan, chain)
                # Replace this market's baseline rather than adding it twice.
                keys = {(t.instrument_id, t.group_id) for t in baseline}
                result = [t for t in result if (t.instrument_id, t.group_id) not in keys]
                result.extend(built)
            else:
                built = self._stress_builder.build(replace(context, capital_budget=slice_budget), underlying, chain)
                result.extend(built)
            for target in built:
                strategy = self._calm_builder.strategy_id if route == 'wheel' else self._stress_builder.strategy_id
                key = target.instrument_id, target.group_id
                if key in attribution and attribution[key] != strategy:
                    raise ValueError('Generated target has conflicting strategy attribution.')
                attribution[key] = strategy
        result = combine(result, self.SLEEVE_ID)
        # Reinspect synthetic desired holdings through the same coverage logic.
        from Sleeves.EquitySleeve.wheel import EquityHolding
        desired_holdings = tuple(EquityHolding(t.instrument_id, t.target_quantity,
            attribution[t.instrument_id, t.group_id], t.group_id) for t in result)
        proposed = replace(snapshot, holdings=desired_holdings, open_orders=())
        for underlying in wheel_markets:
            self._wheel_manager.inspect(context, underlying, proposed)
        if capital.required(result, context.as_of) > context.capital_budget:
            # A staged call unwind may temporarily retain shares above a reduced
            # budget. Permit only a strict subset of already confirmed holdings.
            actual = {(h.instrument_id, h.group_id): h.quantity for h in snapshot.holdings}
            reduction = all((t.instrument_id, t.group_id) in actual and
                t.target_quantity * actual[t.instrument_id, t.group_id] > 0 and
                abs(t.target_quantity) <= abs(actual[t.instrument_id, t.group_id]) for t in result)
            if not reduction or result == combine([TargetPosition('equity', h.instrument_id, h.quantity, h.group_id)
                                                  for h in snapshot.holdings], 'equity'):
                raise ValueError('Desired book exceeds budget without a staged exposure reduction.')
        return result
