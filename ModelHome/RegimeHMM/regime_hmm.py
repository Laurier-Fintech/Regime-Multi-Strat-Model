from pathlib import Path

import numpy as np
import yaml

# Settings come from Config/model.yaml (section regime_hmm), not from this file
CONFIG_FILE = Path(__file__).resolve().parents[2] / "Config" / "model.yaml"
with open(CONFIG_FILE, encoding="utf-8") as f:
    SETTINGS = yaml.safe_load(f)["regime_hmm"]

def _guess(X, n_states, rng):
    T, F = X.shape
    rows = rng.choice(T, size=n_states, replace=False)
    means = X[rows].copy()
    spread = np.atleast_2d(np.cov(X.T))+ SETTINGS["cov_floor"] * np.eye(F)
    covs = np.array([spread for k in range(n_states)])

    pi = np.ones(n_states)/n_states

    stay = SETTINGS["start_stay_prob"]
    A = np.full((n_states, n_states), (1 - stay) / (n_states - 1))
    np.fill_diagonal(A, stay)

    return {"pi": pi, "A": A, "means": means, "covs": covs}

def _densities(X, means, covs):
    """
    For each day and each state how likly is todays data if we're in that state?
    uses the multivariate normal density, works in logs so tiny numbers dont round to 0 
    """
    T, F = X.shape
    K = len(means)

    log_B = np.zeros((T, K))
    for k in range(K):
        diff = X - means[k]
        inv = np.linalg.inv(covs[k])
        dist = np.sum(np.matmul(diff, inv) * diff, axis=1)
        log_det = np.log(np.linalg.det(covs[k]))
        log_B[:, k] = -0.5 * (dist + log_det + F * np.log(2 * np.pi))

    shift = log_B.max(axis=1)
    B = np.exp(log_B - shift[:, None])
    return B, shift

def _forward(B, pi, A):
    """Goes day 1 --> last day. alpha[t] = prob of each state on day t using days up to t only"""
    T, K = B.shape
    alpha = np.zeros((T, K))
    scale = np.zeros(T)

    for t in range(T):
        if t == 0:
            a = pi * B[0]
        else:
            a = np.matmul(alpha[t - 1], A) * B[t]
        scale[t] = a.sum()
        alpha[t] = a / scale[t]

    return alpha, scale

def _backward(B, A, scale):
    """Goes last day --> day 1. Uses FUTURE days, so only ever used inside fit()"""
    T, K = B.shape
    beta = np.ones((T, K))

    for t in range(T - 2, -1, -1):
        beta[t] = np.matmul(A, B[t + 1] * beta[t + 1]) / scale[t + 1]

    return beta

def fit(X: np.ndarray, n_states=SETTINGS["n_states"], n_starts=SETTINGS["n_starts"],
        max_rounds=SETTINGS["max_rounds"], tol=SETTINGS["tol"], Input_seed=SETTINGS["seed"],
        warm_start=None):
    """Learns what each state looks like and how often the market switches between them
        1. Guess (or start from last fit's answer, see warm_start)
        2. Score every day (forward and backward passes)
        3. Re-estimate means, covs, A and pi
        4. Repeat 2-3 until the fit stops improving
        5. Do it all n_starts times from different guesses and keep the best

    Keyword arguments:
    X -- numpy table, one row per day, one column per feature (already scaled)
    n_states -- how many states
    warm_start -- params from the last fit (or None). If given, the first attempt starts from them
                  instead of a random guess. It's usually already close, so it finishes in a few rounds
    Return: A dict of pi, A, means, covs, loglik
    """
    T, F = X.shape
    rng = np.random.default_rng(seed=Input_seed)
    best = None

    for start in range(n_starts):

        # first attempt --> last fit's answer (if we have one), the rest --> random guesses
        if start == 0 and warm_start is not None:
            params = warm_start
        else:
            params = _guess(X, n_states, rng)
        pi, A, means, covs = params['pi'], params['A'], params['means'], params['covs']
        old_loglik = -np.inf

        for i in range(max_rounds):
            B, shift = _densities(X, means, covs)
            alpha, scale = _forward(B, pi, A)
            beta = _backward(B, A, scale)

            gamma = alpha*beta                              # prob of each state on each day
            loglik = np.log(scale).sum() + shift.sum()      # how good the fit is?

            if loglik - old_loglik < tol:
                break
            old_loglik = loglik

            moves = np.matmul(alpha[:-1].T, B[1:] * beta[1:] / scale[1:, None]) * A
            A = moves/moves.sum(axis=1, keepdims=True)

            pi = gamma[0]

            means = np.zeros((n_states, F))
            covs = np.zeros((n_states, F, F))
            for k in range(n_states):
                w = gamma[:, k]                              # how much each day belongs to state k
                means[k] = (w[:, None] * X).sum(axis=0) / w.sum()
                diff = X - means[k]
                covs[k] = np.matmul((w[:, None] * diff).T, diff) / w.sum()
                covs[k] += SETTINGS["cov_floor"] * np.eye(F)
            
        if np.isfinite(loglik) and (best is None or loglik > best['loglik']):
            best = {"pi": pi, "A": A, "means": means, "covs": covs, "loglik": loglik}
    return best



def filter_step(prev_prob, x_today, params):
    """ Predict: prev_prob @ A. If you were 90% calm yesterday, that gives your chance of being calm today before looking at today's data.
        Update: multiply by how well today's data fits each state.
        Normalise so it sums to 1.
        On the first day, prev_prob = pi.
    """
    B, shift = _densities(x_today.reshape(1, -1), params["means"], params['covs'])
    p = np.matmul(prev_prob, params["A"]) * B[0]
    return p / p.sum()

def filter_all(X, params):
    """Loops filter_step over every row and returns one probability row per day"""
    B, shift = _densities(X, params["means"], params["covs"])
    alpha,scale  = _forward(B, params['pi'], params['A'])
    return alpha
