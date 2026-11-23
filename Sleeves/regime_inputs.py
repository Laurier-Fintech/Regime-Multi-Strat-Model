"""Validated four-state regime probabilities shared by strategy sleeves.

Labels match RegimeModel._combine(). Marginals are sums of joint states;
they describe model probabilities, without applying strategy thresholds.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from math import fsum, isclose, isfinite
from numbers import Real


REGIME_STATES = ("calm-bull", "calm-bear", "stressed-bull", "stressed-bear")
_FIELDS = ("calm_bull", "calm_bear", "stressed_bull", "stressed_bear")
_SUM_TOLERANCE = 1e-8


@dataclass(frozen=True, slots=True)
class RegimeProbabilities:
    """One immutable joint distribution and its calm/stress/direction totals.

    Every input must be a finite real number in [0, 1]. Total mass must be
    within 1e-8 of one. Only rounding error inside that tolerance is normalized.
    Missing states and materially incorrect totals are always rejected.
    """

    calm_bull: float
    calm_bear: float
    stressed_bull: float
    stressed_bear: float

    def __post_init__(self) -> None:
        values = []
        for state, field in zip(REGIME_STATES, _FIELDS):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError(f"Probability for {state} must be a real number.")
            if not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"Probability for {state} must be finite and in [0, 1].")
            values.append(float(value))

        total = fsum(values)
        if not isclose(total, 1.0, rel_tol=0.0, abs_tol=_SUM_TOLERANCE):
            raise ValueError("Regime probabilities must sum to 1 within 1e-8.")

        for field, value in zip(_FIELDS, values):
            object.__setattr__(self, field, value / total)

    @classmethod
    def from_mapping(cls, probabilities: Mapping[str, float] | None) -> "RegimeProbabilities":
        """Read exactly the model's four labels, including states with zero mass.

        Convert RegimeModel's pandas Series with .to_dict() at the engine
        boundary. None is its warm-up result and cannot represent a decision.
        """
        if probabilities is None:
            raise ValueError("Regime output is unavailable; the model may still be warming up.")
        if not isinstance(probabilities, Mapping):
            raise TypeError("Regime probabilities must be a mapping; convert Series with .to_dict().")

        supplied = dict(probabilities)
        missing = [state for state in REGIME_STATES if state not in supplied]
        unexpected = [state for state in supplied if state not in REGIME_STATES]
        if missing or unexpected:
            raise ValueError(
                f"Expected exactly {REGIME_STATES}; missing={missing!r}, unexpected={unexpected!r}."
            )
        return cls(*(supplied[state] for state in REGIME_STATES))

    def as_mapping(self) -> dict[str, float]:
        """Return an independent copy using the model's canonical labels."""
        return {state: getattr(self, field) for state, field in zip(REGIME_STATES, _FIELDS)}

    @property
    def calm(self) -> float:
        return fsum((self.calm_bull, self.calm_bear))

    @property
    def stressed(self) -> float:
        return fsum((self.stressed_bull, self.stressed_bear))

    @property
    def bull(self) -> float:
        return fsum((self.calm_bull, self.stressed_bull))

    @property
    def bear(self) -> float:
        return fsum((self.calm_bear, self.stressed_bear))
