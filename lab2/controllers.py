"""Every controller returns closure speed (1/second), never joint forces."""
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class Observation:
    time_s: float
    tactile_time_s: float
    phase: str
    closure: float
    grip_force_N: float
    target_force_N: float
    sensor_forces_N: np.ndarray
    taxel_normal_N: np.ndarray


def tactile_policy(obs, gain=0.3, deadband_N=0.03):
    error = obs.target_force_N - obs.grip_force_N
    return 0.0 if abs(error) <= deadband_N else gain * error


def fixed_policy(obs, fixed_closure, max_rate, control_dt):
    # Open-loop ramp: it deliberately never reads grip_force_N.
    return min(max_rate, max(0.0, fixed_closure - obs.closure) / control_dt)
