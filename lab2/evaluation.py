"""Scoring consumes raw physics, independent of the student controller."""
import numpy as np


class Evaluator:
    def __init__(self, config, initial_position):
        self.config = config
        self.initial_position = np.asarray(initial_position)
        self.peak_force_N = 0.0
        self.overforce_time_s = 0.0
        self.longest_overforce_s = 0.0
        self._overforce_run = 0.0
        self._support_run = 0.0
        self.failure_time_s = None
        self.reasons = set()
        self.minimum_height_m = float(initial_position[2])

    def update(self, time_s, dt, force_N, position, other_support_force):
        self.peak_force_N = max(self.peak_force_N, force_N)
        over = force_N > self.config.force_limit_N
        self._overforce_run = self._overforce_run + dt if over else 0.0
        self.overforce_time_s += dt if over else 0.0
        self.longest_overforce_s = max(self.longest_overforce_s, self._overforce_run)
        if self._overforce_run + 1e-12 >= self.config.overforce_duration_s:
            self.reasons.add("force_limit")
        if time_s < self.config.release_time_s:
            return
        self.minimum_height_m = min(self.minimum_height_m, float(position[2]))
        failures = []
        if self.initial_position[2] - position[2] > self.config.drop_distance_m:
            failures.append("dropped")
        if np.linalg.norm(position - self.initial_position) > self.config.escape_distance_m:
            failures.append("escaped")
        self._support_run = self._support_run + dt if other_support_force > .02 else 0.0
        if self._support_run >= .02:
            failures.append("external_support")
        if failures:
            self.reasons.update(failures)
            if self.failure_time_s is None:
                self.failure_time_s = time_s

    def summary(self, completed_time_s):
        end = self.failure_time_s if self.failure_time_s is not None else completed_time_s
        held_time = min(self.config.hold_time_s, max(0.0, end - self.config.release_time_s))
        completed = completed_time_s + 1e-9 >= self.config.duration_s
        if not completed:
            self.reasons.add("interrupted")
        return {
            "success": completed and not self.reasons,
            "completed": completed,
            "reasons": sorted(self.reasons),
            "held_time_s": held_time,
            "peak_force_N": self.peak_force_N,
            "overforce_time_s": self.overforce_time_s,
            "longest_overforce_s": self.longest_overforce_s,
            "minimum_height_m": self.minimum_height_m,
        }
