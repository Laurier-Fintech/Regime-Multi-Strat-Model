"""Explicit exchange-session dates supplied by the caller, never price history.

This module does not infer holidays. Supply a complete, independently known
exchange schedule spanning the historical inputs and future option horizons.
"""

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class SessionCalendar:
    """Immutable sorted session dates, including any exchange holidays/closures."""

    session_dates: tuple[date, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.session_dates, tuple) or not self.session_dates:
            raise ValueError("session_dates must be a nonempty tuple.")
        if any(not isinstance(day, date) or isinstance(day, datetime) for day in self.session_dates):
            raise TypeError("Session dates must be date objects, without times.")
        if tuple(sorted(set(self.session_dates))) != self.session_dates:
            raise ValueError("Session dates must be sorted and unique.")

    def is_session(self, day: date) -> bool:
        index = bisect_left(self.session_dates, day)
        return index < len(self.session_dates) and self.session_dates[index] == day

    def next_sessions(self, after: date, count: int) -> tuple[date, ...]:
        """The next count sessions, excluding the decision session itself."""
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise ValueError("Session count must be a positive integer.")
        if not self.is_session(after):
            raise ValueError("Decision date must be a session in the supplied calendar.")
        index = bisect_left(self.session_dates, after) + 1
        selected = self.session_dates[index:index + count]
        if len(selected) != count:
            raise ValueError("Session calendar does not cover the requested future horizon.")
        return selected
