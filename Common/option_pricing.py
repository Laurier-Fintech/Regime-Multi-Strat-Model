"""Vanilla option prices per underlying unit, before contract multipliers.

Spot models use a continuous dividend yield. Black-76 uses a supplied futures
price and supports European exercise only. All results are model estimates;
callers must label reconstructed quotes as model-priced.
"""

from dataclasses import dataclass
from enum import Enum
from math import erfc, exp, expm1, isfinite, log, sqrt
from numbers import Real


class OptionType(str, Enum):
    CALL = "C"
    PUT = "P"


class ExerciseStyle(str, Enum):
    EUROPEAN = "european"
    AMERICAN = "american"


class PricingModel(str, Enum):
    BLACK_SCHOLES = "black_scholes"
    BLACK_76 = "black_76"
    CRR = "crr"


@dataclass(frozen=True, slots=True)
class OptionInputs:
    """Inputs for one plain call or put, supplied at a common information cutoff.

    underlying_price is spot for BLACK_SCHOLES/CRR and futures for BLACK_76.
    time_to_expiry is a calendar-year fraction, not a trading-day count.
    Volatility and continuously compounded annual rates use decimals.
    Exercise style is required; it must come from the contract specification.
    """

    option_type: OptionType
    exercise_style: ExerciseStyle
    underlying_price: float
    strike: float
    time_to_expiry: float
    volatility: float
    risk_free_rate: float
    dividend_yield: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.option_type, OptionType):
            raise TypeError("option_type must be an OptionType.")
        if not isinstance(self.exercise_style, ExerciseStyle):
            raise TypeError("exercise_style must be an ExerciseStyle.")
        for name in (
            "underlying_price", "strike", "time_to_expiry", "volatility",
            "risk_free_rate", "dividend_yield",
        ):
            value = _real_number(name, getattr(self, name))
            if name in ("underlying_price", "strike") and value <= 0:
                raise ValueError(f"{name} must be positive for a lognormal model.")
            if name in ("time_to_expiry", "volatility") and value < 0:
                raise ValueError(f"{name} must be nonnegative.")
            object.__setattr__(self, name, value)


def _real_number(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number.")
    try:
        value = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} exceeds floating-point range.") from exc
    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")
    return value


def _finite_result(value: float) -> float:
    if not isfinite(value):
        raise ValueError("Pricing calculation exceeded floating-point range.")
    return value


def _safe_exp(value: float) -> float:
    try:
        result = exp(value)
    except OverflowError as exc:
        raise ValueError("Pricing exponent exceeded floating-point range.") from exc
    if result == 0.0:
        raise ValueError("Pricing exponent underflowed; these inputs are unsupported.")
    return _finite_result(result)


def _normal_cdf(value: float) -> float:
    # erfc preserves small lower-tail probabilities better than 1 + erf.
    return 0.5 * erfc(-value / sqrt(2.0))


def _validate_request(inputs: OptionInputs, model: PricingModel, tree_steps: int) -> None:
    if not isinstance(inputs, OptionInputs):
        raise TypeError("inputs must be OptionInputs.")
    if not isinstance(model, PricingModel):
        raise TypeError("model must be a PricingModel.")
    if model != PricingModel.CRR and inputs.exercise_style != ExerciseStyle.EUROPEAN:
        raise ValueError("American exercise requires the CRR spot model.")
    if model == PricingModel.BLACK_76 and inputs.dividend_yield != 0.0:
        raise ValueError("Black-76 requires dividend_yield=0; carry is already in the futures price.")
    if model == PricingModel.CRR:
        if isinstance(tree_steps, bool) or not isinstance(tree_steps, int):
            raise TypeError("tree_steps must be an integer.")
        if tree_steps < 2:
            raise ValueError("tree_steps must be at least 2.")


def _black_terms(inputs: OptionInputs, model: PricingModel) -> tuple[float, float, float, float]:
    """Return discounted underlying, discounted strike, d1 and d2."""
    s, k, t, sigma = (
        inputs.underlying_price, inputs.strike, inputs.time_to_expiry, inputs.volatility
    )
    discount = _safe_exp(-inputs.risk_free_rate * t)
    carry = inputs.risk_free_rate - inputs.dividend_yield
    if model == PricingModel.BLACK_76:
        a = s * discount
        carry = 0.0
    else:
        a = s * _safe_exp(-inputs.dividend_yield * t)
    b = k * discount
    std_dev = sigma * sqrt(t)
    if std_dev == 0.0:
        raise ValueError("Positive time and volatility are required for Black terms.")
    d1 = (log(s) - log(k) + carry * t) / std_dev + 0.5 * std_dev
    return _finite_result(a), _finite_result(b), _finite_result(d1), _finite_result(d1 - std_dev)


