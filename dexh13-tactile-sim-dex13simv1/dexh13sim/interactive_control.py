from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import numpy as np

from .hand_control import FINGER_FLEXION_INDICES, SPREAD_INDICES, apply_action, control_range

PRESS_JOINT_NAME = "press_z"
MANUAL_PROBE_LIMITS = (-0.015, 0.015)
DEFAULT_PROBE_Z = -0.010


@dataclass(frozen=True)
class ManualControlState:
    close: float = 0.0
    spread: float = 0.0
    probe_z: float = DEFAULT_PROBE_Z
    quit_requested: bool = False

    def clipped(self, probe_limits: tuple[float, float] = MANUAL_PROBE_LIMITS) -> "ManualControlState":
        return replace(
            self,
            close=float(np.clip(self.close, 0.0, 1.0)),
            spread=float(np.clip(self.spread, -1.0, 1.0)),
            probe_z=float(np.clip(self.probe_z, probe_limits[0], probe_limits[1])),
        )


def manual_hand_action(model: Any, state: ManualControlState) -> np.ndarray:
    ranges = control_range(model)
    state = state.clipped()
    action = np.zeros(16, dtype=np.float32)

    for indices in FINGER_FLEXION_INDICES.values():
        for joint_id, weight in zip(indices, (1.0, 0.75, 0.55), strict=True):
            low, high = ranges[joint_id]
            action[joint_id] = low + (high - low) * state.close * weight

    spread_pattern = np.asarray([-0.5, -0.15, 0.15, 0.45], dtype=np.float32)
    for joint_id, weight in zip(SPREAD_INDICES, spread_pattern, strict=True):
        action[joint_id] = 0.25 * state.spread * float(weight)

    return action


def current_close_fraction(model: Any, data: Any) -> float:
    ranges = control_range(model)
    fractions = []
    for indices in FINGER_FLEXION_INDICES.values():
        for joint_id, weight in zip(indices, (1.0, 0.75, 0.55), strict=True):
            low, high = ranges[joint_id]
            span = float(high - low)
            if abs(span) <= 1.0e-12 or weight <= 0.0:
                continue
            qposadr = int(model.jnt_qposadr[joint_id])
            fractions.append((float(data.qpos[qposadr]) - float(low)) / span / float(weight))
    if not fractions:
        return 0.0
    return float(np.clip(np.mean(fractions), 0.0, 1.0))


def current_spread_fraction(model: Any, data: Any) -> float:
    weights = np.asarray([-0.5, -0.15, 0.15, 0.45], dtype=np.float64)
    fractions = []
    for joint_id, weight in zip(SPREAD_INDICES, weights, strict=True):
        if abs(float(weight)) <= 1.0e-12:
            continue
        qposadr = int(model.jnt_qposadr[joint_id])
        fractions.append(float(data.qpos[qposadr]) / (0.25 * float(weight)))
    if not fractions:
        return 0.0
    return float(np.clip(np.mean(fractions), -1.0, 1.0))


def hold_current_manual_target(model: Any, data: Any, state: ManualControlState) -> ManualControlState:
    return replace(
        state,
        close=current_close_fraction(model, data),
        spread=current_spread_fraction(model, data),
    ).clipped(manual_probe_limits(model))


def press_joint_id(model: Any) -> int:
    import mujoco

    return int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, PRESS_JOINT_NAME))


def press_joint_limits(model: Any) -> tuple[float, float]:
    joint_id = press_joint_id(model)
    if joint_id < 0:
        return MANUAL_PROBE_LIMITS
    return tuple(float(v) for v in model.jnt_range[joint_id])


def manual_probe_limits(model: Any) -> tuple[float, float]:
    joint_low, joint_high = press_joint_limits(model)
    return max(joint_low, MANUAL_PROBE_LIMITS[0]), min(joint_high, MANUAL_PROBE_LIMITS[1])


def apply_manual_control(model: Any, data: Any, state: ManualControlState) -> np.ndarray:
    import mujoco

    state = state.clipped(manual_probe_limits(model))
    action = apply_action(model, data, manual_hand_action(model, state))

    joint_id = press_joint_id(model)
    if joint_id >= 0:
        qposadr = int(model.jnt_qposadr[joint_id])
        dofadr = int(model.jnt_dofadr[joint_id])
        data.qpos[qposadr] = state.probe_z
        data.qvel[dofadr] = 0.0
        mujoco.mj_forward(model, data)

    return action


def handle_manual_key(state: ManualControlState, key: str) -> ManualControlState:
    if key == "c":
        return replace(state, close=min(1.0, state.close + 0.05)).clipped()
    if key == "o":
        return replace(state, close=max(0.0, state.close - 0.05)).clipped()
    if key == "u":
        return replace(state, probe_z=state.probe_z + 0.002).clipped()
    if key == "d":
        return replace(state, probe_z=state.probe_z - 0.002).clipped()
    if key == "a":
        return replace(state, spread=max(-1.0, state.spread - 0.05)).clipped()
    if key == "s":
        return replace(state, spread=min(1.0, state.spread + 0.05)).clipped()
    if key == "r":
        return ManualControlState()
    if key == "q":
        return replace(state, quit_requested=True)
    return state.clipped()


def manual_help() -> str:
    return "manual keys: c close, o open, d probe-down, u probe-up, a/s spread, r reset, q quit"
