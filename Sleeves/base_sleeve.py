"""Shared decision inputs and desired-position outputs for all sleeves.

Capital budgets use the portfolio's base currency. Quantities use whole
shares or contracts. Volatility inputs use annualized decimals.
Instrument specifications and multipliers belong in Common/instruments.py.
"""
# ABC define a shared templace for the actual strat. class, abtractmethod is method that each startegy must implement
from abc import ABC, abstractmethod
from dataclasses import dataclass # Auto creates init and repr method (methods that recieve field values when object is created, and gives object printed rep.)
from datetime import datetime # Rep. date and time, including timezone
from math import isclose, isfinite # bruh ik what this means type shi
from types import MappingProxyType # Provides read-only view of a dictionary
from typing import Mapping # idek but if chat says so then yes sir

# Prevent normal reassignment of fields, gives instance fixed set of declared attributes
@dataclass(frozen=True, slots=True)
class SleeveContext:
    """Decision inputs supplied by ModelHome for one sleeve."""

    # Latest info. cut off for the decision being made in sleeve
    as_of: datetime
    capital_budget: float
    # Regime probabilities supplied by ModelHome
    regime_probabilities: Mapping[str, float]

    # A Dataclass calls this function automatically after assigning its fields, use it to reject invalid inputs immediately
    def __post_init__(self) -> None:
        if not isinstance(self.as_of, datetime):
            raise TypeError("as_of must be a datetime.")
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("as_of must include a timezone.")
        if not isfinite(self.capital_budget) or self.capital_budget < 0:
            raise ValueError("capital_budget must be finite and nonnegative.")

        #Copy supplied probabilities into a new dictionary
        probabilities = dict(self.regime_probabilities)
        if not probabilities:
            raise ValueError("regime_probabilities must contain at least one regime.")

        for regime, probability in probabilities.items():
            if not isinstance(regime, str) or not regime.strip():
                raise ValueError("Regime names must be nonempty strings.")
            if not isfinite(probability) or not 0 <= probability <= 1:
                raise ValueError(
                    "Regime probabilities must be finite and between 0 and 1."
                )

        if not isclose(sum(probabilities.values()), 1.0, rel_tol=0.0, abs_tol=1e-8):
            raise ValueError("Regime probabilities must sum to 1.")

        object.__setattr__(
            self, "regime_probabilities", MappingProxyType(probabilities)
        )

# Output record protected against ordinary field assignment
@dataclass(frozen=True, slots=True)
class TargetPosition:
    """A sleeve's desired total holding in one exact instrument.

    Positive quantities are long and negative quantities are short.
    group_id links related legs and must be preserved downstream.
    """

    # Identifies sleeve proposing strategy, unique identifier for the instrument (contract and specifications), quantity wanted to be held after rebalancing, optional identifier linking related positions
    sleeve_id: str
    instrument_id: str
    target_quantity: int
    group_id: str | None = None

    # Validate output record as soon as created
    def __post_init__(self) -> None:
        if not isinstance(self.sleeve_id, str) or not self.sleeve_id.strip():
            raise ValueError("sleeve_id must be a nonempty string.")
        if not isinstance(self.instrument_id, str) or not self.instrument_id.strip():
            raise ValueError("instrument_id must be a nonempty string.")

        if isinstance(self.target_quantity, bool) or not isinstance(
            self.target_quantity, int
        ):
            raise TypeError("target_quantity must be an integer number of shares or contracts.")
        if self.group_id is not None and (
            not isinstance(self.group_id, str) or not self.group_id.strip()
        ):
            raise ValueError("group_id must be a nonempty string when supplied.")

# Inheriting from ABC, makes this an abtract base class
# Actual VolSleeve and EquitySleeve classes inherit this interface
class BaseSleeve(ABC):
    """Common interface implemented by each sleeve.

    Concrete sleeves receive configuration and read-only market-data and
    Portfolio dependencies during construction. Each data request must
    respect context.as_of. Portfolio remains the source of actual holdings,
    fills, and lifecycle events.
    """

    # Each concrete sleeve must provide its own implementation of this method.
    @abstractmethod
    def generate_targets(self, context: SleeveContext) -> list[TargetPosition]:
        """Return the complete desired holdings for this sleeve only.

        Portfolio calculates orders from risk-approved targets and actual
        holdings. An omitted holding has a target of zero. An empty list
        explicitly requests closing all holdings belonging to this sleeve.

        Missing required data and unfinished logic must raise an error.
        Related legs must retain their group_id. Portfolio-wide risk checks
        and order placement are handled by their respective system layers.
        """
        raise NotImplementedError
