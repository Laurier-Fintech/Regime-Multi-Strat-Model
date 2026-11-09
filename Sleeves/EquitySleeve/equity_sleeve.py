"""Skeleton for Sleeve B's public entry point."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from Sleeves.base_sleeve import BaseSleeve, SleeveContext, TargetPosition
from Sleeves.EquitySleeve.wheel import EquityPortfolio, WheelManager
from Sleeves.EquitySleeve.stress_put_spreads import StressPutSpreadBuilder
from Sleeves.EquitySleeve.calm_premium import CalmPremiumBuilder

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True, slots=True)
class EquitySleeveConfig:
    """Entry universes and regime names supplied by configuration."""

    stress_underlying_ids: tuple[str, ...]
    premium_underlying_ids: tuple[str, ...]
    calm_regime: str
    stress_regime: str

    def __post_init__(self) -> None:
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

        for name in ("calm_regime", "stress_regime"):
            value = getattr(self, name)

            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a nonempty string.")

        if self.calm_regime == self.stress_regime:
            raise ValueError("Calm and stress regime names must differ.")


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

    def generate_targets(self, context: SleeveContext) -> list[TargetPosition]:
        # 1. Validate context and require the configured regime names.
        #    A missing regime must raise, rather than defaulting to zero.
        # 2. Read the authoritative equity Portfolio snapshot at context.as_of.
        # 3. Reconcile confirmed wheel holdings, open orders, and events.
        #    Also manage held markets removed from the new-entry universe.
        # 4. Define regime blending/priority and split the capital budget.
        #    Each route/market receives a slice, not the entire sleeve budget.
        # 5. Inspect wheel state and produce plans using named probabilities.
        # 6. Read required option chains through self._market_data.
        # 7. Build stressed-regime spreads and planned wheel holdings/exits.
        #    Blocked new entries do not automatically mean flattening.
        # 8. Combine ALL desired shares and option legs, preserving attribution.
        # 9. Check duplicates, coverage, funding, and total allocated capital.
        # 10. Return targets tagged sleeve_id="equity" with related group IDs.
        #
        # Portfolio remains authoritative after risk vetoes and partial fills.
        # Assignment/expiry events are applied by Portfolio, including events
        # supplied by Backtesting's simulator.
        # RiskManagement approves the combined portfolio; execution handles fills.
        #
        # A successful [] requests flattening the entire equity sleeve.
        # Missing data and unfinished functionality must raise explicit errors.
        raise NotImplementedError(
            "EquitySleeve orchestration has not been implemented."
        )