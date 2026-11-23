"""Shared, read-only inputs and checks for executable sleeve proposals.

Funding reserves are gross, additive base-currency amounts, not maximum loss.
Adapters must include fees, margin buffers and funding for either position sign.
No margin offsets, FX conversions or contract IDs are guessed here.
"""
from dataclasses import dataclass, replace
from datetime import date, datetime, tzinfo
from math import floor, fsum, isfinite
from numbers import Real
from typing import Callable

from Sleeves.base_sleeve import SleeveContext, TargetPosition


def positive(name, value, *, zero=False):
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
        raise ValueError(f"{name} must be finite and numeric.")
    if value < 0 or (not zero and value == 0):
        raise ValueError(f"{name} must be {'nonnegative' if zero else 'positive'}.")


def text(name, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonempty text.")


@dataclass(frozen=True, slots=True)
class SelectionPolicy:
    base_currency: str
    market_timezone: tzinfo
    max_relative_spread: float
    fee_per_contract: float
    max_contracts: int

    def __post_init__(self):
        text('base_currency', self.base_currency)
        if not isinstance(self.market_timezone, tzinfo):
            raise TypeError('market_timezone must be a timezone.')
        positive('max_relative_spread', self.max_relative_spread)
        positive('fee_per_contract', self.fee_per_contract, zero=True)
        if isinstance(self.max_contracts, bool) or not isinstance(self.max_contracts, int) or self.max_contracts <= 0:
            raise ValueError('max_contracts must be a positive integer.')


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    underlying: str
    as_of: datetime
    currency: str
    spot: float

    def __post_init__(self):
        text('underlying', self.underlying)
        text('currency', self.currency)
        if not isinstance(self.as_of, datetime) or self.as_of.utcoffset() is None:
            raise ValueError('Market snapshot needs an aware timestamp.')
        positive('spot', self.spot)


@dataclass(frozen=True, slots=True)
class CapitalSnapshot:
    instrument_id: str
    as_of: datetime
    currency: str
    long_requirement: float
    short_requirement: float
    policy_source: str

    def __post_init__(self):
        for name in ('instrument_id', 'currency', 'policy_source'):
            text(name, getattr(self, name))
        if not isinstance(self.as_of, datetime) or self.as_of.utcoffset() is None:
            raise ValueError('Capital snapshot needs an aware timestamp.')
        positive('long_requirement', self.long_requirement)
        positive('short_requirement', self.short_requirement)


MarketLookup = Callable[[str, datetime], MarketSnapshot]
CapitalLookup = Callable[[str, datetime], CapitalSnapshot]


class CapitalModel:
    """Gross reserves deliberately ignore offsets between related legs."""
    def __init__(self, base_currency: str, lookup: CapitalLookup):
        text('base_currency', base_currency)
        if not callable(lookup):
            raise TypeError('Capital lookup must be callable.')
        self.base_currency, self.lookup = base_currency, lookup

    def unit(self, instrument_id, quantity, as_of):
        row = self.lookup(instrument_id, as_of)
        if not isinstance(row, CapitalSnapshot) or row.instrument_id != instrument_id or row.as_of != as_of:
            raise ValueError('Capital lookup must return the exact instrument and decision timestamp.')
        if row.currency != self.base_currency:
            raise ValueError('Capital reserve currency must match the base currency.')
        return row.long_requirement if quantity > 0 else row.short_requirement

    def required(self, targets, as_of):
        amount = fsum(abs(t.target_quantity) * self.unit(t.instrument_id, t.target_quantity, as_of)
                      for t in targets if t.target_quantity)
        if not isfinite(amount):
            raise ValueError('Capital requirement overflow.')
        return amount

    def check(self, context, targets):
        if self.required(targets, context.as_of) > context.capital_budget:
            raise ValueError('Desired book exceeds its capital budget; rebudget or unwind before new entries.')


def scaled(targets, quantity):
    return [replace(t, target_quantity=t.target_quantity * quantity) for t in targets if t.target_quantity * quantity]


def sized(context, lot, capital, max_contracts, *, unit_floor=0.0):
    unit = max(capital.required(lot, context.as_of), unit_floor)
    positive('one-lot capital', unit)
    count = min(max_contracts, floor(context.capital_budget / unit))
    # Multiplication can round above the boundary even after floor division.
    while count and count * unit > context.capital_budget:
        count -= 1
    return scaled(lot, count)


def combine(targets, sleeve_id):
    """Keep attribution slices; never silently net opposing strategies."""
    amounts, signs = {}, {}
    for t in targets:
        if not isinstance(t, TargetPosition) or t.sleeve_id != sleeve_id:
            raise ValueError('Invalid target or wrong sleeve ID.')
        if not t.target_quantity:
            continue
        sign = 1 if t.target_quantity > 0 else -1
        if t.instrument_id in signs and signs[t.instrument_id] != sign:
            raise ValueError('Opposing attribution slices require explicit Portfolio reconciliation.')
        signs[t.instrument_id] = sign
        key = (t.instrument_id, t.group_id)
        amounts[key] = amounts.get(key, 0) + t.target_quantity
    return [TargetPosition(sleeve_id, i, q, g) for (i, g), q in sorted(
        amounts.items(), key=lambda item: (item[0][0], item[0][1] or '')) if q]


def market_at(lookup, underlying, context, policy):
    row = lookup(underlying, context.as_of)
    if not isinstance(row, MarketSnapshot) or row.underlying != underlying or row.as_of != context.as_of:
        raise ValueError('Market lookup must match the exact underlying and decision timestamp.')
    if row.currency != policy.base_currency:
        raise ValueError('Market and base currency must match; FX is not inferred.')
    return row


def chain_rows(chain, underlying, context, policy, min_dte, max_dte, *, expiry=None):
    """Daily same-session quotes only; adapters enforce their release cutoff.

    Spread is a quote-quality filter, not proof of executable size/liquidity.
    Model-priced sources must retain their source tag through resolution.
    """
    import pandas as pd
    if not isinstance(chain, pd.DataFrame):
        raise TypeError('Option chain must be a DataFrame.')
    required = {'underlying', 'obs_date', 'known_at', 'source', 'contract_id',
                'expiry', 'strike', 'call_put', 'bid', 'ask'}
    if not required <= set(chain.columns):
        raise ValueError(f'Chain lacks required metadata: {sorted(required - set(chain.columns))}')
    if chain.empty:
        raise LookupError('No option chain available.')
    day = context.as_of.astimezone(policy.market_timezone).date()
    rows, seen, ids, sources = [], set(), set(), set()
    for row in chain.to_dict('records'):
        if row['underlying'] != underlying:
            raise ValueError('Chain contains a different underlying.')
        for field in ('obs_date', 'known_at', 'expiry'):
            if type(row[field]) is not date:
                raise ValueError(f'{field} must be a date (daily quote convention).')
        if row['obs_date'] != day or not row['obs_date'] <= row['known_at'] <= day:
            raise ValueError('Chain must be observed and known on the decision session.')
        for field in ('source', 'contract_id'):
            text(field, row[field])
        sources.add(row['source'])
        key = (row['expiry'], row['strike'], row['call_put'])
        if key in seen or row['contract_id'] in ids:
            raise ValueError('Duplicate/ambiguous option contract.')
        seen.add(key); ids.add(row['contract_id'])
        positive('strike', row['strike'])
        positive('bid', row['bid'], zero=True); positive('ask', row['ask'])
        if row['call_put'] not in ('C', 'P') or row['bid'] > row['ask']:
            raise ValueError('Invalid option type or crossed quotes.')
        dte = (row['expiry'] - day).days
        relative_spread = (row['ask'] - row['bid']) / ((row['ask'] + row['bid']) / 2)
        if min_dte <= dte <= max_dte and relative_spread <= policy.max_relative_spread:
            if expiry is None or row['expiry'] == expiry:
                rows.append(row)
    if len(sources) != 1:
        raise ValueError('Mixed quote sources are not supported.')
    if not rows:
        raise LookupError('No quotes meet expiry and spread policy.')
    return sorted(rows, key=lambda r: (r['expiry'], r['strike'], r['call_put']))


def resolved(lookup, row, policy):
    contract = lookup(row)
    for name in ('instrument_id', 'series_id', 'currency'):
        text(name, getattr(contract, name, None))
    for name in ('underlying', 'expiry', 'strike', 'call_put'):
        if getattr(contract, name, None) != row[name]:
            raise ValueError(f'Canonical contract does not match quoted {name}.')
    positive('multiplier', contract.multiplier)
    if contract.currency != policy.base_currency:
        raise ValueError('Contract currency does not match base currency.')
    return contract


def compatible(a, b):
    if a.instrument_id == b.instrument_id or any(getattr(a, field) != getattr(b, field)
            for field in ('underlying', 'expiry', 'multiplier', 'currency', 'series_id')):
        raise ValueError('Option legs must have distinct IDs and compatible settlement/series terms.')


def require_option_funding(capital, contract, row, side, context, policy):
    reserve = capital.unit(contract.instrument_id, side, context.as_of)
    minimum = (row['ask'] * contract.multiplier if side > 0 else 0) + policy.fee_per_contract
    if reserve < minimum:
        raise ValueError('Capital reserve is below quoted premium plus configured costs.')
    return reserve
