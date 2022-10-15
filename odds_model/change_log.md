# 2022-10-07
    - It's clear that the model is significantly underestimating the probability of clean sheets
    - Currently, the implied probability of a clean sheet is `[max(1 - x, 0) for x in df['mean_goals_against']]`
    - With this method, here's the value counts for each calculated proba_cs so far:
    | proba_cs | value_counts |
    |----------|--------------|
    | 0.00000  | 1941         |
    | 0.19180  | 23           |
    | 0.04350  | 22           |
    | 0.32590  | 21           |
    | 0.02060  | 21           |
    | 0.01430  | 20           |
    | 0.23680  | 17           |
    | 0.16230  | 12           |
    | 0.09985  | 5            |
    - This implies that we should only see a clean sheet 6.8% of the time
    - In fact, so far, we've seen clean sheets 29.2% of the time
    - Because of this, I am changing the x_pts calculation to calculate proba_cs with:
        - `[max(2 - x, 0) for x in df['mean_goals_against']]`
        