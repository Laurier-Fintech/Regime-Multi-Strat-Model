import pandas as pd

from Data.DataBase.access import get_features, get_prices
from ModelHome.RegimeHMM import regime_hmm, state_labels
from Config.settings import load

# Settings come from Config/model.yaml (section regime_model), not from this file
SETTINGS = load("model.yaml", "regime_model")

# The two models. Same maths (regime_hmm.py) used twice, just fed different features
STRESS_FEATURES = SETTINGS["stress_features"]
DIRECTION_FEATURES = SETTINGS["direction_features"]

FIRST_DATE = SETTINGS["first_date"]                    # pull history from here
REFIT_EVERY_MONTHS = SETTINGS["refit_every_months"]    # how often to refit
MIN_HISTORY_DAYS = SETTINGS["min_history_days"]        # data needed before the first fit
ZSCORE_FEATURES = SETTINGS["zscore_features"]          # level features fed as "vs the last year" (fixes stuck states)
ZSCORE_WINDOW = SETTINGS["zscore_window"]              # trading days in that window


def _load(features, start, as_of):
    """Features known on as_of, from start. Features in ZSCORE_FEATURES become trailing z-scores:
       (value - average of its last ZSCORE_WINDOW values) / their std, using only past values (no look-ahead)

    Why: raw LEVELS shift after a crisis (credit spreads stayed higher after 2008 even on calm days),
         so the HMM split "before 2008" vs "after 2008" instead of calm vs stressed
    """
    z_features = [f for f in features if f in ZSCORE_FEATURES]
    if not z_features:
        return get_features(features, start, as_of, as_of=as_of).dropna()

    # read ~2 years before start, so the first z-scores have a full window behind them
    early = pd.Timestamp(start) - pd.Timedelta(days=2 * ZSCORE_WINDOW)
    data = get_features(features, early, as_of, as_of=as_of)
    for f in z_features:
        x = data[f].dropna()            # each feature on its own dates (holidays differ between sources)
        mean = x.rolling(ZSCORE_WINDOW, min_periods=ZSCORE_WINDOW).mean()
        std = x.rolling(ZSCORE_WINDOW, min_periods=ZSCORE_WINDOW).std()
        data[f] = ((x - mean) / std).reindex(data.index)
    return data[data.index >= pd.Timestamp(start)].dropna()


class RegimeModel:
    """Holds both HMMs and remembers their state from one day to the next.
       The engine calls update(today) once per day. This is the only file in RegimeHMM that reads the database
    """

    def __init__(self):
        """Sets up an empty slot for each model"""
        self.models = {
            "stress": self._empty_slot(STRESS_FEATURES),
            "direction": self._empty_slot(DIRECTION_FEATURES),
        }

    def _empty_slot(self, features):
        """Everything one model needs to remember between days"""
        return {
            "features": features,   # which feature_ids it reads
            "params": None,         # from regime_hmm.fit(), None until the first fit
            "labels": None,         # e.g. ['calm', 'stressed']
            "scale_mean": None,     # mean of each feature in the training window
            "scale_std": None,      # std of each feature in the training window
            "prob": None,           # yesterday's probabilities e.g. [0.9, 0.1]
            "last_row": None,       # date of the last feature row we used
            "last_fit": None,       # date of the last refit
        }

    def update(self, as_of):
        """Gives the 4 mood probabilities for one day, using only data known on that day

        Keyword arguments:
        as_of -- the date the engine is asking about
        Return: calm-bull: XX, calm-bear: XX, stressed-bull: XX, stressed-bear: XX (sums to 1)
                or None while there isn't enough history yet
        """
        as_of = pd.Timestamp(as_of)

        for kind, slot in self.models.items():
            # Is it a refit day?
            #   Yes --> _refit
            #   No  --> _step
            if self._is_refit_day(slot, as_of):
                self._refit(kind, slot, as_of)
            else:
                self._step(slot, as_of)

        return self._combine()

    def _is_refit_day(self, slot, as_of):
        """True the first time, then once every REFIT_EVERY_MONTHS months"""
        if slot["last_fit"] is None:
            return True
        months = (as_of.year - slot["last_fit"].year) * 12 + (as_of.month - slot["last_fit"].month)
        return months >= REFIT_EVERY_MONTHS

    def _refit(self, kind, slot, as_of):
        """Re-learns one model on all data known up to as_of"""

        # Pull everything known on as_of --> table, dates down the side, one column per feature
        data = _load(slot["features"], FIRST_DATE, as_of)

        # Not enough history yet --> no probabilities, try again tomorrow
        if len(data) < MIN_HISTORY_DAYS:
            return

        # Scale with this window only --> X = (data - mean) / std
        slot["scale_mean"] = data.mean()
        slot["scale_std"] = data.std()
        X = ((data - slot["scale_mean"]) / slot["scale_std"]).to_numpy()

        # Fit (warm start from last quarter's answer if we have one), then put the states in a fixed order
        params = regime_hmm.fit(X, warm_start=slot["params"])
        params, labels = state_labels.name_states(params, slot["features"], kind)

        # Today's prob = last row of the filtered probabilities (look-back only)
        slot["params"] = params
        slot["labels"] = labels
        slot["prob"] = regime_hmm.filter_all(X, params)[-1]
        slot["last_row"] = data.index[-1]
        slot["last_fit"] = as_of

    def _step(self, slot, as_of):
        """Moves one model forward over any rows that became known since last time"""
        if slot["params"] is None:
            return

        # Only the rows after the last one we used
        start = slot["last_row"] + pd.Timedelta(days=1)
        new_rows = _load(slot["features"], start, as_of)

        # Usually 1 new row. 0 if nothing new is known today (FRED lag). More if days were skipped
        for date, row in new_rows.iterrows():
            x = ((row - slot["scale_mean"]) / slot["scale_std"]).to_numpy()   # scale with the STORED numbers
            slot["prob"] = regime_hmm.filter_step(slot["prob"], x, slot["params"])
            slot["last_row"] = date

    def _combine(self):
        """Turns the two models into the 4 moods

            calm-bull     = P(calm)     * P(bull)
            calm-bear     = P(calm)     * P(bear)
            stressed-bull = P(stressed) * P(bull)
            stressed-bear = P(stressed) * P(bear)

        Return: a pandas Series of the 4 numbers (they sum to 1), or None if a model isn't ready
        """
        stress = self.models["stress"]
        direction = self.models["direction"]
        if stress["prob"] is None or direction["prob"] is None:
            return None

        moods = {}
        for i, s_label in enumerate(stress["labels"]):
            for j, d_label in enumerate(direction["labels"]):
                moods[f"{s_label}-{d_label}"] = stress["prob"][i] * direction["prob"][j]
        return pd.Series(moods)

    def run(self, start, end):
        """Runs update() over every trading day from start to end. For research charts, not used by the engine

        Return: a table, one row per day, one column per mood
        """
        # SPY's dates = the list of trading days
        days = get_prices("spy", start, end, as_of=end).index

        rows = {}
        for day in days:
            moods = self.update(day)
            if moods is not None:
                rows[day] = moods

        return pd.DataFrame(rows).T
