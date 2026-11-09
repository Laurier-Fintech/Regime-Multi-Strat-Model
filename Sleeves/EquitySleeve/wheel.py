"""Read-only Portfolio views and wheel decision interfaces for Sleeve B.

Portfolio owns actual holdings, orders, cash, and lifecycle events.
Wheel decisions are proposals; they never create fills or assignments.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Protocol

from Sleeves.base_sleeve import SleeveContext


@dataclass(frozen=True, slots=True)
class EquityInstrument:
    """A read-only view of details resolved through Common's contract master."""

    instrument_id: str
    underlying: str
    asset_type: str
    multiplier: float
    currency: str
    call_put: str | None = None

    # Required for share-covered options; unsupported deliverables must fail.
    # Never assume that every option delivers 100 shares.
    deliverable_shares: float | None = None


class EquityInstruments(Protocol):
    """Adapter interface to Common; this does not create a second master."""

    def resolve_option(self, fields: Mapping[str, object]) -> EquityInstrument:
        """Resolve the exact quoted contract to its canonical instrument ID."""
        raise NotImplementedError

    def get_instrument(self, instrument_id: str) -> EquityInstrument:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class EquityHolding:
    """One confirmed, strategy-attributed slice of an actual holding."""

    instrument_id: str
    quantity: int
    strategy_id: str
    group_id: str | None = None


@dataclass(frozen=True, slots=True)
class EquityOpenOrder:
    """A confirmed open order, with its signed unfilled quantity."""

    order_id: str
    instrument_id: str
    remaining_quantity: int
    strategy_id: str
    group_id: str | None = None


@dataclass(frozen=True, slots=True)
class EquityLifecycleEvent:
    """An event already recorded and applied by Portfolio."""

    event_id: str
    instrument_id: str
    event_type: str
    occurred_at: datetime
    known_at: datetime


@dataclass(frozen=True, slots=True)
class EquityPortfolioSnapshot:
    """Portfolio's read-only view at one information cutoff.

    Holding slices must reconcile to actual net holdings.
    Strategy/group attribution must be supplied, never guessed from puts alone.
    Attribution persistence remains an integration task with the schema owner.
    """

    sleeve_id: str
    as_of: datetime
    base_currency: str

    # Portfolio-reported available cash under its reservation policy.
    # New allocations must also respect the sleeve's capital budget.
    available_cash: float

    holdings: tuple[EquityHolding, ...]
    open_orders: tuple[EquityOpenOrder, ...]
    lifecycle_events: tuple[EquityLifecycleEvent, ...]


class EquityPortfolio(Protocol):
    """Live/simulated book interface; not a post-run reporting query."""

    def get_snapshot(
        self,
        *,
        sleeve_id: str,
        as_of: datetime,
    ) -> EquityPortfolioSnapshot:
        raise NotImplementedError


class WheelStage(str, Enum):
    FLAT = "flat"
    SHORT_PUTS = "short_puts"
    HOLDING_SHARES = "holding_shares"
    COVERED_CALLS = "covered_calls"

    # Partial fills/assignments can leave several exposures simultaneously.
    MIXED = "mixed"


@dataclass(frozen=True, slots=True)
class WheelState:
    """Classification derived from a confirmed Portfolio snapshot."""

    underlying: str
    stage: WheelStage
    portfolio_snapshot: EquityPortfolioSnapshot


@dataclass(frozen=True, slots=True)
class WheelPlan:
    """Requested behavior, separate from the confirmed wheel state."""

    state: WheelState
    allow_new_puts: bool
    allow_covered_calls: bool
    exit_requested: bool
    reason: str


@dataclass(frozen=True, slots=True)
class WheelConfig:
    """Planned regime gates; values will be supplied through configuration."""

    calm_entry_probability: float
    stress_exit_probability: float

    def __post_init__(self) -> None:
        for name in ("calm_entry_probability", "stress_exit_probability"):
            value = getattr(self, name)

            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number.")

            if not isfinite(value) or not 0 < value <= 1:
                raise ValueError(f"{name} must be finite and in (0, 1].")


class WheelManager:
    """Inspect confirmed state and propose regime-dependent wheel behavior."""

    def __init__(
        self,
        config: WheelConfig,
        instruments: EquityInstruments,
    ) -> None:
        if not isinstance(config, WheelConfig):
            raise TypeError("config must be a WheelConfig.")

        self._config = config
        self._instruments = instruments

    def inspect(
        self,
        context: SleeveContext,
        underlying: str,
        portfolio: EquityPortfolioSnapshot,
    ) -> WheelState:
        # Validate sleeve, timestamps, holdings, orders, and event cutoffs.
        # Separate wheel inventory from stress-spread inventory by attribution.
        # Classify actual exposures, including partial fills and assignments.
        # Flag unsupported/inconsistent coverage explicitly.
        # Events have already changed Portfolio's books: never apply them twice.
        raise NotImplementedError(
            "Wheel state classification is not implemented."
        )

    def plan(
        self,
        context: SleeveContext,
        state: WheelState,
        *,
        calm_probability: float,
        stress_probability: float,
    ) -> WheelPlan:
        # Validate probabilities and match the snapshot to the decision time.
        # Apply the configured entry/exit gates and resolve conflicting intents.
        # Account for existing orders and reserved share/cash capacity.
        # An exit request remains a proposal until Portfolio confirms fills.
        raise NotImplementedError(
            "Wheel decision rules are not implemented."
        )