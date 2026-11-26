import pandas as pd

from Config.settings import load
from Data.DataBase.access import get_versions

# The speed-up: load prices / series / dividends ONCE for a whole backtest, then answer each day
# from memory instead of asking the database ~5 times a day (20 min --> ~2 min).
# Same as-of rule as access.py: on each day only rows with known_at <= that day are visible,
# newest version per date. tests/system_check.py checks it matches access.py exactly

LOOKBACK_DAYS = load("configs.yaml", "portfolio")["price_lookback_days"]


class MarketBook:
    """Everything a backtest reads, in memory. A class because it holds the loaded tables"""

    def __init__(self, price_ids, series_ids, start, end):
        """Loads every version from start (minus the lookback) to end, known by end"""
        first = pd.Timestamp(start) - pd.Timedelta(days=LOOKBACK_DAYS + 7)
        self.tables = {
            "prices": self._split(get_versions("prices", price_ids, first, end, as_of=end)),
            "series": self._split(get_versions("series", series_ids, first, end, as_of=end)),
            "dividends": self._split(get_versions("dividends", price_ids, first, end, as_of=end)),
            "splits": self._split(get_versions("splits", price_ids, first, end, as_of=end)),
        }

    def _split(self, df):
        """One small table per id --> each daily lookup only searches that id's rows"""
        df["obs_date"] = pd.to_datetime(df["obs_date"])
        df["known_at"] = pd.to_datetime(df["known_at"])
        return {sid: rows.drop(columns="series_id") for sid, rows in df.groupby("series_id")}

    def _known(self, source, sid, day, days_back):
        """One id's values as known on `day`: obs_date in [day - days_back, day], newest version per date"""
        rows = self.tables[source].get(sid)
        if rows is None:
            return pd.Series(dtype=float)
        day = pd.Timestamp(day)
        rows = rows[(rows["known_at"] <= day) & (rows["obs_date"] <= day)
                    & (rows["obs_date"] >= day - pd.Timedelta(days=days_back))]
        rows = rows.sort_values(["obs_date", "known_at"]).drop_duplicates("obs_date", keep="last")
        return rows.set_index("obs_date")["value"].dropna()

    def last_prices(self, ids, day):
        """Last known close per id (today's, or an older one within the lookback), same as valuation needs

        Return: dict id --> (price, date it's from)
        """
        out = {}
        for sid in ids:
            known = self._known("prices", sid, day, LOOKBACK_DAYS)
            if not known.empty:
                out[sid] = (known.iloc[-1], known.index[-1])
        return out

    def series(self, sid, day):
        """A series' known values over the lookback, oldest --> newest (e.g. VIX, T-bill rate)"""
        return self._known("series", sid, day, LOOKBACK_DAYS)

    def dividends(self, ids, day):
        """Dividends with ex-date exactly on `day`: dict id --> dividend per share"""
        return self._on_day("dividends", ids, day)

    def splits(self, ids, day):
        """Splits with ex-date exactly on `day`: dict id --> new shares per old share"""
        return self._on_day("splits", ids, day)

    def _on_day(self, source, ids, day):
        """Events (dividends / splits) dated exactly on `day`"""
        out = {}
        for sid in ids:
            known = self._known(source, sid, day, 0)
            if not known.empty:
                out[sid] = known.iloc[-1]
        return out
