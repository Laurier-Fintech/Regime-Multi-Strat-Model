# VIX circuit breaker. The regime takes DAYS to notice a crisis, this reacts the SAME day.
# On a VIX jump it moves the short-vol sleeves' weight into the reserve, holds, then rebuilds slowly.
# Runs right after the allocator, on its weights, so it works with sleeves on or off.
# It's a class because it remembers when it last fired (like the allocator remembers yesterday)
# Settings come from Config/risk.yaml (section "vix_breaker")


class VixBreaker:
    def __init__(self):
        settings = load "vix_breaker" from risk.yaml, check them (shares in [0,1], days >= 0)
        last_trigger = None      # date it last fired
        days_since = None        # trading days since then

    def _triggered(self, as_of):
        vix = last 2 days of VIX from get_series("vix", ..., as_of=as_of)
        jump = vix_today / vix_yesterday - 1
        return jump >= jump_pct or vix_today >= level

    def _cut_share_today(self):
        # how much of the short-vol weight to remove today
        if never fired                           --> 0
        if days_since <= hold_days               --> cut_share            (fully cut)
        if days_since <= hold_days + rebuild_days --> cut_share shrinking evenly to 0  (rebuilding)
        else                                      --> 0                    (back to normal)

    def apply(self, weights, as_of):
        # weights: the allocator's output (vol, equity, spread, reserve), adds up to 1
        if weights is None --> return None
        if _triggered(as_of) --> last_trigger = as_of, days_since = 0   (a new jump restarts the clock)
        else if last_trigger --> days_since += 1

        share = _cut_share_today()
        events = []
        for each sleeve in short_vol_sleeves:
            moved = weights[sleeve] * share
            weights[sleeve] -= moved
            weights["reserve"] += moved
            if moved > 0 --> events.append(rule="vix_circuit_breaker", action="cut", sleeve, detail=VIX + moved)

        return weights, events     # still adds up to 1. events --> trading.duckdb "risk_events"
