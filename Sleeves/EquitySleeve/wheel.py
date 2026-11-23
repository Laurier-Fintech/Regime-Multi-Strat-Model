"""Confirmed wheel state and configurable decision gates for Sleeve B.

Portfolio owns actual holdings, orders, cash, and lifecycle events.
Wheel decisions are proposals; they never create fills or assignments.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from math import isfinite
from numbers import Real
from typing import Protocol

from Sleeves.base_sleeve import SleeveContext


def _text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string.")


def _timestamp(name: str, value: datetime) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone.")


def _integer(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be a whole integer quantity.")


def _number(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number.")
    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")


def _attribution(instrument_id: str, strategy_id: str, group_id: str | None) -> None:
    _text("instrument_id", instrument_id)
    _text("strategy_id", strategy_id)
    if group_id is not None:
        _text("group_id", group_id)


@dataclass(frozen=True, slots=True)
class EquityInstrument:
    """A read-only view of details resolved through Common's contract master."""

    instrument_id: str
    underlying: str
    asset_type: str
    multiplier: float
    currency: str
    call_put: str | None = None

    # Pure share deliverables only. Common must reject cash baskets or other
    # adjusted terms it cannot represent with this view. Never assume 100.
    deliverable_shares: float | None = None
    # Required for new selection; optional for legacy held positions.
    expiry: date | None = None
    strike: float | None = None
    series_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("instrument_id", "underlying", "asset_type", "currency"):
            _text(name, getattr(self, name))
        _number("multiplier", self.multiplier)
        if self.multiplier <= 0:
            raise ValueError("multiplier must be positive.")
        if self.asset_type == "option":
            if self.call_put not in ("C", "P"):
                raise ValueError("An option must specify call_put='C' or 'P'.")
        elif self.call_put is not None or self.deliverable_shares is not None:
            raise ValueError("Option terms may only be supplied for options.")
        if self.deliverable_shares is not None:
            _number("deliverable_shares", self.deliverable_shares)
            if self.deliverable_shares <= 0 or self.deliverable_shares % 1 != 0:
                raise ValueError("Only positive whole-share deliverables are supported.")


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

    def __post_init__(self) -> None:
        _attribution(self.instrument_id, self.strategy_id, self.group_id)
        _integer("quantity", self.quantity)


@dataclass(frozen=True, slots=True)
class EquityOpenOrder:
    """A confirmed open order, with its signed unfilled quantity."""

    order_id: str
    instrument_id: str
    remaining_quantity: int
    strategy_id: str
    group_id: str | None = None

    def __post_init__(self) -> None:
        _text("order_id", self.order_id)
        _attribution(self.instrument_id, self.strategy_id, self.group_id)
        _integer("remaining_quantity", self.remaining_quantity)
        if self.remaining_quantity == 0:
            raise ValueError("An open order must have nonzero remaining quantity.")


@dataclass(frozen=True, slots=True)
class EquityLifecycleEvent:
    """An event already recorded and applied by Portfolio."""

    event_id: str
    instrument_id: str
    event_type: str
    occurred_at: datetime
    known_at: datetime

    def __post_init__(self) -> None:
        for name in ("event_id", "instrument_id", "event_type"):
            _text(name, getattr(self, name))
        _timestamp("occurred_at", self.occurred_at)
        _timestamp("known_at", self.known_at)
        if self.known_at < self.occurred_at:
            raise ValueError("An event cannot be known before it occurred.")


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

    def __post_init__(self) -> None:
        _text("sleeve_id", self.sleeve_id)
        _text("base_currency", self.base_currency)
        _timestamp("as_of", self.as_of)
        # A real funding deficit is represented by a negative available_cash.
        # It blocks new puts; the manager must not fabricate a positive balance.
        _number("available_cash", self.available_cash)
        for name, expected_type in (
            ("holdings", EquityHolding), ("open_orders", EquityOpenOrder),
            ("lifecycle_events", EquityLifecycleEvent),
        ):
            rows = getattr(self, name)
            if not isinstance(rows, tuple) or any(not isinstance(row, expected_type) for row in rows):
                raise TypeError(f"{name} must be a tuple of {expected_type.__name__} records.")
        holding_keys = [(row.strategy_id, row.instrument_id, row.group_id) for row in self.holdings]
        order_ids = [row.order_id for row in self.open_orders]
        event_ids = [row.event_id for row in self.lifecycle_events]
        for name, keys in (("holding attribution", holding_keys), ("order ID", order_ids), ("event ID", event_ids)):
            if len(keys) != len(set(keys)):
                raise ValueError(f"Duplicate {name} in Portfolio snapshot.")


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
    share_quantity: int
    short_put_contracts: int
    short_call_contracts: int
    call_share_obligation: int
    available_call_shares: int
    pending_order_ids: tuple[str, ...]
    wheel_order_ids: tuple[str, ...]
    entry_order_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WheelPlan:
    """Requested behavior, separate from the confirmed wheel state."""

    state: WheelState
    allow_new_puts: bool
    allow_covered_calls: bool
    exit_requested: bool
    reason: str
    # Cancellation intent only; Portfolio/Execution must confirm cancellation.
    # Existing risk-reducing orders are not automatically cancelled.
    cancel_order_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WheelConfig:
    """Uncalibrated policy thresholds supplied explicitly by configuration.

    New puts require both calm and calm-bull gates. Covered calls use the calm
    gate against confirmed eligible shares. Total stress has exit priority.
    """

    calm_entry_probability: float
    stress_exit_probability: float
    calm_bull_entry_probability: float
    strategy_id: str = "wheel"

    def __post_init__(self) -> None:
        for name in ("calm_entry_probability", "stress_exit_probability", "calm_bull_entry_probability"):
            value = getattr(self, name)
            _number(name, value)
            if not 0 < value <= 1:
                raise ValueError(f"{name} must be finite and in (0, 1].")
        _text("strategy_id", self.strategy_id)


