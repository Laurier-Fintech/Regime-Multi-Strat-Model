"""Skeleton for Sleeve B's stressed-regime index put spreads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from Sleeves.base_sleeve import SleeveContext, TargetPosition
from Sleeves.EquitySleeve.wheel import EquityInstruments

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True, slots=True)
class StressPutSpreadConfig:
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


class StressPutSpreadBuilder:
    """Propose desired put-spread legs for one underlying."""

    def __init__(
        self,
        config: StressPutSpreadConfig,
        instruments: EquityInstruments,
    ) -> None:
        if not isinstance(config, StressPutSpreadConfig):
            raise TypeError("config must be a StressPutSpreadConfig.")

        self._config = config
        self._instruments = instruments

    def build(
        self,
        context: SleeveContext,
        underlying: str,
        option_chain: pd.DataFrame,
    ) -> list[TargetPosition]:
        # 1. Validate the chain's underlying, information cutoff, and quotes.
        # 2. Select puts with the same expiry and compatible contract terms.
        # 3. Choose the higher-strike long put and lower-strike short put.
        # 4. Resolve exact canonical contracts using self._instruments.
        # 5. Size within this market's allocated budget, including costs.
        #    Financing and settlement risks require their own checks.
        # 6. Return signed integer quantities tagged sleeve_id="equity".
        # 7. Keep related legs under one group_id and preserve their ratio.
        #
        # These are desired total spread holdings, not orders.
        # Missing data or unfinished logic must raise an error.
        raise NotImplementedError(
            "Stress put-spread selection and sizing are not implemented."
        )