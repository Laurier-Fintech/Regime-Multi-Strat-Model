"""Skeleton for Sleeve A's desired delta-hedge holdings.

Common supplies instrument sensitivities and contract specifications.
Portfolio converts approved target holdings into orders.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from Sleeves.base_sleeve import SleeveContext, TargetPosition


@dataclass(frozen=True, slots=True)
class DeltaHedgeConfig:
    """Hedge instruments and reporting currency supplied by configuration."""

    # The portfolio's base currency.
    base_currency: str

    # Maps a named risk factor to an exact canonical hedge instrument ID.
    # ETF IDs and dated futures contracts must resolve through Common.
    hedge_instruments: Mapping[str, str]

    def __post_init__(self) -> None:
        if not isinstance(self.base_currency, str) or not self.base_currency.strip():
            raise ValueError("base_currency must be a nonempty string.")

        instruments = dict(self.hedge_instruments)

        if not instruments:
            raise ValueError("At least one hedge instrument is required.")

        for factor, instrument_id in instruments.items():
            if not isinstance(factor, str) or not factor.strip():
                raise ValueError("Risk factor IDs must be nonempty strings.")

            if not isinstance(instrument_id, str) or not instrument_id.strip():
                raise ValueError("Hedge instrument IDs must be nonempty strings.")

        # Copy and protect the mapping against later changes by the caller.
        object.__setattr__(
            self, "hedge_instruments", MappingProxyType(instruments)
        )


@dataclass(frozen=True, slots=True)
class DeltaSnapshot:
    """One instrument's sensitivity under a shared hedging convention."""

    instrument_id: str
    risk_factor_id: str
    as_of: datetime

    # Must match the configured portfolio base currency.
    currency: str

    # Estimated first-order P&L for a +1% move in the named risk factor,
    # per ONE share or contract.
    #
    # The Common adapter must already include the contract multiplier,
    # currency conversion, and mapping to the specified risk factor.
    # Option and hedge sensitivities must use this same convention.
    cash_delta_per_unit: float


# Receives a canonical instrument ID and the decision's information cutoff.
# The adapter must use only data available by that cutoff.
# Missing or unusable sensitivities must raise an explicit error.
DeltaLookup = Callable[[str, datetime], DeltaSnapshot]


class DeltaHedger:
    """Calculate desired hedge holdings for Sleeve A's proposed option book."""

    def __init__(
        self,
        config: DeltaHedgeConfig,
        delta_lookup: DeltaLookup,
    ) -> None:
        if not isinstance(config, DeltaHedgeConfig):
            raise TypeError("config must be a DeltaHedgeConfig.")

        if not callable(delta_lookup):
            raise TypeError("delta_lookup must be callable.")

        self._config = config
        self._delta_lookup = delta_lookup

    def build(
        self,
        context: SleeveContext,
        option_targets: list[TargetPosition],
    ) -> list[TargetPosition]:
        """Return the complete desired hedge holdings for this option target book.

        option_targets contains Sleeve A's complete desired OPTION holdings.
        Existing hedge positions are handled through Portfolio's rebalancing.

        The result contains hedge targets only. VolSleeve will combine these
        with the option targets before returning the sleeve's complete book.
        """

        # Implementation steps:
        # 1. Validate context and the supplied option targets.
        # 2. Obtain each option's sensitivity using self._delta_lookup.
        # 3. Validate timestamps, currencies, risk factors, and finite values.
        # 4. Sum target_quantity * cash_delta_per_unit for each risk factor.
        # 5. Resolve that factor's configured hedge and obtain its sensitivity.
        # 6. Calculate the desired hedge quantity:
        #
        #       hedge quantity = -option cash delta / hedge cash delta per unit
        #
        # 7. Reject missing, zero, or incompatible hedge sensitivities.
        # 8. Apply the agreed whole-unit rounding and residual-delta policy.
        # 9. Return TargetPosition records with sleeve_id="vol".
        #
        # Preserve option group IDs. Attribution of a shared hedge across
        # multiple option groups remains an integration decision.
        # Funding, collateral, and risk approval must cover the combined book.
        #
        # These are desired TOTAL hedge holdings, not incremental orders.
        # Portfolio calculates changes from its actual holdings.
        # Risk adjustments to option targets may require the hedge to be
        # recalculated or the combined exposure to be checked again.

        raise NotImplementedError(
            "Delta aggregation and hedge sizing have not been implemented."
        )