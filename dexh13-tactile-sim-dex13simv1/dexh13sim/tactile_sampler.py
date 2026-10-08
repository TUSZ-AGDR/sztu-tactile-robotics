from __future__ import annotations

import numpy as np


class TactileSampler:
    def __init__(self, sim_dt: float, tactile_hz: float, shape: tuple[int, int]):
        steps_per_frame = round(1.0 / (sim_dt * tactile_hz))
        if steps_per_frame <= 0:
            raise ValueError("steps_per_frame must be positive")
        if abs(steps_per_frame * sim_dt * tactile_hz - 1.0) > 1.0e-9:
            raise ValueError("sim_dt and tactile_hz must produce an integer step ratio")

        self.steps_per_frame = int(steps_per_frame)
        self.shape = shape
        self._accumulator = np.zeros(shape, dtype=np.float64)
        self._count = 0
        self.frames_emitted = 0

    def add(self, frame: np.ndarray) -> np.ndarray | None:
        frame = np.asarray(frame, dtype=np.float64)
        if frame.shape != self.shape:
            raise ValueError(f"expected frame shape {self.shape}, got {frame.shape}")

        self._accumulator += frame
        self._count += 1
        if self._count < self.steps_per_frame:
            return None

        averaged = (self._accumulator / self._count).astype(np.float32)
        self._accumulator.fill(0.0)
        self._count = 0
        self.frames_emitted += 1
        return averaged
