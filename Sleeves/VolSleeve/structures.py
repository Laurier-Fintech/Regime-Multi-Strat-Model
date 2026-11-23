"""Exact-expiry straddles/strangles with canonical contracts and gross reserves."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from datetime import date
from typing import TYPE_CHECKING

from Sleeves.base_sleeve import SleeveContext, TargetPosition
from Sleeves.VolSleeve.signal import VolSignal, VolDirection
from Common.targeting import (SelectionPolicy, CapitalModel, MarketLookup, chain_rows,
    market_at, resolved, compatible, require_option_funding, sized)

# This import is only needed by static type checkers.
# Importing this module does not require pandas to be loaded.
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
    selection: SelectionPolicy

    def __post_init__(self) -> None:
        if not isinstance(self.selection, SelectionPolicy):
            raise TypeError('selection must be a SelectionPolicy.')
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
    underlying: str
    expiry: date
    strike: float
    call_put: str
    # Exact settlement/exercise/deliverable family from Common, not a ticker.
    series_id: str


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
        *,
        market_lookup: MarketLookup,
        capital_model: CapitalModel,
    ) -> None:
        if not isinstance(config, StructureConfig):
            raise TypeError("config must be a StructureConfig.")

        if not callable(contract_lookup):
            raise TypeError("contract_lookup must be callable.")

        self._config = config
        self._contract_lookup = contract_lookup
        self._market_lookup = market_lookup
        self.capital_model = capital_model
        if capital_model.base_currency != config.selection.base_currency:
            raise ValueError('Selection and capital currencies must match.')

    def build(
        self,
        context: SleeveContext,
        signal: VolSignal,
        option_chain: pd.DataFrame,
        *,
        horizon_end: date,
    ) -> list[TargetPosition]:
        """Return desired option holdings for the signal's underlying.

        The caller supplies an option chain read through access.py.
        VolSleeve will combine these legs with other markets and hedge targets
        before returning the sleeve's complete desired holdings.
        """

        if not isinstance(signal, VolSignal) or signal.as_of != context.as_of:
            raise ValueError('Signal must match the decision timestamp.')
        # Neutral means unwind, including existing hedges, not hold indefinitely.
        if signal.direction == VolDirection.NEUTRAL or context.capital_budget == 0:
            return []
        if type(horizon_end) is not date:
            raise ValueError('An explicit session-aligned horizon_end is required.')
        cfg, policy = self._config, self._config.selection
        spot = market_at(self._market_lookup, signal.underlying, context, policy).spot
        rows = chain_rows(option_chain, signal.underlying, context, policy,
                          cfg.min_dte_calendar_days, cfg.max_dte_calendar_days, expiry=horizon_end)
        family = cfg.long_vol_structure if signal.direction == VolDirection.LONG_VOL else cfg.short_vol_structure
        pairs = []
        for put in (r for r in rows if r['call_put'] == 'P'):
            for call in (r for r in rows if r['call_put'] == 'C'):
                if family == StructureType.STRADDLE and put['strike'] == call['strike']:
                    pairs.append((abs(put['strike'] - spot), put['strike'], put, call))
                elif family == StructureType.STRANGLE and put['strike'] < spot < call['strike']:
                    pairs.append((spot - put['strike'] + call['strike'] - spot, put['strike'], put, call))
        if not pairs:
            raise LookupError('No complete quoted structure at the forecast expiry.')
        _, _, put, call = min(pairs, key=lambda p: p[:2])
        a, b = [resolved(self._contract_lookup, row, policy) for row in (put, call)]
        compatible(a, b)
        side = 1 if signal.direction == VolDirection.LONG_VOL else -1
        if side < 0 and min(put['bid'], call['bid']) <= 0:
            raise ValueError('Short option entries require positive bids.')
        for contract, row in ((a, put), (b, call)):
            require_option_funding(self.capital_model, contract, row, side, context, policy)
        group = f'vol:{signal.underlying}:{horizon_end}:{family.value}:{a.instrument_id}:{b.instrument_id}'
        lot = [TargetPosition('vol', c.instrument_id, side, group) for c in (a, b)]
        return sized(context, lot, self.capital_model, policy.max_contracts)
