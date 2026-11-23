"""Validated volatility comparisons and an explicit stress veto for short vol.

All volatility values use annualized decimals.
Missing or misaligned inputs raise rather than producing a neutral decision.
"""

# Baseline comparison:
#
# Comparison                              Signal
# Implied volatility sufficiently          Consider short volatility
# above forecast
#
# Implied volatility sufficiently          Consider long volatility
# below forecast
#
# Difference too small                    Neutral
#
# Regime probabilities may modify this baseline interpretation.

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from math import isclose, isfinite

from Sleeves.base_sleeve import SleeveContext
from Sleeves.VolSleeve.rv_forecast import (
    RVForecast, _validate_horizon, _validate_identity, _validate_volatility,
)


# An Enum defines a fixed set of named choices.
# These describe volatility exposure, rather than specific option orders.
class VolDirection(str, Enum):
    LONG_VOL = "long_vol"
    SHORT_VOL = "short_vol"
    NEUTRAL = "neutral"


@dataclass(frozen=True, slots=True)
class ImpliedVolSnapshot:
    """One implied-volatility observation supplied by the data adapter.

    The adapter must align its future window with the forecast horizon.
    Provider calendar-day tenors require conversion before creating this record.
    """

    # Database identifier for the underlying, such as "spy".
    underlying: str

    # When the market observation was made.
    observed_at: datetime

    # When that observation became available to the system.
    known_at: datetime

    # Future trading-day window represented by this volatility measurement.
    horizon_trading_days: int

    # Example: 0.25 means 25% annualized implied volatility.
    annualized_vol: float
    source_underlying: str | None = None
    source: str | None = None
    horizon_end: date | None = None
    tenor_days_used: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        _validate_identity(self.underlying, self.observed_at)
        _validate_identity(self.underlying, self.known_at)
        _validate_horizon(self.horizon_trading_days)
        _validate_volatility("annualized_vol", self.annualized_vol)
        if self.known_at < self.observed_at:
            raise ValueError("IV cannot be known before its observation.")
        for value in (self.source_underlying, self.source):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError("IV source identifiers must be nonempty strings.")
        if self.horizon_end is not None:
            if not isinstance(self.horizon_end, date) or isinstance(self.horizon_end, datetime):
                raise TypeError("horizon_end must be a date.")
            if self.horizon_end <= self.observed_at.date():
                raise ValueError("horizon_end must follow the observation date.")
        if not isinstance(self.tenor_days_used, tuple):
            raise TypeError("tenor_days_used must be a tuple.")
        for tenor in self.tenor_days_used:
            _validate_horizon(tenor)


@dataclass(frozen=True, slots=True)
class VolSignalConfig:
    """Settings supplied when constructing the signal generator."""

    # Minimum volatility gap required by the baseline comparison.
    # Example units: 0.02 means two volatility percentage points.
    # The actual value must come from configuration.
    min_edge: float
    stress_block_short_probability: float
    max_iv_age: timedelta

    def __post_init__(self) -> None:
        if isinstance(self.min_edge, bool) or not isinstance(
            self.min_edge, (int, float)
        ):
            raise TypeError("min_edge must be a number.")

        if not isfinite(self.min_edge) or self.min_edge <= 0:
            raise ValueError("min_edge must be finite and positive.")
        probability = self.stress_block_short_probability
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            raise TypeError("stress_block_short_probability must be a number.")
        if not isfinite(probability) or not 0 < probability <= 1:
            raise ValueError("stress_block_short_probability must be in (0, 1].")
        if not isinstance(self.max_iv_age, timedelta) or self.max_iv_age < timedelta(0):
            raise ValueError("max_iv_age must be a nonnegative timedelta.")


