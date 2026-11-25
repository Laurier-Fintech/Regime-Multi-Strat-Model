import pandas as pd

from Data.DataBase.access import get_series
from Config.settings import load

# VIX circuit breaker. The regime takes DAYS to notice a crisis, this reacts the SAME day.
# On a VIX jump it moves the short-vol sleeves' weight into the reserve, holds, then rebuilds slowly.
# Runs right after the allocator, on its weights, so it works with sleeves on or off

LOOKBACK_DAYS = load("configs.yaml", "portfolio")["price_lookback_days"]


class VixBreaker:
    """A class because it remembers when it last fired (like the allocator remembers yesterday)"""

    def __init__(self):
        settings = load("risk.yaml", "vix_breaker")
        self.jump_pct = settings["jump_pct"]
        self.jump_min_level = settings["jump_min_level"]
        self.level = settings["level"]
        self.sleeves = settings["short_vol_sleeves"]
        self.cut_share = settings["cut_share"]
        self.hold_days = settings["hold_days"]
        self.rebuild_days = settings["rebuild_days"]
        self.days_since = None      # trading days since it last fired (None = never)

    def _vix_today(self, as_of):
        """Last 2 known VIX closes --> today's close and the jump from the day before"""
        start = pd.Timestamp(as_of) - pd.Timedelta(days=LOOKBACK_DAYS)
        vix = get_series("vix", start, as_of, as_of=as_of)["vix"].dropna()
        if len(vix) < 2:
            return None, None
        return vix.iloc[-1], vix.iloc[-1] / vix.iloc[-2] - 1

    def _share_cut_today(self):
        """How much of the short-vol weight to take away today"""
        if self.days_since is None:
            return 0.0
        if self.days_since <= self.hold_days:
            return self.cut_share                                 # fully cut
        rebuilt = (self.days_since - self.hold_days) / self.rebuild_days if self.rebuild_days > 0 else 1
        return max(0.0, self.cut_share * (1 - rebuilt))           # giving it back evenly --> 0

    def apply(self, weights, as_of):
        """Trims the allocator's weights if VIX jumped

        Keyword arguments:
        weights -- the allocator's weight per sleeve (sums to 1)
        Return: new weights (still sum to 1), list of risk events for trading.duckdb "risk_events"
        """
        if weights is None:
            return None, []

        vix, jump = self._vix_today(as_of)
        # fires on a big jump from an already-high level, or on a very high level
        big_jump = vix is not None and jump >= self.jump_pct and vix >= self.jump_min_level
        fired = big_jump or (vix is not None and vix >= self.level)

        if fired:
            self.days_since = 0           # a new jump restarts the clock
        elif self.days_since is not None:
            self.days_since += 1

        share = self._share_cut_today()
        weights = weights.copy()          # never change the allocator's own copy
        events = []
        vix_text = "no vix today" if vix is None else f"vix {vix:.1f} ({jump:+.0%})"
        for sleeve in self.sleeves:
            moved = weights[sleeve] * share
            if moved > 0:
                weights[sleeve] -= moved
                weights["reserve"] += moved
                events.append({"rule": "vix_circuit_breaker", "action": "cut", "sleeve": sleeve,
                               "detail": f"{vix_text}, moved {moved:.1%} to reserve"})
        return weights, events
