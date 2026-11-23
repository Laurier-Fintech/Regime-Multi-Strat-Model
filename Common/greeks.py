"""Option sensitivities before position quantities, multipliers or FX.

Vega and rho are per 1.0 change in annualized decimal volatility/rate.
Theta is per calendar year of elapsed time. Delta/gamma refer to spot for
BLACK_SCHOLES/CRR, and to the supplied futures price for BLACK_76.
"""

from dataclasses import dataclass, replace
from math import exp, pi, sqrt

from Common.option_pricing import (
    OptionInputs, OptionType, PricingModel, _binomial_tree, _black_terms,
    _finite_result, _normal_cdf, _real_number, _safe_exp, _validate_request,
    price_option,
)


@dataclass(frozen=True, slots=True)
class Greeks:
    """Long-option unit Greeks; multiply by signed quantity and multiplier."""

    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float
    model: PricingModel

    @property
    def vega_per_vol_point(self) -> float:
        """Approximate value change for +0.01 annualized decimal volatility."""
        return self.vega * 0.01

    @property
    def rho_per_rate_point(self) -> float:
        return self.rho * 0.01

    @property
    def theta_per_calendar_day(self) -> float:
        """Annual theta / 365; a local approximation, not a one-day reprice."""
        return self.theta / 365.0


def calculate_greeks(
    inputs: OptionInputs,
    *,
    model: PricingModel,
    tree_steps: int = 501,
    volatility_bump: float = 0.0001,
    rate_bump: float = 0.0001,
) -> Greeks:
    """Analytic European Greeks or CRR node/bump estimates for spot options.

    Tree delta/gamma/theta come from the first two levels, avoiding tiny spot
    bumps of a piecewise-linear lattice price. Vega and rho reprice the same
    grid with central bumps; the volatility bump is capped at sigma/2.
    Black-76 rho and theta hold the supplied futures price fixed.

    Greeks at expiry or zero volatility are deliberately rejected: payoff
    kinks and limiting sensitivities require a separate settlement policy.
    """
    _validate_request(inputs, model, tree_steps)
    if inputs.time_to_expiry <= 0 or inputs.volatility <= 0:
        raise ValueError("Greeks require positive time_to_expiry and volatility.")
    if model == PricingModel.CRR:
        dv = _real_number("volatility_bump", volatility_bump)
        dr = _real_number("rate_bump", rate_bump)
        if dv <= 0 or dr <= 0:
            raise ValueError("Greek bumps must be positive.")
        dv = min(dv, inputs.volatility / 2)
        if inputs.volatility + dv == inputs.volatility or inputs.risk_free_rate + dr == inputs.risk_free_rate:
            raise ValueError("Greek bumps are too small to change the inputs.")
        tree = _binomial_tree(inputs, tree_steps)

        def reprice(**changes: float) -> float:
            return price_option(replace(inputs, **changes), model=model, tree_steps=tree_steps)

        vega = (
            reprice(volatility=inputs.volatility + dv)
            - reprice(volatility=inputs.volatility - dv)
        ) / (2 * dv)
        rho = (
            reprice(risk_free_rate=inputs.risk_free_rate + dr)
            - reprice(risk_free_rate=inputs.risk_free_rate - dr)
        ) / (2 * dr)
        values = (tree.delta, tree.gamma, vega, tree.theta, rho)
    else:
        a, b, d1, d2 = _black_terms(inputs, model)
        s, t, sigma = inputs.underlying_price, inputs.time_to_expiry, inputs.volatility
        root_t = sqrt(t)
        density = exp(-0.5 * d1 * d1) / sqrt(2 * pi)
        sign = 1 if inputs.option_type == OptionType.CALL else -1
        n1, n2 = _normal_cdf(sign * d1), _normal_cdf(sign * d2)
        underlying_discount = _safe_exp(
            -t * (inputs.risk_free_rate if model == PricingModel.BLACK_76 else inputs.dividend_yield)
        )
        delta = sign * underlying_discount * n1
        gamma = underlying_discount * density / (s * sigma * root_t)
        vega = a * density * root_t
        diffusion_theta = -a * density * sigma / (2 * root_t)
        if model == PricingModel.BLACK_76:
            price = price_option(inputs, model=model)
            theta = diffusion_theta + inputs.risk_free_rate * price
            rho = -t * price
        else:
            theta = (
                diffusion_theta - sign * inputs.risk_free_rate * b * n2
                + sign * inputs.dividend_yield * a * n1
            )
            rho = sign * t * b * n2
        values = (delta, gamma, vega, theta, rho)
    return Greeks(*(_finite_result(value) for value in values), model=model)


def cash_delta_for_one_percent_move(
    delta: float,
    underlying_price: float,
    *,
    multiplier: float,
    fx_rate: float = 1.0,
) -> float:
    """First-order base-currency P&L for +1% in this delta's price variable.

    Result is per one LONG contract, matching DeltaSnapshot's cash-delta unit
    when the price variable is its risk factor. FX is base currency per one
    quote-currency unit. Supply the actual multiplier; no 100-share default.
    Cross-underlying/risk-factor hedge mappings must be applied by the adapter.
    """
    delta = _real_number("delta", delta)
    underlying_price = _real_number("underlying_price", underlying_price)
    multiplier = _real_number("multiplier", multiplier)
    fx_rate = _real_number("fx_rate", fx_rate)
    if underlying_price <= 0 or multiplier <= 0 or fx_rate <= 0:
        raise ValueError("underlying_price, multiplier and fx_rate must be positive.")
    return _finite_result(delta * underlying_price * 0.01 * multiplier * fx_rate)
