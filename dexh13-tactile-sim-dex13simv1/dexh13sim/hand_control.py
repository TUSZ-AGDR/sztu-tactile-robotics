from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

PolicyName = Literal["hold_open", "sine_close", "index_tap"]
POLICY_NAMES: tuple[PolicyName, ...] = ("hold_open", "sine_close", "index_tap")

FINGER_FLEXION_INDICES = {
    "index": (1, 2, 3),
    "middle": (5, 6, 7),
    "ring": (9, 10, 11),
    "thumb": (13, 14, 15),
}
SPREAD_INDICES = (0, 4, 8, 12)


def control_range(model: Any) -> np.ndarray:
    ranges = np.asarray(model.actuator_ctrlrange[:16], dtype=np.float32)
    if ranges.shape != (16, 2):
        raise ValueError(f"DexH13 scripted policies require 16 position actuators, got {ranges.shape}")
    return ranges


def clip_action(model: Any, action: np.ndarray) -> np.ndarray:
    values = np.asarray(action, dtype=np.float32)
    if values.shape != (16,):
        raise ValueError(f"expected action shape (16,), got {values.shape}")
    ranges = control_range(model)
    return np.clip(values, ranges[:, 0], ranges[:, 1]).astype(np.float32)


def apply_action(model: Any, data: Any, action: np.ndarray) -> np.ndarray:
    applied = clip_action(model, action)
    data.ctrl[:16] = applied
    return applied


@dataclass(frozen=True)
class ScriptedHandPolicy:
    model: Any
    name: PolicyName = "hold_open"
    amplitude: float = 0.45
    period_s: float = 2.0

    def action(self, time_s: float) -> np.ndarray:
        if self.period_s <= 0.0:
            raise ValueError("period_s must be positive")
        if self.name == "hold_open":
            return clip_action(self.model, np.zeros(16, dtype=np.float32))
        if self.name == "sine_close":
            return self._sine_close(float(time_s))
        if self.name == "index_tap":
            return self._index_tap(float(time_s))
        raise ValueError(f"unsupported policy {self.name!r}")

    def _sine_close(self, time_s: float) -> np.ndarray:
        ranges = control_range(self.model)
        phase = 0.5 - 0.5 * np.cos(2.0 * np.pi * time_s / self.period_s)
        action = np.zeros(16, dtype=np.float32)
        fraction = float(np.clip(self.amplitude, 0.0, 1.0)) * phase

        for indices in FINGER_FLEXION_INDICES.values():
            for joint_id, weight in zip(indices, (1.0, 0.75, 0.55), strict=True):
                low, high = ranges[joint_id]
                action[joint_id] = low + (high - low) * fraction * weight

        spread = 0.15 * float(np.clip(self.amplitude, 0.0, 1.0)) * np.sin(2.0 * np.pi * time_s / self.period_s)
        spread_pattern = np.asarray([-0.5, -0.15, 0.15, 0.45], dtype=np.float32)
        for joint_id, weight in zip(SPREAD_INDICES, spread_pattern, strict=True):
            action[joint_id] = spread * float(weight)

        return clip_action(self.model, action)

    def _index_tap(self, time_s: float) -> np.ndarray:
        ranges = control_range(self.model)
        phase = 0.5 - 0.5 * np.cos(2.0 * np.pi * time_s / self.period_s)
        action = np.zeros(16, dtype=np.float32)
        fraction = float(np.clip(self.amplitude, 0.0, 1.0)) * phase

        for joint_id, weight in zip(FINGER_FLEXION_INDICES["index"], (1.0, 0.8, 0.6), strict=True):
            low, high = ranges[joint_id]
            action[joint_id] = low + (high - low) * fraction * weight

        return clip_action(self.model, action)
