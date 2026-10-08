#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import h5py
import mujoco
import numpy as np

from dexh13sim.episode_validation import validate_episode
from dexh13sim.pose_capture import HAND_JOINT_NAMES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay a recorded DexH13 HDF5 episode in MuJoCo.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--mjcf", type=Path, required=True)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--realtime", action="store_true")
    return parser.parse_args()


def hand_qpos_addresses(model: mujoco.MjModel) -> np.ndarray:
    addresses = []
    for name in HAND_JOINT_NAMES:
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        if joint_id < 0:
            raise ValueError(f"missing hand joint {name}")
        addresses.append(int(model.jnt_qposadr[joint_id]))
    return np.asarray(addresses, dtype=np.int32)


def free_joint_for_body(model: mujoco.MjModel, body_name: str) -> int:
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name)
    if body_id < 0:
        return -1
    for joint_id in range(int(model.body_jntadr[body_id]), int(model.body_jntadr[body_id] + model.body_jntnum[body_id])):
        if int(model.jnt_type[joint_id]) == int(mujoco.mjtJoint.mjJNT_FREE):
            return joint_id
    return -1


def object_names_from_metadata(h5: h5py.File) -> list[str]:
    names = h5["metadata"].attrs.get("object_names", "")
    if isinstance(names, bytes):
        names = names.decode("utf-8")
    return [name for name in str(names).split(",") if name]


def apply_frame(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    hand_qposadr: np.ndarray,
    object_joint_ids: list[int],
    qpos: np.ndarray,
    object_xpos: np.ndarray,
    object_xquat: np.ndarray,
    frame_id: int,
) -> None:
    data.qpos[hand_qposadr] = qpos[frame_id]
    for object_index, joint_id in enumerate(object_joint_ids):
        if joint_id < 0 or object_index >= object_xpos.shape[1]:
            continue
        qposadr = int(model.jnt_qposadr[joint_id])
        data.qpos[qposadr : qposadr + 3] = object_xpos[frame_id, object_index]
        data.qpos[qposadr + 3 : qposadr + 7] = object_xquat[frame_id, object_index]
    data.qvel[:] = 0.0
    mujoco.mj_forward(model, data)


def main() -> None:
    args = parse_args()
    report = validate_episode(args.input)
    model = mujoco.MjModel.from_xml_path(str(args.mjcf))
    data = mujoco.MjData(model)
    hand_qposadr = hand_qpos_addresses(model)

    viewer = None
    if not args.headless:
        from mujoco import viewer as mujoco_viewer

        try:
            viewer = mujoco_viewer.launch_passive(model, data)
        except RuntimeError as exc:
            if sys.platform == "darwin" and "mjpython" in str(exc):
                raise SystemExit("ERROR: replay GUI requires mjpython on macOS. Add --headless for non-GUI replay.")
            raise

    replayed = 0
    with h5py.File(args.input, "r") as h5:
        object_joint_ids = [free_joint_for_body(model, name) for name in object_names_from_metadata(h5)]
        max_frames = report.frames if args.max_frames is None else min(report.frames, args.max_frames)
        for frame_id in range(max_frames):
            if viewer is not None and not viewer.is_running():
                break
            start = time.perf_counter()
            apply_frame(
                model,
                data,
                hand_qposadr,
                object_joint_ids,
                h5["qpos"],
                h5["state/object_xpos"],
                h5["state/object_xquat"],
                frame_id,
            )
            replayed += 1
            if viewer is not None:
                viewer.sync()
            if args.realtime:
                elapsed = time.perf_counter() - start
                time.sleep(max(0.0, 0.1 - elapsed))

    if viewer is not None:
        viewer.close()
    print(f"replayed frames={replayed} input={args.input}")


if __name__ == "__main__":
    main()
