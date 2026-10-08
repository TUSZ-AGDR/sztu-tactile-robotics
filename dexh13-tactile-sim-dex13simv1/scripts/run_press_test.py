#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

import mujoco

from dexh13sim.dataset_writer import DatasetWriter
from dexh13sim.pose_capture import PoseCapture
from dexh13sim.runtime import TactileRuntime


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a short DexH13 tactile press smoke test.")
    parser.add_argument("--mjcf", type=Path, default=Path("assets/dexh13_mjcf/test_press_scene.xml"))
    parser.add_argument("--calibration", type=Path, default=Path("configs/calibration.yaml"))
    parser.add_argument("--steps", type=int, default=400)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--objects", nargs="*", default=["press_sphere"])
    args = parser.parse_args()

    model = mujoco.MjModel.from_xml_path(str(args.mjcf))
    data = mujoco.MjData(model)
    runtime = TactileRuntime(model, calibration_yaml=args.calibration)
    pose_capture = PoseCapture(model, runtime.mount, args.objects)

    emitted = 0
    last_norm = 0.0
    metadata = {
        "sim_dt": runtime.sim_dt,
        "sensor_native_hz": runtime.sensor_native_hz,
        "tactile_hz": runtime.tactile_hz,
        "tactile_hz_source": runtime.tactile_hz_source,
        "lsb_per_N": runtime.lsb_per_N,
        "mjcf_path": str(args.mjcf),
        "calibration_path": str(args.calibration),
        "mode": "press_test",
        "object_names": ",".join(args.objects),
    }
    writer_context = DatasetWriter(args.out, metadata) if args.out else None
    writer = writer_context.__enter__() if writer_context is not None else None
    try:
        for _ in range(args.steps):
            mujoco.mj_step(model, data)
            raw, contacts = runtime.raw_from_data(data)
            sampled = runtime.sample(raw)
            if sampled is not None:
                emitted += 1
                detail_N, detail_sdk = runtime.detail(sampled)
                last_norm = float((detail_N * detail_N).sum() ** 0.5)
                if writer is not None:
                    state = pose_capture.capture(data, contact_count=len(contacts))
                    writer.append(
                        time_s=float(data.time),
                        detail_N=detail_N,
                        detail_sdk=detail_sdk,
                        raw_sensor_N=sampled,
                        qpos=state["qpos"],
                        qvel=state["qvel"],
                        action=state["action"],
                        sensor_frame_xpos=state["sensor_frame_xpos"],
                        sensor_frame_xquat=state["sensor_frame_xquat"],
                        object_xpos=state["object_xpos"],
                        object_xquat=state["object_xquat"],
                        object_cvel=state["object_cvel"],
                        contact_count=state["contact_count"],
                    )
    finally:
        if writer_context is not None:
            writer_context.__exit__(None, None, None)

    print(f"frames={emitted} last_norm={last_norm:.6f}")


if __name__ == "__main__":
    main()
