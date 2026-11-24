
def _load_and_check():
    open model.yaml, take the "allocator" section
    mixes = mood_mixes as a table (rows = moods, columns = sleeves)

    check: all 4 moods are there
    check: all 4 sleeves are there
    check: no weight is < 0
    check: each mood row adds up to 1
    check: smoothing_step is in (0,1)
    check: no_trade_band is >= 0

    return mixes, smoothing_step, no_trade_band


def _blend(probs, mixes):
    # 70% stressed bear + 30% calm-bull --> 0.7 * that row + 0.3 * this row
    target = sum over moods of (prob of mood * that moods weights)
    return target

def _smooth(last_weights, new_weights, smoothing_step):
    # move only part of the way towards the target
    return last_weights + smoothing_step * (new_weights - last_weights)

class Allocator:
    def __init__(self):
        mixes, step, band = _load_and_check()
        last_weights = None

    def update(self, probs):
        if probs is None:
            return None
        target = _blend(probs, mixes)
        if last_weights is None:
            last_weights = target
            return last_weights
        smoothed = _smooth(last_weights, target, step)
        if the biggest |smoothed - last_weights| across sleeves < band:
            return last_weights
        last_weights = smoothed
        return last_weights
        
