"""Inputs, outputs, and HAR-style realized-volatility forecasting.

Volatility values are annualized decimals: 0.20 means 20% per year.
The baseline predicts variance using daily-return volatility proxies.
"""

# Overall Question: Based on recent market movement, how much volatility do we expect over the next specified period?
# RVInputs: Holds the observed 1-, 5-, and 22-day volatility measurements; RVForecast: Holds predicted volatility, its market, decision time, and forecast horizon; RVForecaster: Defines the method that HAR and any later alternative must implement
# Predicted Variance = intercept + rv_1d^2(daily weight) + rv_5d^2(weekly weight) + rv_22d^2(monthly weight). model learns these weights from historical examples using NumPy’s least-squares solver. Each fitted model covers one underlying and one forecast horizon.
# HAR model is a small statistical model that forecasts future volatility using volatility measured over different past periods

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from math import isfinite

# Internal helper, hints describe the expected inouts the checks enforce those expectations, returns no value when validation succeeds
# Just validates stuff basically
def _validate_identity(underlying: str, as_of: datetime) -> None:
    """Check the market identifier and the decision timestamp."""
    if not isinstance(underlying, str) or not underlying.strip():
        raise ValueError("underlying must be a nonempty string.")

    if not isinstance(as_of, datetime):
        raise TypeError("as_of must be a datetime.")

    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must include a timezone.")


def _validate_volatility(name: str, value: float) -> None:
    """Reject missing, infinite, negative, or nonnumeric volatility."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number.")

    if not isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative.")


def _validate_horizon(horizon_trading_days: int) -> None:
    """The forecast must cover a positive whole number of trading days."""
    if isinstance(horizon_trading_days, bool) or not isinstance(
        horizon_trading_days, int
    ):
        raise TypeError("horizon_trading_days must be an integer.")

    if horizon_trading_days <= 0:
        raise ValueError("horizon_trading_days must be positive.")

# Prevents ordinary reassignment of the records field, gives instances a fixed set of declared attributes
@dataclass(frozen=True, slots=True)
class RVInputs:
    """Historical volatility inputs available at one decision time.

    The caller must obtain these through the as-of data reader.
    This record validates values; it cannot verify their data provenance.
    """

    # The decision timestamp anf information cutoff, use databases underlying identifiers
    underlying: str
    as_of: datetime

    # Observed volatility over the last 1, 5, and 22 trading days.
    # These match the existing rv_spy_* and rv_qqq_* feature definitions.
    rv_1d: float
    rv_5d: float
    rv_22d: float

    # Dataclass calls this automatically after assigning the fields, invalid record raises an error
    def __post_init__(self) -> None:
        _validate_identity(self.underlying, self.as_of)

        for name in ("rv_1d", "rv_5d", "rv_22d"):
            _validate_volatility(name, getattr(self, name))


@dataclass(frozen=True, slots=True)
class RVForecast:
    """Forecast volatility over a specified future trading-day horizon."""

    underlying: str
    as_of: datetime
    horizon_trading_days: int

    # Annualized units do not make this a one-year forecast.
    # For example, a five-day forecast can still be quoted as 0.20 annually.
    annualized_vol: float

    def __post_init__(self) -> None:
        _validate_identity(self.underlying, self.as_of)
        _validate_horizon(self.horizon_trading_days)
        _validate_volatility("annualized_vol", self.annualized_vol)


class RVForecaster(ABC):
    """Common interface for HAR and any later alternative forecasters."""

    @abstractmethod
    def forecast(
        self,
        inputs: RVInputs,
        *,
        horizon_trading_days: int,
    ) -> RVForecast:
        """Forecast using a model fitted only on data known by inputs.as_of."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class HARTrainingExample:
    """One historical input snapshot paired with its later observed outcome.

    realized_vol must cover exactly the next horizon_trading_days sessions.
    known_at is when that entire outcome became available.
    The caller is responsible for constructing these correctly from as-of data.
    """

    # Historical information available when the original decision was made.
    inputs: RVInputs

    # The future window whose volatility we subsequently observed.
    horizon_trading_days: int

    # Actual volatility over that future window, in annualized decimal units.
    realized_vol: float

    # When the complete future outcome became observable.
    # Until then, this example cannot be used for training.
    known_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.inputs, RVInputs):
            raise TypeError("inputs must be an RVInputs instance.")

        _validate_horizon(self.horizon_trading_days)
        _validate_volatility("realized_vol", self.realized_vol)
        _validate_identity(self.inputs.underlying, self.known_at)

        if self.known_at <= self.inputs.as_of:
            raise ValueError(
                "The future outcome must become known after its inputs."
            )


@dataclass(frozen=True, slots=True)
class _HARFit:
    """Internal record of one successful fit and its information cutoff."""

    underlying: str
    horizon_trading_days: int
    fitted_as_of: datetime

    # Order: intercept, daily weight, weekly weight, monthly weight.
    coefficients: tuple[float, ...]