def _black_price(inputs: OptionInputs, model: PricingModel) -> float:
    a, b, d1, d2 = _black_terms(inputs, model)
    # Compute the out-of-the-money side first and use parity for the other
    # side. This avoids subtracting two large almost equal ITM terms.
    if a <= b:
        call = max(0.0, _finite_result(a * _normal_cdf(d1) - b * _normal_cdf(d2)))
        put = call + b - a
    else:
        put = max(0.0, _finite_result(b * _normal_cdf(-d2) - a * _normal_cdf(-d1)))
        call = put + a - b
    return call if inputs.option_type == OptionType.CALL else put


def _payoff(inputs: OptionInputs, underlying: float) -> float:
    sign = 1 if inputs.option_type == OptionType.CALL else -1
    return max(sign * (underlying - inputs.strike), 0.0)


def _deterministic_price(inputs: OptionInputs, model: PricingModel, steps: int) -> float:
    """Zero-volatility limit, including exercise on the American tree grid."""
    s, k, t, r, q = (
        inputs.underlying_price, inputs.strike, inputs.time_to_expiry,
        inputs.risk_free_rate, inputs.dividend_yield,
    )
    if model == PricingModel.BLACK_76:
        return _safe_exp(-r * t) * _payoff(inputs, s)
    sign = 1 if inputs.option_type == OptionType.CALL else -1
    if inputs.exercise_style == ExerciseStyle.AMERICAN:
        times = (t * i / steps for i in range(steps + 1))
    else:
        times = (t,)
    return max(
        max(sign * (s * _safe_exp(-q * tau) - k * _safe_exp(-r * tau)), 0.0)
        for tau in times
    )


@dataclass(frozen=True, slots=True)
class _TreeResult:
    price: float
    delta: float
    gamma: float
    theta: float


def _binomial_tree(inputs: OptionInputs, steps: int) -> _TreeResult:
    """CRR spot lattice; retain the first two levels for stable tree Greeks.

    p = (exp((r-q)*dt)-d)/(u-d), u=exp(sigma*sqrt(dt)), d=1/u.
    American nodes choose the larger of continuation and exercise value.
    """
    s, t, sigma = inputs.underlying_price, inputs.time_to_expiry, inputs.volatility
    dt = t / steps
    dx = sigma * sqrt(dt)
    try:
        # Multiplying numerator and denominator by u gives this stable form.
        p = expm1((inputs.risk_free_rate - inputs.dividend_yield) * dt + dx) / expm1(2 * dx)
    except (OverflowError, ZeroDivisionError) as exc:
        raise ValueError("CRR step is outside numerical range; revise inputs or tree_steps.") from exc
    if not isfinite(p) or not 0 <= p <= 1:
        raise ValueError("CRR risk-neutral probability is outside [0, 1]; increase tree_steps.")
    discount = _safe_exp(-inputs.risk_free_rate * dt)
    log_s = log(s)
    values = [_payoff(inputs, _safe_exp(log_s + (2 * j - steps) * dx)) for j in range(steps + 1)]
    first = second = None
    if steps == 2:
        second = tuple(values)
    american = inputs.exercise_style == ExerciseStyle.AMERICAN
    for level in range(steps - 1, -1, -1):
        for j in range(level + 1):
            continuation = discount * ((1 - p) * values[j] + p * values[j + 1])
            if american:
                node_spot = _safe_exp(log_s + (2 * j - level) * dx)
                values[j] = max(continuation, _payoff(inputs, node_spot))
            else:
                values[j] = continuation
        if level == 2:
            second = tuple(values[:3])
        elif level == 1:
            first = tuple(values[:2])
    down, up = s * _safe_exp(-dx), s * _safe_exp(dx)
    down2, up2 = s * _safe_exp(-2 * dx), s * _safe_exp(2 * dx)
    if down == up or down2 == s or up2 == s:
        raise ValueError("CRR node spacing is too small to compute sensitivities.")
    delta = (first[1] - first[0]) / (up - down)
    delta_down = (second[1] - second[0]) / (s - down2)
    delta_up = (second[2] - second[1]) / (up2 - s)
    gamma = (delta_up - delta_down) / ((up2 - down2) / 2)
    theta = (second[1] - values[0]) / (2 * dt)
    return _TreeResult(*(_finite_result(v) for v in (values[0], delta, gamma, theta)))


def price_option(inputs: OptionInputs, *, model: PricingModel, tree_steps: int = 501) -> float:
    """Return a long option's model price per underlying unit.

    Multiply by the contract multiplier for one contract's currency value.
    BLACK_SCHOLES and BLACK_76 require European exercise. CRR supports either
    exercise style for spot underlyings. Its grid size affects convergence.
    Expiry returns intrinsic value; zero volatility uses a deterministic limit.
    Invalid model/exercise combinations raise even at these boundaries.
    """
    _validate_request(inputs, model, tree_steps)
    if inputs.time_to_expiry == 0:
        value = _payoff(inputs, inputs.underlying_price)
    elif inputs.volatility == 0:
        value = _deterministic_price(inputs, model, tree_steps)
    elif model == PricingModel.CRR:
        value = _binomial_tree(inputs, tree_steps).price
    else:
        value = _black_price(inputs, model)
    return _finite_result(value)
