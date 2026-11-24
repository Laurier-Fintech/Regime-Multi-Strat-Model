from pathlib import Path

import yaml
import pandas as pd

# Settings come from Config/model.yaml (section allocator), not from this file
MOODS_CHECK = ["stressed-bear", "calm-bull", "stressed-bull", "calm-bear"]
SLEEVES_CHECK = ["vol", "equity", "spread", "reserve"]

def _load_and_check():
    """Reads the allocator settings from model.yaml and checks them

    Return: mixes (rows = moods, cols = sleeves), smoothing_step, no_trade_band
    """
    CONFIG_FILE = Path(__file__).resolve().parents[1] / "Config" / "model.yaml"
    with open(CONFIG_FILE, encoding="utf-8") as f:
        SETTINGS = yaml.safe_load(f)["allocator"]
    mixes = SETTINGS['mood_mixes']

    # all 4 moods must be there
    missing_moods = [mood for mood in MOODS_CHECK if mood not in mixes]
    if missing_moods:
        raise ValueError(f"Moods missing from mood_mixes: {missing_moods}.")

    for mood in mixes:
        if mood not in MOODS_CHECK:
            raise ValueError(f"Mood {mood} is not in the accepted moods: [{', '.join(MOODS_CHECK)}].")

        # all 4 sleeves must be there in every mood
        missing_sleeves = [sleeve for sleeve in SLEEVES_CHECK if sleeve not in mixes[mood]]
        if missing_sleeves:
            raise ValueError(f"Mood {mood} is missing sleeves: {missing_sleeves}.")

        mood_total = 0.0
        for sleeve in mixes[mood]:
            if sleeve not in SLEEVES_CHECK:
                raise ValueError(f"Sleeve {sleeve} is not in the accepted sleeves: [{', '.join(SLEEVES_CHECK)}].")
            if mixes[mood][sleeve] < 0:
                raise ValueError(f"The {sleeve} has a value of {mixes[mood][sleeve]} which is below 0, should be above.")
            mood_total += mixes[mood][sleeve]

        if abs(mood_total - 1) > 1e-9:
            raise ValueError(f"The total probabilities of moods has a value of {mood_total} which is not 1.")

    if SETTINGS["smoothing_step"] > 1 or SETTINGS["smoothing_step"] <= 0:
        raise ValueError(f"The smoothing step has a value of {SETTINGS["smoothing_step"]} which is out of bounds of (0,1].")

    if SETTINGS["no_trade_band"] < 0:
        raise ValueError(f"The no trade band has a value of {SETTINGS["no_trade_band"]} which is out of bounds of >= 0.")

    # dict --> table, once
    mixes = pd.DataFrame(mixes).T[SLEEVES_CHECK]

    return mixes, SETTINGS["smoothing_step"], SETTINGS["no_trade_band"]


def _blend(probs, mixes):
    """70% stressed-bear + 30% calm-bull --> 0.7 * that row + 0.3 * this row

    Keyword arguments:
    probs -- the 4 mood probabilities
    mixes -- table from _load_and_check
    Return: one weight per sleeve
    """
    target = (mixes.mul(probs[MOODS_CHECK], axis=0)).sum()

    return target

def _smooth(last_weights, new_weights, smoothing_step):
    """Moves part of the way from yesterday's weights toward the target

    Return: the smoothed weights per sleeve
    """
    return last_weights + smoothing_step * (new_weights - last_weights)

class Allocator:
    """Mood probabilities --> sleeve weights. A class because it remembers yesterday's weights"""

    def __init__(self):
        self.mixes, self.step, self.band = _load_and_check()
        self.last_weights = None

    def update(self, probs):
        """Today's weights: blend --> band --> smooth

        Return: weight per sleeve, or None while the regime warms up
        """
        if probs is None:
            return None

        target = _blend(probs, self.mixes)

        # day one: go straight to the target
        if self.last_weights is None:
            self.last_weights = target
            return self.last_weights

        # band vs the TARGET (not the smoothed step), else the weights get stuck short of it
        biggest_gap = (target - self.last_weights).abs().max()

        if biggest_gap < self.band:
            return self.last_weights

        self.last_weights = _smooth(self.last_weights, target, self.step)

        return self.last_weights
