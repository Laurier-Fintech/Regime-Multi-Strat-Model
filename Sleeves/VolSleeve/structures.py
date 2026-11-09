"""Skeleton for selecting and sizing Sleeve A's option structures.

The builder returns desired option holdings for one underlying.
Contract selection and sizing remain to be implemented.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from Sleeves.base_sleeve import SleeveContext, TargetPosition
from Sleeves.VolSleeve.signal import VolSignal

# This import is only needed by static type checkers.
# Importing this skeleton does not require pandas to be loaded.
if TYPE_CHECKING:
    import pandas as pd


class StructureType(str, Enum):
    """Initial option-combination families available for configuration."""

    STRADDLE = "straddle"
    STRANGLE = "strangle"


@dataclass(frozen=True, slots=True)
class StructureConfig:
    """Structure preferences and expiry bounds supplied by configuration."""

    # These are preferences; the builder still needs suitable quoted contracts.
    long_vol_structure: StructureType
    short_vol_structure: StructureType

    # Option-chain expiries use calendar days.
    # The volatility forecast uses trading days and must be aligned separately.
    min_dte_calendar_days: int
    max_dte_calendar_days: int

    def __post_init__(self) -> None:
        for name in ("long_vol_structure", "short_vol_structure"):
            if not isinstance(getattr(self, name), StructureType):
                raise TypeError(f"{name} must be a StructureType.")

        for name in ("min_dte_calendar_days", "max_dte_calendar_days"):
            value = getattr(self, name)

            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer.")

            if value <= 0:
                raise ValueError(f"{name} must be positive.")

        if self.min_dte_calendar_days > self.max_dte_calendar_days:
            raise ValueError("Minimum DTE cannot exceed maximum DTE.")


@dataclass(frozen=True, slots=True)
class OptionContractRef:
    """Read-only contract details returned by an adapter to Common.

    Common's contract master remains authoritative.
    This record contains the selected contract's sizing details.
    """

    instrument_id: str
    multiplier: float
    currency: str


# The lookup receives fields describing one selected option-chain contract.
# It must resolve the exact contract or raise an error.
# A provider contract_id must not be assumed to be our canonical instrument_id.
OptionContractLookup = Callable[[Mapping[str, object]], OptionContractRef]


class OptionStructureBuilder:
    """Turn one market's volatility signal into desired option-leg holdings."""

    def __init__(
        self,
        config: StructureConfig,
        contract_lookup: OptionContractLookup,
    ) -> None:
        if not isinstance(config, StructureConfig):
            raise TypeError("config must be a StructureConfig.")

        if not callable(contract_lookup):
            raise TypeError("contract_lookup must be callable.")

        self._config = config
        self._contract_lookup = contract_lookup

    def build(
        self,
        context: SleeveContext,
        signal: VolSignal,
        option_chain: pd.DataFrame,
    ) -> list[TargetPosition]:
        """Return desired option holdings for the signal's underlying.

        The caller supplies an option chain read through access.py.
        VolSleeve will combine these legs with other markets and hedge targets
        before returning the sleeve's complete desired holdings.
        """

        # Implementation steps:
        # 1. Validate the signal, decision time, and option-chain data.
        # 2. Define neutral-signal behavior explicitly.
        # 3. Choose the configured long-vol or short-vol structure.
        # 4. Select an expiry compatible with the forecast window and DTE bounds.
        # 5. Select suitable strikes and check quote freshness and liquidity.
        # 6. Resolve each exact instrument using self._contract_lookup.
        # 7. Size the structure within the supplied capital budget, accounting
        #    for multipliers, currency, collateral, and the chosen sizing policy.
        # 8. Create TargetPosition records with sleeve_id="vol".
        # 9. Give related legs one shared group_id and preserve their ratios.
        #
        # Portfolio-wide approval belongs to RiskManagement.
        # Portfolio and Execution handle orders and fills.

        # An unfinished builder must fail explicitly.
        # An empty result could otherwise be interpreted as a flatten request.
        raise NotImplementedError(
            "Option contract selection and structure sizing "
            "have not been implemented."
        )