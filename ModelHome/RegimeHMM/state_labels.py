import numpy as np

from Config.settings import load

SETTINGS = load("model.yaml", "regime_model")


def _swap(params, order):
    """Helper: applies the new order to pi, A, means and covs so nothing gets mixed up

    Keyword arguments:
    params -- dict from fit()
    order -- list of state indexes in the new order e.g. [1, 0]
    Return: new params dict
    """
    return {
        "pi": params["pi"][order],
        "A": params["A"][order][:, order],      # rows AND columns, both are states
        "means": params["means"][order],
        "covs": params["covs"][order],
        "loglik": params["loglik"],             # the fit score doesn't change when we rename
    }

def name_states(params, feature_names, kind):
    """After every refit the states come out in a random order (state 0 could be calm or stressed).
       This puts them in a fixed order so state 0 is always calm/bull and state 1 is always stressed/bear

        stress model    --> the state with the higher average log_vix is stressed
        direction model --> the state with the higher average trend_spy is bull

    Keyword arguments:
    params -- the dict that comes out of regime_hmm.fit() (pi, A, means, covs, loglik)
    feature_names -- the column names of X in order, so we know which column of means is log_vix / trend_spy
    kind -- 'stress' or 'direction'
    Return: the same params dict but reordered, plus the labels in order e.g. ['calm', 'stressed']
    """
    if kind == "stress":
        col = feature_names.index(SETTINGS["stress_label_feature"])
        labels = ["calm", "stressed"]
        order = np.argsort(params['means'][:, col])
    elif kind == "direction":
        col = feature_names.index(SETTINGS["direction_label_feature"])
        labels= ["bull", "bear"]
        order = np.argsort(params["means"][:, col])[::-1]
    else:
        raise ValueError(f"kind must be 'stress' or 'direction', got {kind}")

    return _swap(params, order), labels