@dataclass(frozen=True, slots=True)
class VolSignal:
    """The volatility exposure proposed for one market and future window."""

    underlying: str
    as_of: datetime
    horizon_trading_days: int

    # One of the three choices defined by VolDirection.
    direction: VolDirection

    # Implied volatility minus forecast realized volatility.
    # This records a volatility difference in annualized decimal units.
    edge: float

    # Explanation of the decision, including any regime adjustment.
    reason: str

    def __post_init__(self) -> None:
        _validate_identity(self.underlying, self.as_of)
        _validate_horizon(self.horizon_trading_days)
        if not isinstance(self.direction, VolDirection):
            raise TypeError("direction must be a VolDirection.")
        if isinstance(self.edge, bool) or not isinstance(self.edge, (int, float)) or not isfinite(self.edge):
            raise ValueError("edge must be a finite number.")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("reason must explain the decision.")


class VolSignalGenerator:
    """Combine forecast volatility, implied volatility, and regime information."""

    def __init__(self, config: VolSignalConfig) -> None:
        if not isinstance(config, VolSignalConfig):
            raise TypeError("config must be a VolSignalConfig instance.")

        # Keep the supplied settings available for future generate() calls.
        self._config = config

    def generate(
        self,
        context: SleeveContext,
        forecast: RVForecast,
        implied_vol: ImpliedVolSnapshot,
    ) -> VolSignal:
        """Compare aligned volatilities; high stress vetoes a short-vol entry.

        Positive edge at/above min_edge proposes short volatility unless total
        stress meets its veto threshold. Negative edge at/below -min_edge
        proposes long volatility. Otherwise neutral. Stress alone never forces
        a long trade. Both stress directions count equally for this vol policy.
        """
        if not isinstance(context, SleeveContext) or not isinstance(forecast, RVForecast):
            raise TypeError("Supply a SleeveContext and RVForecast.")
        if not isinstance(implied_vol, ImpliedVolSnapshot):
            raise TypeError("implied_vol must be an ImpliedVolSnapshot.")
        if forecast.as_of != context.as_of:
            raise ValueError("Forecast decision timestamp must match context.as_of.")
        if forecast.underlying != implied_vol.underlying:
            raise ValueError("Forecast and implied volatility must match underlying.")
        if forecast.horizon_trading_days != implied_vol.horizon_trading_days:
            raise ValueError("Forecast and implied volatility must match future horizon.")
        if implied_vol.known_at > context.as_of or implied_vol.observed_at > context.as_of:
            raise ValueError("Implied volatility was not available at the decision cutoff.")
        age = context.as_of.astimezone(timezone.utc) - implied_vol.observed_at.astimezone(timezone.utc)
        if age > self._config.max_iv_age:
            raise ValueError("Implied-volatility observation is stale.")
        if implied_vol.horizon_end is not None:
            local_day = context.as_of.astimezone(implied_vol.observed_at.tzinfo).date()
            if implied_vol.horizon_end <= local_day:
                raise ValueError("IV horizon must end after the decision session.")

        edge = implied_vol.annualized_vol - forecast.annualized_vol
        threshold = self._config.min_edge
        # Only arithmetic roundoff at the inclusive threshold is tolerated.
        rich = edge >= threshold or isclose(edge, threshold, rel_tol=1e-12, abs_tol=0.0)
        cheap = edge <= -threshold or isclose(edge, -threshold, rel_tol=1e-12, abs_tol=0.0)
        stressed = context.market_regime.stressed
        if rich and stressed >= self._config.stress_block_short_probability:
            direction = VolDirection.NEUTRAL
            policy = "Short-vol entry vetoed by total stress; no automatic long-vol override."
        elif rich:
            direction = VolDirection.SHORT_VOL
            policy = "Implied volatility exceeds forecast by the configured minimum edge."
        elif cheap:
            direction = VolDirection.LONG_VOL
            policy = "Implied volatility is below forecast by the configured minimum edge."
        else:
            direction = VolDirection.NEUTRAL
            policy = "Volatility gap is inside the neutral band."
        return VolSignal(
            underlying=forecast.underlying, as_of=context.as_of,
            horizon_trading_days=forecast.horizon_trading_days,
            direction=direction, edge=edge,
            reason=f"{policy} edge={edge:.6f}, min_edge={threshold:.6f}, stressed={stressed:.4f}.",
        )
