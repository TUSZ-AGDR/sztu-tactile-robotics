from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import numpy as np


DEFAULT_OBJECT_BODY = "free_sphere"
DEFAULT_OBJECT_POS = (0.219, -0.0315, 0.026)
DEFAULT_OBJECT_QUAT = (1.0, 0.0, 0.0, 0.0)
MAX_PHYSICAL_DRAG_PENETRATION_M = 0.004


@dataclass(frozen=True)
class ObjectControlState:
    body_name: str = DEFAULT_OBJECT_BODY
    pos: tuple[float, float, float] = DEFAULT_OBJECT_POS
    quat: tuple[float, float, float, float] = DEFAULT_OBJECT_QUAT
    step: float = 0.002

    def normalized(self) -> "ObjectControlState":
        quat = np.asarray(self.quat, dtype=np.float64)
        norm = float(np.linalg.norm(quat))
        if norm <= 0.0:
            quat = np.asarray(DEFAULT_OBJECT_QUAT, dtype=np.float64)
        else:
            quat = quat / norm
        return replace(
            self,
            pos=tuple(float(v) for v in self.pos),
            quat=tuple(float(v) for v in quat),
            step=float(max(0.0005, min(0.05, self.step))),
        )


def free_joint_id_for_body(model: Any, body_name: str) -> int:
    import mujoco

    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name)
    if body_id < 0:
        raise ValueError(f"missing MuJoCo body {body_name}")

    jnt_adr = int(model.body_jntadr[body_id])
    jnt_num = int(model.body_jntnum[body_id])
    for joint_id in range(jnt_adr, jnt_adr + jnt_num):
        if int(model.jnt_type[joint_id]) == int(mujoco.mjtJoint.mjJNT_FREE):
            return joint_id
    raise ValueError(f"body {body_name} does not have a freejoint")


def target_body_name_for(body_name: str) -> str:
    return f"{body_name}_target"


def mocap_id_for_body(model: Any, body_name: str) -> int:
    import mujoco

    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name)
    if body_id < 0:
        raise ValueError(f"missing MuJoCo body {body_name}")
    mocap_id = int(model.body_mocapid[body_id])
    if mocap_id < 0:
        raise ValueError(f"body {body_name} is not a mocap body")
    return mocap_id


def apply_object_control(model: Any, data: Any, state: ObjectControlState) -> ObjectControlState:
    import mujoco

    state = state.normalized()
    free_joint_id_for_body(model, state.body_name)
    mocap_id = mocap_id_for_body(model, target_body_name_for(state.body_name))
    data.mocap_pos[mocap_id] = np.asarray(state.pos, dtype=np.float64)
    data.mocap_quat[mocap_id] = np.asarray(state.quat, dtype=np.float64)
    mujoco.mj_forward(model, data)
    return state


def body_pose(model: Any, data: Any, body_name: str) -> tuple[np.ndarray, np.ndarray]:
    import mujoco

    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name)
    if body_id < 0:
        raise ValueError(f"missing MuJoCo body {body_name}")
    return np.asarray(data.xpos[body_id], dtype=np.float64), np.asarray(data.xquat[body_id], dtype=np.float64)


def sync_object_control_to_body(model: Any, data: Any, state: ObjectControlState) -> ObjectControlState:
    pos, quat = body_pose(model, data, state.body_name)
    return apply_object_control(model, data, replace(state, pos=tuple(pos), quat=tuple(quat)))


def sync_object_control_to_mocap_target(model: Any, data: Any, state: ObjectControlState) -> ObjectControlState:
    mocap_id = mocap_id_for_body(model, target_body_name_for(state.body_name))
    return replace(
        state,
        pos=tuple(float(v) for v in data.mocap_pos[mocap_id]),
        quat=tuple(float(v) for v in data.mocap_quat[mocap_id]),
    ).normalized()


def halt_object_motion(model: Any, data: Any, state: ObjectControlState) -> ObjectControlState:
    joint_id = free_joint_id_for_body(model, state.body_name)
    dofadr = int(model.jnt_dofadr[joint_id])
    data.qvel[dofadr : dofadr + 6] = 0.0
    return sync_object_control_to_body(model, data, state)


def viewer_is_perturbing_body(viewer: Any, model: Any, body_name: str) -> bool:
    import mujoco

    perturb = getattr(viewer, "perturb", None)
    if perturb is None:
        return False
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name)
    if body_id < 0:
        return False
    selected = int(getattr(perturb, "select", -1))
    active = int(getattr(perturb, "active", 0)) or int(getattr(perturb, "active2", 0))
    return selected == body_id and bool(active)


def handle_object_key(state: ObjectControlState, key: str) -> ObjectControlState:
    state = state.normalized()
    x, y, z = state.pos
    step = state.step
    if key == "h":
        return replace(state, pos=(x - step, y, z))
    if key == "l":
        return replace(state, pos=(x + step, y, z))
    if key == "k":
        return replace(state, pos=(x, y - step, z))
    if key == "i":
        return replace(state, pos=(x, y + step, z))
    if key == "n":
        return replace(state, pos=(x, y, z - step))
    if key == "m":
        return replace(state, pos=(x, y, z + step))
    if key == "[":
        return replace(state, step=step * 0.5).normalized()
    if key == "]":
        return replace(state, step=step * 2.0).normalized()
    if key == "R":
        return ObjectControlState(body_name=state.body_name, step=state.step)
    return state


def object_help() -> str:
    return "object keys: h/l x-,x+; k/i y-,y+; n/m z-,z+; [/ ] step; R reset physical-drag target; release locks target to object pose"
