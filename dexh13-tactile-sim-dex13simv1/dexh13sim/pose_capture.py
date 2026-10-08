from __future__ import annotations

from typing import Any, Sequence

import numpy as np


HAND_JOINT_NAMES: tuple[str, ...] = (
    "right_index_joint_0",
    "right_index_joint_1",
    "right_index_joint_2",
    "right_index_joint_3",
    "right_middle_joint_0",
    "right_middle_joint_1",
    "right_middle_joint_2",
    "right_middle_joint_3",
    "right_ring_joint_0",
    "right_ring_joint_1",
    "right_ring_joint_2",
    "right_ring_joint_3",
    "right_thumb_joint_0",
    "right_thumb_joint_1",
    "right_thumb_joint_2",
    "right_thumb_joint_3",
)


def quat_from_xmat(xmat: np.ndarray) -> np.ndarray:
    mat = np.asarray(xmat, dtype=np.float64).reshape(3, 3)
    trace = float(np.trace(mat))
    if trace > 0.0:
        s = np.sqrt(trace + 1.0) * 2.0
        qw = 0.25 * s
        qx = (mat[2, 1] - mat[1, 2]) / s
        qy = (mat[0, 2] - mat[2, 0]) / s
        qz = (mat[1, 0] - mat[0, 1]) / s
    elif mat[0, 0] > mat[1, 1] and mat[0, 0] > mat[2, 2]:
        s = np.sqrt(1.0 + mat[0, 0] - mat[1, 1] - mat[2, 2]) * 2.0
        qw = (mat[2, 1] - mat[1, 2]) / s
        qx = 0.25 * s
        qy = (mat[0, 1] + mat[1, 0]) / s
        qz = (mat[0, 2] + mat[2, 0]) / s
    elif mat[1, 1] > mat[2, 2]:
        s = np.sqrt(1.0 + mat[1, 1] - mat[0, 0] - mat[2, 2]) * 2.0
        qw = (mat[0, 2] - mat[2, 0]) / s
        qx = (mat[0, 1] + mat[1, 0]) / s
        qy = 0.25 * s
        qz = (mat[1, 2] + mat[2, 1]) / s
    else:
        s = np.sqrt(1.0 + mat[2, 2] - mat[0, 0] - mat[1, 1]) * 2.0
        qw = (mat[1, 0] - mat[0, 1]) / s
        qx = (mat[0, 2] + mat[2, 0]) / s
        qy = (mat[1, 2] + mat[2, 1]) / s
        qz = 0.25 * s
    quat = np.asarray([qw, qx, qy, qz], dtype=np.float64)
    return quat / np.linalg.norm(quat)


class PoseCapture:
    def __init__(self, model: Any, mount: Any, object_body_names: Sequence[str] = ()):  # noqa: D401
        import mujoco

        self.model = model
        self.mount = mount
        self.hand_joint_ids = []
        for name in HAND_JOINT_NAMES:
            joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if joint_id < 0:
                raise ValueError(f"missing MuJoCo hand joint {name}")
            self.hand_joint_ids.append(joint_id)
        self.hand_qposadr = np.asarray([model.jnt_qposadr[joint_id] for joint_id in self.hand_joint_ids], dtype=np.int32)
        self.hand_dofadr = np.asarray([model.jnt_dofadr[joint_id] for joint_id in self.hand_joint_ids], dtype=np.int32)
        self.object_body_names = list(object_body_names)
        self.object_body_ids: list[int] = []
        for name in self.object_body_names:
            body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
            if body_id < 0:
                raise ValueError(f"missing MuJoCo body {name}")
            self.object_body_ids.append(body_id)

    def capture(
        self,
        data: Any,
        action: np.ndarray | None = None,
        contact_count: int = 0,
    ) -> dict[str, np.ndarray | int]:
        sensor_frame_xpos = []
        sensor_frame_xquat = []
        for instance in sorted(self.mount.instances, key=lambda item: item.sensor_id):
            sensor_frame_xpos.append(np.asarray(data.site_xpos[instance.site_id], dtype=np.float64))
            sensor_frame_xquat.append(quat_from_xmat(np.asarray(data.site_xmat[instance.site_id], dtype=np.float64)))

        object_xpos = []
        object_xquat = []
        object_cvel = []
        for body_id in self.object_body_ids:
            object_xpos.append(np.asarray(data.xpos[body_id], dtype=np.float64))
            object_xquat.append(np.asarray(data.xquat[body_id], dtype=np.float64))
            object_cvel.append(np.asarray(data.cvel[body_id], dtype=np.float64))

        return {
            "qpos": np.asarray(data.qpos[self.hand_qposadr], dtype=np.float32),
            "qvel": np.asarray(data.qvel[self.hand_dofadr], dtype=np.float32),
            "action": np.zeros(16, dtype=np.float32) if action is None else np.asarray(action, dtype=np.float32),
            "sensor_frame_xpos": np.asarray(sensor_frame_xpos, dtype=np.float32),
            "sensor_frame_xquat": normalize_rows(np.asarray(sensor_frame_xquat, dtype=np.float32)),
            "object_xpos": np.asarray(object_xpos, dtype=np.float32).reshape(len(self.object_body_ids), 3),
            "object_xquat": normalize_rows(np.asarray(object_xquat, dtype=np.float32).reshape(len(self.object_body_ids), 4)),
            "object_cvel": np.asarray(object_cvel, dtype=np.float32).reshape(len(self.object_body_ids), 6),
            "contact_count": int(contact_count),
        }


def normalize_rows(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    norms = np.linalg.norm(values, axis=1)
    if np.any(norms <= 0):
        raise ValueError("cannot normalize zero-length quaternion")
    return values / norms[:, None]
