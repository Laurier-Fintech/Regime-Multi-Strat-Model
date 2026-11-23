"""Read-only daily adapters over Data.DataBase.access, with explicit provenance.

No downloads, SQL, fitted models or synthetic contracts live here. The session
schedule, daily availability convention and any underlying proxies are inputs.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from math import ceil, isclose, isfinite, sqrt
from numbers import Real
from typing import Protocol

import pandas as pd

from Common.calendar import SessionCalendar
from Sleeves.VolSleeve.rv_forecast import RVInputs, _validate_horizon, _validate_identity
from Sleeves.VolSleeve.signal import ImpliedVolSnapshot


def _identifier(value: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip().lower():
        raise ValueError("Database identifiers must be nonempty canonical lowercase strings.")


def _number(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
        raise ValueError(f"{name} must be a finite real number.")
    return float(value)


@dataclass(frozen=True, slots=True)
class VolMarketSpec:
    """Logical strategy market and its explicit RV/IV database identities.

    A proxy acknowledgement is required whenever either source differs from
    the logical market. This records an assumption, not economic equivalence.
    """

    underlying: str
    rv_underlying: str
    iv_underlying: str
    proxy_reason: str | None = None

    def __post_init__(self) -> None:
        for value in (self.underlying, self.rv_underlying, self.iv_underlying):
            _identifier(value)
        uses_proxy = self.rv_underlying != self.underlying or self.iv_underlying != self.underlying
        if self.proxy_reason is not None and (not isinstance(self.proxy_reason, str) or not self.proxy_reason.strip()):
            raise ValueError("proxy_reason must be a nonempty explanation.")
        if uses_proxy and self.proxy_reason is None:
            raise ValueError("A different RV/IV underlying requires an explicit proxy_reason.")


@dataclass(frozen=True, slots=True)
class VolDataConfig:
    """Daily DATE-to-timestamp policy and source/freshness selection.

    available_time is a naive wall-clock time in market_timezone at which a
    database known_at date is assumed usable. This is a daily convention,
    not intraday vendor evidence. Decisions before that time are rejected.
    """

    markets: tuple[VolMarketSpec, ...]
    market_timezone: tzinfo
    available_time: time
    max_observation_age: timedelta
    iv_source: str
    option_quote_source: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.markets, tuple) or not self.markets:
            raise ValueError("markets must be a nonempty tuple.")
        if any(not isinstance(market, VolMarketSpec) for market in self.markets):
            raise TypeError("markets must contain VolMarketSpec records.")
        if len({market.underlying for market in self.markets}) != len(self.markets):
            raise ValueError("Logical market identities must be unique.")
        if not isinstance(self.market_timezone, tzinfo):
            raise TypeError("market_timezone must be an explicit tzinfo.")
        if not isinstance(self.available_time, time) or self.available_time.tzinfo is not None:
            raise ValueError("available_time must be a naive local wall-clock time.")
        if not isinstance(self.max_observation_age, timedelta) or self.max_observation_age < timedelta(0):
            raise ValueError("max_observation_age must be a nonnegative timedelta.")
        _identifier(self.iv_source)
        if self.option_quote_source is not None:
            _identifier(self.option_quote_source)


class VolDataReader(Protocol):
    """Subset of the public access.py API; injectable for isolated tests."""

    def get_features(self, feature_ids, start, end=None, *, as_of, include_metadata=False): ...
    def get_option_iv(self, underlyings, start, end=None, *, as_of, **filters): ...
    def get_option_chain(self, underlying, *, as_of, **filters): ...


class DatabaseVolMarketData:
    """Concrete VolMarketData implementation using only the public data reader."""

    def __init__(
        self, config: VolDataConfig, *, calendar: SessionCalendar,
        reader: VolDataReader | None = None,
    ) -> None:
        if not isinstance(config, VolDataConfig) or not isinstance(calendar, SessionCalendar):
            raise TypeError("Supply VolDataConfig and an explicit SessionCalendar.")
        self._config = config
        self._calendar = calendar
        self._markets = {market.underlying: market for market in config.markets}
        self._reader = reader

    def _api(self) -> VolDataReader:
        if self._reader is None:
            # Lazy import: importing the sleeve interfaces does not open a DB.
            from Data.DataBase import access
            self._reader = access
        return self._reader

    def _decision(self, underlying: str, as_of: datetime) -> tuple[VolMarketSpec, date, date]:
        _validate_identity(underlying, as_of)
        market = self._markets[underlying]
        local = as_of.astimezone(self._config.market_timezone)
        if local.time() < self._config.available_time:
            raise ValueError("Daily data cannot be used before its configured availability time.")
        day = local.date()
        if not self._calendar.is_session(day):
            raise ValueError("Decision date must be a supplied exchange session.")
        lookback = ceil(self._config.max_observation_age.total_seconds() / 86400) + 1
        return market, day, day - timedelta(days=lookback)

    def _stamp(self, day: date) -> datetime:
        return datetime.combine(day, self._config.available_time, tzinfo=self._config.market_timezone)

    @staticmethod
    def _day(value, name: str) -> date:
        if not isinstance(value, date) or pd.isna(value):
            raise ValueError(f"{name} must contain database DATE values.")
        if isinstance(value, datetime):
            if value.tzinfo is not None or value.time() != time.min:
                raise ValueError(f"{name} must be a DATE, not an intraday timestamp.")
            return value.date()
        return value

    def _rows(self, frame: pd.DataFrame, columns: set[str], start: date, day: date) -> pd.DataFrame:
        if not isinstance(frame, pd.DataFrame) or not frame.columns.is_unique or not columns.issubset(frame.columns):
            raise ValueError("Data reader must return the required columns, including actual known_at metadata.")
        if frame.empty:
            raise LookupError("No market observations are available at this cutoff.")
        rows = frame.copy(deep=True)
        for name in ("obs_date", "known_at"):
            rows[name] = [self._day(value, name) for value in rows[name]]
        for observed, known in zip(rows.obs_date, rows.known_at):
            if not start <= observed <= day or not observed <= known <= day:
                raise ValueError("Reader returned observations outside the requested as-of window.")
            if not self._calendar.is_session(observed):
                raise ValueError("Observation date is not in the supplied exchange calendar.")
        return rows

    def _fresh(self, observed: date, as_of: datetime) -> None:
        age = as_of.astimezone(timezone.utc) - self._stamp(observed).astimezone(timezone.utc)
        if age > self._config.max_observation_age:
            raise ValueError("Market observation is stale under the configured age limit.")

    def get_rv_inputs(self, underlying: str, *, as_of: datetime) -> RVInputs:
        market, day, start = self._decision(underlying, as_of)
        ids = [f"rv_{market.rv_underlying}_{window}d" for window in (1, 5, 22)]
        rows = self._rows(
            self._api().get_features(ids, start, day, as_of=day, include_metadata=True),
            {"feature_id", "obs_date", "value", "known_at"}, start, day,
        )
        if not set(rows.feature_id).issubset(ids):
            raise ValueError("Reader returned unexpected RV feature identities.")
        observed = max(rows.obs_date)
        selected = rows[rows.obs_date == observed]
        if len(selected) != 3 or set(selected.feature_id) != set(ids):
            raise ValueError("Latest RV observation must contain all three features exactly once.")
        self._fresh(observed, as_of)
        values = selected.set_index("feature_id").value
        return RVInputs(
            underlying, as_of, *(_number(values[feature], feature) for feature in ids),
            source_underlying=market.rv_underlying,
            observed_at=self._stamp(observed), known_at=self._stamp(max(selected.known_at)),
        )

    def get_implied_vol(
        self, underlying: str, *, as_of: datetime, horizon_trading_days: int,
    ) -> ImpliedVolSnapshot:
        _validate_horizon(horizon_trading_days)
        market, day, start = self._decision(underlying, as_of)
        end = self._calendar.next_sessions(day, horizon_trading_days)[-1]
        rows = self._rows(
            self._api().get_option_iv(
                [market.iv_underlying], start, day, as_of=day,
                moneyness_type="pct_spot", source=self._config.iv_source,
                include_metadata=True,
            ),
            {"underlying", "obs_date", "known_at", "source", "moneyness_type", "moneyness", "tenor_days", "iv"},
            start, day,
        )
        if not (rows.underlying == market.iv_underlying).all() or not (rows.source == self._config.iv_source).all():
            raise ValueError("IV reader returned an unexpected underlying or source.")
        if not (rows.moneyness_type == "pct_spot").all():
            raise ValueError("IV reader must use percent-of-spot moneyness.")
        observed = max(rows.obs_date)
        latest = rows[rows.obs_date == observed]
        atm = latest[[isclose(_number(value, "moneyness"), 100.0, abs_tol=1e-8, rel_tol=0) for value in latest.moneyness]]
        if atm.empty:
            raise LookupError("Latest IV observation has no ATM percent-of-spot quotes.")
        self._fresh(observed, as_of)
        curve: dict[int, float] = {}
        for row in atm.itertuples(index=False):
            tenor = _number(row.tenor_days, "tenor_days")
            vol = _number(row.iv, "iv")
            if tenor <= 0 or tenor % 1 or vol < 0:
                raise ValueError("IV tenors must be positive integers and volatility nonnegative.")
            tenor = int(tenor)
            if tenor in curve:
                raise ValueError("Duplicate ATM IV tenor at the selected observation.")
            variance = vol * vol * tenor
            if not isfinite(variance):
                raise ValueError("IV total variance exceeds numerical range.")
            curve[tenor] = variance
        tenors = sorted(curve)
        variances = [curve[tenor] for tenor in tenors]
        if any(right < left for left, right in zip(variances, variances[1:])):
            raise ValueError("ATM total variance decreases with tenor; reject this IV curve.")
        start_days, end_days = (day - observed).days, (end - observed).days
        if end_days < tenors[0] or end_days > tenors[-1]:
            raise ValueError("Forecast horizon end is not bracketed by available IV tenors; no extrapolation.")
        nodes, totals = [0] + tenors, [0.0] + variances
        used: set[int] = set()

        def total_variance(days: int) -> float:
            index = bisect_left(nodes, days)
            if nodes[index] == days:
                if days:
                    used.add(days)
                return totals[index]
            low, high = nodes[index - 1], nodes[index]
            used.update(value for value in (low, high) if value)
            weight = (days - low) / (high - low)
            return totals[index - 1] * (1 - weight) + totals[index] * weight

        # Difference the same observation's variance curve to cover the future
        # decision-to-end window, even when the observation is a few days old.
        forward_variance = (total_variance(end_days) - total_variance(start_days)) / (end_days - start_days)
        if not isfinite(forward_variance) or forward_variance < 0:
            raise ValueError("Invalid horizon-aligned implied variance.")
        return ImpliedVolSnapshot(
            underlying, self._stamp(observed), self._stamp(max(atm.known_at)),
            horizon_trading_days, sqrt(forward_variance),
            source_underlying=market.iv_underlying, source=self._config.iv_source,
            horizon_end=end, tenor_days_used=tuple(sorted(used)),
        )

    def get_option_chain(self, underlying: str, *, as_of: datetime) -> pd.DataFrame:
        """Read actual contract quotes; IV grids never manufacture a chain."""
        _, day, _ = self._decision(underlying, as_of)
        rows = self._rows(
            self._api().get_option_chain(
                underlying, as_of=day, obs_date=day,
                source=self._config.option_quote_source, include_metadata=True,
            ),
            {"underlying", "obs_date", "known_at", "source", "expiry", "strike", "call_put", "bid", "ask"},
            day, day,
        )
        invalid_source = any(not isinstance(value, str) or not value.strip() for value in rows.source)
        if not (rows.underlying == underlying).all() or invalid_source or rows.source.nunique() != 1:
            raise ValueError("Option chains must match the actual underlying and one configured/unique source.")
        if self._config.option_quote_source is not None and not (rows.source == self._config.option_quote_source).all():
            raise ValueError("Option chain source does not match configuration.")
        rows["expiry"] = [self._day(value, "expiry") for value in rows.expiry]
        if rows.duplicated(["expiry", "strike", "call_put"]).any():
            raise ValueError("Duplicate exact option contracts in the chain.")
        for row in rows.itertuples(index=False):
            bid, ask, strike = (_number(getattr(row, name), name) for name in ("bid", "ask", "strike"))
            if bid < 0 or ask < bid or strike <= 0 or row.call_put not in ("C", "P") or row.expiry < day:
                raise ValueError("Option chain contains invalid contract terms or crossed/negative quotes.")
        return rows
