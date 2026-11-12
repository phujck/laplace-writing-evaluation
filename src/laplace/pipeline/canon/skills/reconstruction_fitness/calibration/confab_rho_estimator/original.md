The spectral radius is estimated empirically from successive lost-set deltas. Near a fixed point the
error decays as the ratio of consecutive deltas, which tends to the dominant eigenvalue magnitude.
Forming a ratio needs at least two deltas, so the estimator needs at least three verdicts; below
that it returns None. The estimate is noisy, because the adjudicator is stochastic.
