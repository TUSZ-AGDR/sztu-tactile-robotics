"""Lab 2: edit GAIN or the force-error logic below.

Return a closure rate in 1/s: positive tightens, negative loosens, zero holds.
The simulation handles rate limits and converts closure into joint targets.
"""
GAIN = 0.3  # TODO: try 0.1, 0.3, and 0.6; watch for overshoot or dropping.


def policy(obs):
    error = obs.target_force_N - obs.grip_force_N
    return GAIN * error  # TODO: optionally ignore small force errors here.
