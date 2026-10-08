"""Student-facing parameters, independent of the MuJoCo model."""
from dataclasses import dataclass, asdict
import math


@dataclass(frozen=True)
class ExperimentConfig:
    object_name: str = "box"
    target_force_N: float = 4.0
    mass_kg: float = 0.03
    friction: float = 1.0
    disturbance: bool = True
    pull_force_N: float = 0.1
    approach_time_s: float = 2.0
    release_time_s: float = 4.0
    hold_time_s: float = 3.0
    pull_after_release_s: float = 1.5
    pull_duration_s: float = 0.25
    force_limit_N: float = 12.0
    overforce_duration_s: float = 0.02
    drop_distance_m: float = 0.015
    escape_distance_m: float = 0.04
    fixed_closure: float | None = None  # None selects the object's nominal 4 N preset.
    controller_gain: float = 0.3
    deadband_N: float = 0.03
    max_closure_rate: float = 0.6
    tactile_hz: int = 100
    noise_std_N: float = 0.0
    seed: int = 0

    def __post_init__(self):
        if self.object_name not in ("box", "cylinder", "sphere"):
            raise ValueError("object_name must be box, cylinder, or sphere")
        for name, value in asdict(self).items():
            if isinstance(value, (int, float)) and not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        for name in ("target_force_N", "mass_kg", "friction", "release_time_s",
                     "hold_time_s", "force_limit_N", "overforce_duration_s",
                     "drop_distance_m", "escape_distance_m", "max_closure_rate"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.fixed_closure is not None and not 0 <= self.fixed_closure <= 1:
            raise ValueError("fixed_closure must be in [0, 1]")
        for name in ("pull_force_N", "pull_after_release_s", "pull_duration_s",
                     "controller_gain", "deadband_N", "noise_std_N", "approach_time_s"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.approach_time_s >= self.release_time_s:
            raise ValueError("approach_time_s must be shorter than release_time_s")
        if self.tactile_hz <= 0 or self.tactile_hz != int(self.tactile_hz) or 2000 % self.tactile_hz:
            raise ValueError("tactile_hz must be an integer divisor of 2000")
        if self.seed < 0 or self.seed != int(self.seed):
            raise ValueError("seed must be a non-negative integer")
        if self.disturbance and (self.pull_duration_s <= 0 or
                self.pull_after_release_s + self.pull_duration_s > self.hold_time_s):
            raise ValueError("the pull must have positive duration and fit inside the hold phase")

    @property
    def duration_s(self):
        return self.release_time_s + self.hold_time_s

    def phase(self, time_s):
        if time_s < self.approach_time_s:
            return "approach"
        if time_s < self.release_time_s:
            return "grasp"
        if self.pulling(time_s):
            return "pull"
        return "hold"

    def pulling(self, time_s):
        elapsed = time_s - self.release_time_s
        return (self.disturbance and self.pull_after_release_s <= elapsed
                < self.pull_after_release_s + self.pull_duration_s)
