
def _densities(X, means, covs):
    """
    For each day and each state how likly is todays data if we're in that state?
    uses the multivariate normal density, works in logs so tiny numbers dont round to 0 
    """
    pass

def _forward(X, params):
    pass

def _backwards(X, params):
    pass   



def fit(X, n_states=2):
    """Learns what each state looks like and how often the market switches between them
        1. Guess Pick a random starting averages for each state. Use overall spread of the data for each states covariance matrix. Pick a random starting transition matrix.
           Start with a a "sticky" switching table: 95% chance of staying in the same state tomorrow
        2. For each day work out the probability it was in each state, using the whole window (forward and backwards passes)
        3. Re-estimate: Each states average = the average of the days weighted by how likley each day was in that state
           then same idea for the covariance and btw the switching table = how often the market moved form state i to j      
        4. repreat steps 2-3 unitl the fit stops improving
        5. do the whole thing about 10 times from different random guesses and keep the best
    
    Keyword arguments:
    argument -- description
    Return: A dict of pi (starting prob.) A (2x2 switching matrix), means (state * features), covs (one coveraince per state), loglik (how good the fit it )
    """
    
    pass

def filter_step(prev_prob, x_today, params):
    """ Predict: prev_prob @ A. If you were 90% calm yesterday, that gives your chance of being calm today before looking at today's data.
        Update: multiply by how well today's data fits each state.
        Normalise so it sums to 1.
        On the first day, prev_prob = pi.
    """
    pass

def filter_all(X, params):
    """Loops filter_step over every row and returns one probability row per day"""
    pass