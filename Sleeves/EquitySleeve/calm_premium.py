"""Skeleton for Sleeve B's calm-regime premium strategies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from Sleeves.base_sleeve import SleeveContext, TargetPosition
from Sleeves.EquitySleeve.wheel import EquityInstruments, WheelPlan

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True, slots=True)
class CalmPremiumConfig:
    """Expiry bounds supplied by configuration, in calendar days."""

    min_dte_calendar_days: int
    max_dte_calendar_days: int

    def __post_init__(self) -> None:
        for name in ("min_dte_calendar_days", "max_dte_calendar_days"):
            value = getattr(self, name)

            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer.")

            if value <= 0:
                raise ValueError(f"{name} must be positive.")

        if self.min_dte_calendar_days > self.max_dte_calendar_days:
            raise ValueError("Minimum DTE cannot exceed maximum DTE.")


class CalmPremiumBuilder:
    """Propose a complete desired wheel book for one underlying."""

    def __init__(
        self,
        config: CalmPremiumConfig,
        instruments: EquityInstruments,
    ) -> None:
        if not isinstance(config, CalmPremiumConfig):
            raise TypeError("config must be a CalmPremiumConfig.")

        self._config = config
        self._instruments = instruments

    def build(
        self,
        context: SleeveContext,
        plan: WheelPlan,
        option_chain: pd.DataFrame,
    ) -> list[TargetPosition]:
        # 1. Validate the plan, snapshot, underlying, and quote availability.
        # 2. Resolve canonical contracts and their exact deliverable terms.
        # 3. Select OTM puts when the plan permits new put exposure.
        # 4. Enforce the chosen cash/collateral policy and allocated budget.
        # 5. Select covered calls only against confirmed, eligible shares.
        #    Account for existing short calls and unfilled sell-call orders.
        #    Proposed share purchases do not provide confirmed coverage.
        # 6. Preserve desired share holdings explicitly in the returned book.
        #    Omitting them from the final sleeve targets would request zero.
        # 7. Implement explicit hold/exit behavior, even when entries are barred.
        # 8. Tag targets sleeve_id="equity" and preserve related group IDs.
        #
        # Coordinate call unwinds and share exits through Portfolio/Execution.
        # Partial fills must not silently leave calls uncovered.
        # Never update the actual wheel state from these proposed targets.
        raise NotImplementedError(
            "Calm premium selection, coverage, and exit logic are not implemented."
        )