class HARVolatilityForecaster(RVForecaster):
    """HAR-style variance regression using the repository's daily-return proxies."""

    def __init__(self, *, min_samples: int) -> None:
        # Four coefficients are fitted.
        # Five rows provide a basic numerical minimum, not adequate validation.
        # The actual minimum history is supplied by the caller.
        if isinstance(min_samples, bool) or not isinstance(min_samples, int):
            raise TypeError("min_samples must be an integer.")

        if min_samples < 5:
            raise ValueError("min_samples must be at least 5.")

        self._min_samples = min_samples

        # None means no model has been fitted successfully yet.
        self._fit: _HARFit | None = None

    @staticmethod
    def _design_row(inputs: RVInputs) -> tuple[float, ...]:
        """Convert one input snapshot into regression inputs."""

        # Squaring annualized volatility gives annualized variance.
        # The leading 1.0 allows the model to fit an intercept.
        return (
            1.0,
            inputs.rv_1d ** 2,
            inputs.rv_5d ** 2,
            inputs.rv_22d ** 2,
        )

    def fit(
        self,
        examples: list[HARTrainingExample],
        *,
        fitted_as_of: datetime,
    ) -> None:
        """Fit one market and horizon using outcomes known by fitted_as_of."""

        # Take a fixed snapshot of the supplied collection.
        examples = tuple(examples)

        if len(examples) < self._min_samples:
            raise ValueError(
                f"At least {self._min_samples} examples are required."
            )

        if any(not isinstance(row, HARTrainingExample) for row in examples):
            raise TypeError("Every example must be a HARTrainingExample.")

        # The first example establishes this model's market and horizon.
        underlying = examples[0].inputs.underlying
        horizon = examples[0].horizon_trading_days
        _validate_identity(underlying, fitted_as_of)

        seen = set()

        for row in examples:
            if row.inputs.underlying != underlying:
                raise ValueError("Fit each underlying separately.")

            if row.horizon_trading_days != horizon:
                raise ValueError("Fit each forecast horizon separately.")

            # Reject outcomes that were still unknown at the fitting cutoff.
            if row.known_at > fitted_as_of:
                raise ValueError(
                    "A training outcome was unknown at fitted_as_of."
                )

            # Repeating an example would accidentally give it extra weight.
            if row.inputs.as_of in seen:
                raise ValueError("Duplicate training input timestamp.")

            seen.add(row.inputs.as_of)

        # Import when fitting so the basic interface remains importable
        # even before the numerical dependency is available.
        import numpy as np

        # x contains one row of explanatory variables per training example.
        # y contains the subsequently observed annualized variance.
        x = np.asarray([self._design_row(row.inputs) for row in examples])
        y = np.asarray([row.realized_vol ** 2 for row in examples])

        if not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError("Training variances must be finite.")

        # Find the weights that minimize squared prediction errors.
        # rank describes how many independent columns the solver found.
        coefficients, _, rank, _ = np.linalg.lstsq(x, y, rcond=None)

        if rank < 4:
            raise ValueError("Training features lack independent variation.")

        if not np.isfinite(coefficients).all():
            raise ValueError("Fitted coefficients must be finite.")

        # Install the fitted model only after every check succeeds.
        # A failed refit leaves the previous successful fit intact.
        self._fit = _HARFit(
            underlying=underlying,
            horizon_trading_days=horizon,
            fitted_as_of=fitted_as_of,
            coefficients=tuple(float(value) for value in coefficients),
        )

    def forecast(
        self,
        inputs: RVInputs,
        *,
        horizon_trading_days: int,
    ) -> RVForecast:
        if not isinstance(inputs, RVInputs):
            raise TypeError("inputs must be an RVInputs instance.")

        _validate_horizon(horizon_trading_days)

        fitted = self._fit

        if fitted is None:
            raise RuntimeError("Fit the HAR model before forecasting.")

        if inputs.underlying != fitted.underlying:
            raise ValueError(
                "The model was fitted for a different underlying."
            )

        if horizon_trading_days != fitted.horizon_trading_days:
            raise ValueError(
                "The model was fitted for a different horizon."
            )

        # A historical decision cannot use a model fitted afterward.
        if inputs.as_of < fitted.fitted_as_of:
            raise ValueError(
                "The model was fitted after this decision time."
            )

        # Multiply each learned weight by its corresponding input and add.
        # strict=True requires both sequences to have the same length.
        variance = sum(
            weight * value
            for weight, value in zip(
                fitted.coefficients,
                self._design_row(inputs),
                strict=True,
            )
        )

        # Linear regression can extrapolate to a negative variance.
        # Reject that result explicitly.
        if not isfinite(variance) or variance < 0:
            raise ValueError(
                "The model produced an invalid variance forecast."
            )

        return RVForecast(
            underlying=inputs.underlying,
            as_of=inputs.as_of,
            horizon_trading_days=horizon_trading_days,
            annualized_vol=variance ** 0.5,
        )
