"""Skeleton for Sleeve A's public entry point.

ModelHome calls generate_targets(context).
This module coordinates forecasting, signals, option structures, and hedging.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol

from Sleeves.base_sleeve import BaseSleeve, SleeveContext, TargetPosition
from Sleeves.VolSleeve.rv_forecast import RVForecaster, RVInputs
from Sleeves.VolSleeve.signal import ImpliedVolSnapshot, VolSignalGenerator
from Sleeves.VolSleeve.structures import OptionStructureBuilder
from Sleeves.VolSleeve.delta_hedge import DeltaHedger

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
# The eventual adapter will wrap Data/DataBase/access.py and handle daily
# cutoff conventions and horizon alignment. It will perform no downloads.
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

    def generate_targets(self, context: SleeveContext) -> list[TargetPosition]:
        """Return the complete desired option and hedge holdings for Sleeve A."""

        # Implementation sequence:
        # 1. Validate the context and required dependencies.
        # 2. Allocate the sleeve budget across its configured markets.
        #    Each market must receive its allocated slice, rather than
        #    independently spending the entire sleeve budget.
        # 3. Read each market's inputs using context.as_of.
        # 4. Request a forecast from that market's properly fitted model.
        # 5. Generate its volatility signal using aligned implied volatility.
        # 6. Build its desired option positions within its market budget.
        # 7. Combine the complete desired option book across all markets.
        # 8. Calculate hedge targets for that combined option book.
        # 9. Reconcile duplicate instrument IDs and preserve group attribution.
        # 10. Validate that all targets belong to sleeve_id="vol".
        # 11. Return the complete desired option and hedge holdings.
        #
        # Funding and collateral checks must cover options and hedges together.
        # The engine passes targets through RiskManagement and Portfolio.
        # Orders, fills, and actual holdings remain with their owning layers.
        #
        # A valid empty list explicitly requests flattening this sleeve.
        # Missing data, unfitted models, and unfinished logic must raise errors.
        # Never convert these errors into an empty target list.

        raise NotImplementedError(
            "VolSleeve orchestration has not been implemented."
        )