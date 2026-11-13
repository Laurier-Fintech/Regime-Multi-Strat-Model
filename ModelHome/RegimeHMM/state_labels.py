
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
    pass

    # Find the column we sort by
    #   stress    --> log_vix
    #   direction --> trend_spy

    # Look at means[:, that column] --> which state is higher?

    # Build the new order e.g. [1, 0] if we need to swap

    # Reorder everything with it:
    #   pi    --> pi[order]
    #   A     --> rows AND columns: A[order][:, order]
    #   means --> means[order]
    #   covs  --> covs[order]


def _swap(params, order):
    """Helper: applies the new order to pi, A, means and covs so nothing gets mixed up

    Keyword arguments:
    params -- dict from fit()
    order -- list of state indexes in the new order e.g. [1, 0]
    Return: new params dict
    """
    pass
