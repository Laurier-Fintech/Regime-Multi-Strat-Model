"""Sleeve A's complete option and hedge target pipeline.

ModelHome calls generate_targets(context).
This module coordinates forecasting, signals, option structures, and hedging.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol

from Sleeves.base_sleeve import BaseSleeve, SleeveContext, TargetPosition
from Sleeves.VolSleeve.rv_forecast import RVForecaster, RVInputs
from Sleeves.VolSleeve.signal import ImpliedVolSnapshot, VolSignalGenerator
from Sleeves.VolSleeve.structures import OptionStructureBuilder
from Sleeves.VolSleeve.delta_hedge import DeltaHedger
from Sleeves.VolSleeve.signal import VolDirection
from Common.targeting import combine, scaled

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True, slots=True)
class VolSleeveConfig:
    """Market universe and forecast horizon supplied by configuration."""

    underlying_ids: tuple[str, ...]
    horizon_trading_days: int

    def __post_init__(self) -> None:
        if not isinstance(self.underlying_ids, tuple):
            raise TypeError("underlying_ids must be a tuple.")

        if not self.underlying_ids:
            raise ValueError("At least one underlying is required.")

        for underlying in self.underlying_ids:
            if not isinstance(underlying, str) or not underlying.strip():
                raise ValueError("Underlying IDs must be nonempty strings.")

        if len(set(self.underlying_ids)) != len(self.underlying_ids):
            raise ValueError("Underlying IDs must be unique.")

        if isinstance(self.horizon_trading_days, bool) or not isinstance(
            self.horizon_trading_days, int
        ):
            raise TypeError("horizon_trading_days must be an integer.")

        if self.horizon_trading_days <= 0:
            raise ValueError("horizon_trading_days must be positive.")


# A Protocol describes the methods a supplied object must provide.
# DatabaseVolMarketData in market_data.py implements this interface over the
# public data reader, with explicit source proxies and session alignment.
class VolMarketData(Protocol):
    """Read-only data adapter contract for the volatility sleeve."""

    def get_rv_inputs(
        self,
        underlying: str,
        *,
        as_of: datetime,
    ) -> RVInputs:
        raise NotImplementedError

    def get_implied_vol(
        self,
        underlying: str,
        *,
        as_of: datetime,
        horizon_trading_days: int,
    ) -> ImpliedVolSnapshot:
        raise NotImplementedError

    def get_option_chain(
        self,
        underlying: str,
        *,
        as_of: datetime,
    ) -> pd.DataFrame:
        raise NotImplementedError


class VolSleeve(BaseSleeve):
    """Coordinate Sleeve A and return its complete desired holdings."""

    # Matches the identifier used in Config and the trading database.
    SLEEVE_ID = "vol"

    def __init__(
        self,
        config: VolSleeveConfig,
        *,
        market_data: VolMarketData,
        forecasters: Mapping[str, RVForecaster],
        signal_generator: VolSignalGenerator,
        structure_builder: OptionStructureBuilder,
        delta_hedger: DeltaHedger,
    ) -> None:
        if not isinstance(config, VolSleeveConfig):
            raise TypeError("config must be a VolSleeveConfig.")

        # Each underlying needs its own model, fitted for the chosen horizon.
        models = dict(forecasters)
        missing = set(config.underlying_ids) - set(models)

        if missing:
            raise ValueError(f"Missing forecasters for: {sorted(missing)}")

        if any(not isinstance(model, RVForecaster) for model in models.values()):
            raise TypeError("Every forecaster must implement RVForecaster.")

        self._config = config
        self._market_data = market_data
        self._forecasters = MappingProxyType(models)
        self._signal_generator = signal_generator
        self._structure_builder = structure_builder
        self._delta_hedger = delta_hedger
        if structure_builder.capital_model.base_currency != delta_hedger.base_currency:
            raise ValueError('Structure funding and hedge currencies must match.')

    def generate_targets(self, context: SleeveContext) -> list[TargetPosition]:
        """Return the complete desired option and hedge holdings for Sleeve A."""

        if not isinstance(context, SleeveContext):
            raise TypeError('context must be a SleeveContext.')
        if context.capital_budget == 0:
            return []
        capital = self._structure_builder.capital_model
        market_context = replace(context, capital_budget=context.capital_budget / len(self._config.underlying_ids))
        options = []
        for underlying in self._config.underlying_ids:
            inputs = self._market_data.get_rv_inputs(underlying, as_of=context.as_of)
            if inputs.underlying != underlying or inputs.as_of != context.as_of:
                raise ValueError('RV inputs must match market and decision timestamp.')
            forecast = self._forecasters[underlying].forecast(inputs, horizon_trading_days=self._config.horizon_trading_days)
            iv = self._market_data.get_implied_vol(underlying, as_of=context.as_of,
                horizon_trading_days=self._config.horizon_trading_days)
            signal = self._signal_generator.generate(context, forecast, iv)
            if signal.underlying != underlying:
                raise ValueError('Signal market does not match configured market.')
            if signal.direction == VolDirection.NEUTRAL:
                continue
            chain = self._market_data.get_option_chain(underlying, as_of=context.as_of)
            proposed = self._structure_builder.build(market_context, signal, chain, horizon_end=iv.horizon_end)
            if not proposed:
                continue
            # The builder emits a 1:1 two-leg structure. Size again with its
            # hedge so options cannot consume capital reserved for hedging.
            count = abs(proposed[0].target_quantity)
            lot = [replace(t, target_quantity=1 if t.target_quantity > 0 else -1) for t in proposed]
            # Descending search is exact even around hedge-rounding thresholds.
            # max_contracts bounds its cost; no monotonic margin assumption.
            for quantity in range(count, 0, -1):
                candidate = scaled(lot, quantity)
                hedges = self._delta_hedger.build(context, candidate)
                if capital.required(candidate + hedges, context.as_of) <= market_context.capital_budget:
                    options.extend(candidate)
                    break
        options = combine(options, self.SLEEVE_ID)
        result = combine(options + self._delta_hedger.build(context, options), self.SLEEVE_ID)
        # Shared-factor whole-unit rounding can require an extra hedge unit
        # even when isolated market hedges rounded to zero. Remove whole lots
        # deterministically, preserving both legs, and recalculate the hedge.
        while capital.required(result, context.as_of) > context.capital_budget and options:
            group = sorted({t.group_id for t in options})[-1]
            options = [replace(t, target_quantity=t.target_quantity - (1 if t.target_quantity > 0 else -1))
                       if t.group_id == group else t for t in options]
            options = [t for t in options if t.target_quantity]
            result = combine(options + self._delta_hedger.build(context, options), self.SLEEVE_ID)
        capital.check(context, result)
        return result