class WheelManager:
    """Inspect confirmed state and propose regime-dependent wheel behavior."""

    @property
    def strategy_id(self):
        return self._config.strategy_id

    @property
    def instruments(self):
        return self._instruments

    def __init__(
        self,
        config: WheelConfig,
        instruments: EquityInstruments,
    ) -> None:
        if not isinstance(config, WheelConfig):
            raise TypeError("config must be a WheelConfig.")
        if not callable(getattr(instruments, "get_instrument", None)):
            raise TypeError("instruments must provide get_instrument().")

        self._config = config
        self._instruments = instruments

    def inspect(
        self,
        context: SleeveContext,
        underlying: str,
        portfolio: EquityPortfolioSnapshot,
    ) -> WheelState:
        """Classify confirmed wheel holdings and reserve worst-case call coverage.

        Events have already been applied by Portfolio. Pending buys never
        supply shares; pending call buys never release existing call coverage.
        Other strategies do not determine the wheel stage, but their calls
        and share-sale orders cannot reuse the same physical shares.
        """
        if not isinstance(context, SleeveContext):
            raise TypeError("context must be a SleeveContext.")
        _text("underlying", underlying)
        if not isinstance(portfolio, EquityPortfolioSnapshot):
            raise TypeError("portfolio must be an EquityPortfolioSnapshot.")
        if portfolio.sleeve_id != "equity":
            raise ValueError("Wheel inspection requires the equity sleeve snapshot.")
        if portfolio.as_of != context.as_of:
            raise ValueError("Portfolio snapshot must match the decision as_of exactly.")
        for event in portfolio.lifecycle_events:
            if event.known_at > context.as_of or event.occurred_at > context.as_of:
                raise ValueError("Portfolio contains a lifecycle event after the decision cutoff.")

        instruments: dict[str, EquityInstrument] = {}

        def resolve(instrument_id: str) -> EquityInstrument:
            if instrument_id not in instruments:
                instrument = self._instruments.get_instrument(instrument_id)
                if not isinstance(instrument, EquityInstrument) or instrument.instrument_id != instrument_id:
                    raise ValueError("Contract lookup must return the exact canonical EquityInstrument.")
                instruments[instrument_id] = instrument
            return instruments[instrument_id]

        def deliverable(instrument: EquityInstrument) -> int:
            if instrument.deliverable_shares is None:
                raise ValueError(f"Missing pure-share deliverable for {instrument.instrument_id}.")
            return int(instrument.deliverable_shares)

        def require_wheel_instrument(instrument: EquityInstrument) -> None:
            if instrument.currency != portfolio.base_currency:
                raise ValueError("Wheel instruments must match the snapshot base currency; FX is not inferred.")
            if instrument.asset_type in ("stock", "etf"):
                if instrument.multiplier != 1:
                    raise ValueError("Share holdings require multiplier=1.")
            elif instrument.asset_type == "option":
                deliverable(instrument)
            else:
                raise ValueError("Wheel supports shares and pure-share-deliverable options only.")

        shares = puts = calls = own_call_shares = 0
        total_shares = total_call_shares = 0
        own_pending_calls = own_share_sales = 0
        total_pending_calls = total_share_sales = 0
        pending_ids, wheel_ids, entry_ids = [], [], []
        short_inventory: dict[str, int] = {}
        closing_orders: dict[str, int] = {}

        for holding in portfolio.holdings:
            instrument = resolve(holding.instrument_id)
            if instrument.underlying != underlying or holding.quantity == 0:
                continue
            quantity = holding.quantity
            if instrument.asset_type in ("stock", "etf"):
                if instrument.multiplier != 1:
                    raise ValueError("Share holdings require multiplier=1.")
                total_shares += quantity
            elif instrument.asset_type == "option" and instrument.call_put == "C" and quantity < 0:
                total_call_shares += -quantity * deliverable(instrument)

            if holding.strategy_id != self._config.strategy_id:
                continue
            require_wheel_instrument(instrument)
            if instrument.asset_type in ("stock", "etf"):
                if quantity < 0:
                    raise ValueError("Short wheel share holdings are unsupported.")
                shares += quantity
            else:
                if quantity > 0:
                    raise ValueError("Long wheel option holdings are unsupported; check attribution.")
                short_inventory[holding.instrument_id] = short_inventory.get(holding.instrument_id, 0) - quantity
                if instrument.call_put == "P":
                    puts -= quantity
                else:
                    calls -= quantity
                    own_call_shares += -quantity * deliverable(instrument)

        for order in portfolio.open_orders:
            instrument = resolve(order.instrument_id)
            if instrument.underlying != underlying:
                continue
            pending_ids.append(order.order_id)
            quantity = order.remaining_quantity
            if instrument.asset_type in ("stock", "etf"):
                if instrument.multiplier != 1:
                    raise ValueError("Share orders require multiplier=1.")
                if quantity < 0:
                    total_share_sales -= quantity
            elif instrument.asset_type == "option" and instrument.call_put == "C" and quantity < 0:
                total_pending_calls += -quantity * deliverable(instrument)

            if order.strategy_id != self._config.strategy_id:
                continue
            require_wheel_instrument(instrument)
            wheel_ids.append(order.order_id)
            if instrument.asset_type in ("stock", "etf"):
                if quantity < 0:
                    own_share_sales -= quantity
                else:
                    entry_ids.append(order.order_id)
            elif quantity < 0:
                entry_ids.append(order.order_id)
                if instrument.call_put == "C":
                    own_pending_calls += -quantity * deliverable(instrument)
            else:
                closing_orders[order.instrument_id] = closing_orders.get(order.instrument_id, 0) + quantity

        if any(quantity > short_inventory.get(instrument_id, 0) for instrument_id, quantity in closing_orders.items()):
            raise ValueError("Wheel option buy orders exceed confirmed short inventory; long option entries are unsupported.")
        own_free = shares - own_call_shares - own_pending_calls - own_share_sales
        global_free = total_shares - total_call_shares - total_pending_calls - total_share_sales
        if own_call_shares + own_pending_calls > 0 and (own_free < 0 or global_free < 0):
            raise ValueError("Wheel calls lack confirmed share coverage under worst-case pending fills.")
        if own_share_sales > shares:
            raise ValueError("Pending wheel share sales exceed confirmed wheel shares.")
        active = sum((shares > 0, puts > 0, calls > 0))
        if active == 0:
            stage = WheelStage.FLAT
        elif puts > 0 and (shares > 0 or calls > 0):
            stage = WheelStage.MIXED
        elif calls > 0:
            stage = WheelStage.COVERED_CALLS
        elif shares > 0:
            stage = WheelStage.HOLDING_SHARES
        else:
            stage = WheelStage.SHORT_PUTS
        return WheelState(
            underlying, stage, portfolio, shares, puts, calls, own_call_shares,
            max(0, min(own_free, global_free)), tuple(sorted(pending_ids)),
            tuple(sorted(wheel_ids)), tuple(sorted(entry_ids)),
        )

    def plan(
        self,
        context: SleeveContext,
        state: WheelState,
    ) -> WheelPlan:
        """Propose entry/hold/exit intent, preserving Portfolio as book of record.

        Threshold equality triggers the gate. Stress exits take precedence,
        followed by a zero capital budget. Pending orders pause new entries.
        New puts need calm AND calm-bull gates and an otherwise flat wheel.
        Covered calls need calm and confirmed unreserved shares. No prices or
        strikes are selected here, so eligibility is not a collateral guarantee.
        """
        if not isinstance(state, WheelState):
            raise TypeError("state must be a WheelState.")
        confirmed = self.inspect(context, state.underlying, state.portfolio_snapshot)
        if state != confirmed:
            raise ValueError("WheelState does not match its confirmed Portfolio snapshot.")
        regime = context.market_regime
        has_work = state.stage != WheelStage.FLAT or bool(state.wheel_order_ids)
        if regime.stressed >= self._config.stress_exit_probability:
            return WheelPlan(
                state, False, False, has_work,
                f"Stress exit gate: stressed={regime.stressed:.4f}; no new wheel exposure.",
                state.entry_order_ids,
            )
        if context.capital_budget == 0:
            return WheelPlan(
                state, False, False, has_work,
                "Zero capital budget: close wheel exposure and cancel pending entries.",
                state.entry_order_ids,
            )
        if state.pending_order_ids:
            return WheelPlan(state, False, False, False, "Pending orders for this underlying: await confirmed fills/cancellations.")
        if regime.calm < self._config.calm_entry_probability:
            return WheelPlan(state, False, False, False, "Calm gate not met: hold/manage existing inventory without new entries.")

        allow_puts = (
            state.stage == WheelStage.FLAT
            and regime.calm_bull >= self._config.calm_bull_entry_probability
            and state.portfolio_snapshot.available_cash > 0
        )
        allow_calls = state.available_call_shares > 0
        return WheelPlan(
            state, allow_puts, allow_calls, False,
            f"Calm gate met: calm={regime.calm:.4f}, calm-bull={regime.calm_bull:.4f}; "
            f"new_puts={allow_puts}, covered_calls={allow_calls}. "
            "Builders must still check selected-contract coverage, collateral and allocated budget.",
        )
