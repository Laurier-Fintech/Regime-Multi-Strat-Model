"""Inputs, outputs, and interface for Sleeve A's volatility signals.

All volatility values use annualized decimals.
The comparison and regime-adjustment logic will be implemented next.
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
from datetime import datetime
from enum import Enum
from math import isfinite

from Sleeves.base_sleeve import SleeveContext
from Sleeves.VolSleeve.rv_forecast import RVForecast


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


@dataclass(frozen=True, slots=True)
class VolSignalConfig:
    """Settings supplied when constructing the signal generator."""

    # Minimum volatility gap required by the baseline comparison.
    # Example units: 0.02 means two volatility percentage points.
    # The actual value must come from configuration.
    min_edge: float

    def __post_init__(self) -> None:
        if isinstance(self.min_edge, bool) or not isinstance(
            self.min_edge, (int, float)
        ):
            raise TypeError("min_edge must be a number.")

        if not isfinite(self.min_edge) or self.min_edge <= 0:
            raise ValueError("min_edge must be finite and positive.")


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
        """Produce a signal using information available at context.as_of.

        This method will validate the supplied records and their alignment.
        It will then calculate the volatility gap, apply configured thresholds,
        and incorporate the regime probabilities.
        """

        # Implementation steps:
        # 1. Validate input types, values, and timezone-aware timestamps.
        # 2. Match the underlying and future horizon across both measurements.
        # 3. Match the forecast's decision time to context.as_of.
        # 4. Check that the IV observation was known and sufficiently fresh.
        # 5. Calculate edge = implied_vol - forecast_vol.
        # 6. Apply the configured threshold and the agreed regime policy.
        # 7. Return a VolSignal with its direction, gap, and explanation.

        # Unfinished logic raises an explicit error.
        # Returning NEUTRAL here would incorrectly imply a completed decision.
        raise NotImplementedError(
            "Volatility comparison and regime adjustment "
            "have not been implemented."
        )