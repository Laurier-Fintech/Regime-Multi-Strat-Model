"""Sleeve A's desired whole-unit delta-hedge holdings.

Common supplies instrument sensitivities and contract specifications.
Portfolio converts approved target holdings into orders.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from math import floor, fsum, isfinite
from numbers import Real
from Common.targeting import combine

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

    def __post_init__(self):
        for value in (self.instrument_id, self.risk_factor_id, self.currency):
            if not isinstance(value, str) or not value.strip():
                raise ValueError('Delta identifiers and currency must be nonempty.')
        if not isinstance(self.as_of, datetime) or self.as_of.utcoffset() is None:
            raise ValueError('Delta timestamp must be timezone aware.')
        value = self.cash_delta_per_unit
        if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
            raise ValueError('Cash delta must be finite and numeric.')


# Receives a canonical instrument ID and the decision's information cutoff.
# The adapter must use only data available by that cutoff.
# Missing or unusable sensitivities must raise an explicit error.
DeltaLookup = Callable[[str, datetime], DeltaSnapshot]


class DeltaHedger:
    """Calculate desired hedge holdings for Sleeve A's proposed option book."""

    @property
    def base_currency(self):
        return self._config.base_currency

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

        if not isinstance(context, SleeveContext):
            raise TypeError('context must be a SleeveContext.')
        targets = combine(option_targets, 'vol')

        def lookup(instrument_id):
            row = self._delta_lookup(instrument_id, context.as_of)
            if not isinstance(row, DeltaSnapshot) or row.instrument_id != instrument_id or row.as_of != context.as_of:
                raise ValueError('Delta lookup must match instrument and decision timestamp exactly.')
            if row.currency != self._config.base_currency:
                raise ValueError('Delta currency does not match base currency.')
            return row

        by_factor = {}
        for target in targets:
            if target.instrument_id in self._config.hedge_instruments.values():
                raise ValueError('Option target cannot also be a hedge instrument.')
            row = lookup(target.instrument_id)
            by_factor.setdefault(row.risk_factor_id, []).append(target.target_quantity * row.cash_delta_per_unit)
        result, used = [], set()
        for factor, values in sorted(by_factor.items()):
            delta = fsum(values)
            if not isfinite(delta):
                raise ValueError('Aggregate delta overflow.')
            if factor not in self._config.hedge_instruments:
                raise ValueError(f'Missing hedge mapping for {factor}.')
            instrument_id = self._config.hedge_instruments[factor]
            if instrument_id in used:
                raise ValueError('One hedge cannot represent multiple independent risk factors.')
            used.add(instrument_id)
            hedge = lookup(instrument_id)
            if hedge.risk_factor_id != factor or hedge.cash_delta_per_unit == 0:
                raise ValueError('Hedge factor mismatch or zero sensitivity.')
            desired = -delta / hedge.cash_delta_per_unit
            if not isfinite(desired):
                raise ValueError('Hedge quantity overflow.')
            # Nearest whole unit, exact ties away from zero. Residual <= half
            # one hedge unit; Risk must assess whether that is acceptable.
            quantity = (1 if desired >= 0 else -1) * floor(abs(desired) + 0.5)
            if quantity:
                result.append(TargetPosition('vol', instrument_id, quantity, f'vol:hedge:{factor}'))
        return result
