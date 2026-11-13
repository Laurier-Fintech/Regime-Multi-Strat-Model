from Data.DataBase.access import get_features, get_prices

from ModelHome.RegimeHMM import regime_hmm, state_labels

# The two models. Same maths (regime_hmm.py) used twice, just fed different features
# Later these move into Config/model.yaml
STRESS_FEATURES = ["log_vix", "credit_spread", "credit_spread_chg_20d"]
# TODO v2: add "vix_term" back to STRESS_FEATURES once Bloomberg VIX3M history (2008) is loaded.
#          Left out of v1 because it only starts 2009-09-18 and would cut 2008 out of the stress model.
DIRECTION_FEATURES = ["trend_spy", "curve_slope"]

REFIT_EVERY = "month"     # refit on the first trading day of each month
MIN_HISTORY_DAYS = 1260   # ~5 years of data before the first fit


class RegimeModel:
    """Holds both HMMs and remembers their state from one day to the next.
       The engine calls update(today) once per day. This is the only file in RegimeHMM that reads the database
    """

    def __init__(self):
        """Sets up an empty slot for each model

        Each model (stress and direction) keeps:
            features   -- which feature_ids it reads
            params     -- from regime_hmm.fit() (None until the first fit)
            scale_mean -- mean of each feature in the training window (to scale new days the same way)
            scale_std  -- std of each feature in the training window
            prob       -- yesterday's probabilities e.g. [0.9, 0.1]
            last_row   -- the date of the last feature row we stepped on (so we never step twice on the same row)
            last_fit   -- the date of the last refit
        """
        pass

    def update(self, as_of):
        """Gives the 4 mood probabilities for one day, using only data known on that day

        Keyword arguments:
        as_of -- the date the engine is asking about
        Return: calm-bull: XX, calm-bear: XX, stressed-bull: XX, stressed-bear: XX (sums to 1)
        """
        pass

        # For each model (stress, direction):

        #   Is it a refit day? (first time, or a new month started)
        #       Yes --> self._refit(model, as_of)
        #       No  --> self._step(model, as_of)

        # Combine --> self._combine()

    def _refit(self, model, as_of):
        """Re-learns one model on all data known up to as_of

        Pulls: get_features(model features, start=first date, end=as_of, as_of=as_of)
               --> table, dates down the side, one column per feature
        """
        pass

        # Drop rows with any blanks

        # Not enough history yet (< MIN_HISTORY_DAYS)? --> skip, no probabilities yet

        # scale_mean, scale_std from THIS window only --> X = (data - mean) / std

        # regime_hmm.fit(X) --> params
        # state_labels.name_states(params, features, kind) --> params in a fixed order

        # regime_hmm.filter_all(X, params) --> keep only the last row as today's prob
        # last_row = last date in the window, last_fit = as_of

    def _step(self, model, as_of):
        """Moves one model forward by one day

        Pulls: get_features(model features, start=as_of - 10 days, end=as_of, as_of=as_of)
               --> just the last few rows, we only need the newest one
        """
        pass

        # Take the newest row with no blanks

        # Same date as last_row? --> nothing new is known today (FRED lag), keep yesterday's prob

        # Scale it with the stored scale_mean / scale_std (NOT today's numbers)

        # regime_hmm.filter_step(prob, x_today, params) --> new prob
        # last_row = that row's date

    def _combine(self):
        """Turns the two models into the 4 moods

            calm-bull     = P(calm)     * P(bull)
            calm-bear     = P(calm)     * P(bear)
            stressed-bull = P(stressed) * P(bull)
            stressed-bear = P(stressed) * P(bear)

        Return: the 4 numbers above (they sum to 1 on their own)
        """
        pass

    def run(self, start, end):
        """Runs update() over every trading day from start to end. For research charts, not used by the engine

        Pulls: get_prices("spy", start, end, as_of=end) --> just to get the list of trading days (its dates)
        Return: a table, one row per day, one column per mood
        """
        pass

        # for each trading day --> self.update(day)

        # Plot it --> stressed should light up in 2008, 2011, 2015, 2018, 2020, 2022
