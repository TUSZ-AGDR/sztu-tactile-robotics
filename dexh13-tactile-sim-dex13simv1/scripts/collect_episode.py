#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

import mujoco

from dexh13sim.dataset_writer import DatasetWriter
from dexh13sim.hand_control import POLICY_NAMES, ScriptedHandPolicy, apply_action
from dexh13sim.pose_capture import PoseCapture
from dexh13sim.runtime import TactileRuntime, summarize_raw


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect a synchronized DexH13 tactile and pose episode.")
    parser.add_argument("--mjcf", type=Path, default=Path("assets/dexh13_mjcf/interactive_press_scene.xml"))
    parser.add_argument("--calibration", type=Path, default=Path("configs/calibration.yaml"))
    parser.add_argument("--steps", type=int, default=None)
    parser.add_argument("--seconds", type=float, default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--objects", nargs="*", default=["press_probe"], help="MuJoCo body names to record as objects.")
    parser.add_argument("--policy", choices=POLICY_NAMES, default="hold_open", help="Scripted 16-DoF hand control policy.")
    parser.add_argument("--policy-amplitude", type=float, default=0.45, help="Policy amplitude as a 0..1 fraction of joint control range.")
    parser.add_argument("--policy-period", type=float, default=2.0, help="Policy cycle period in seconds.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model = mujoco.MjModel.from_xml_path(str(args.mjcf))
    data = mujoco.MjData(model)
    runtime = TactileRuntime(model, calibration_yaml=args.calibration)
    pose_capture = PoseCapture(model, runtime.mount, args.objects)
    policy = ScriptedHandPolicy(
        model,
        name=args.policy,
        amplitude=args.policy_amplitude,
        period_s=args.policy_period,
    )

    steps = args.steps
    if steps is None:
        seconds = 10.0 if args.seconds is None else args.seconds
        steps = int(round(seconds / runtime.sim_dt))

    metadata = {
        "sim_dt": runtime.sim_dt,
        "sensor_native_hz": runtime.sensor_native_hz,
        "tactile_hz": runtime.tactile_hz,
        "tactile_hz_source": runtime.tactile_hz_source,
        "lsb_per_N": runtime.lsb_per_N,
        "mjcf_path": str(args.mjcf),
        "calibration_path": str(args.calibration),
        "mode": "collect_episode",
        "object_names": ",".join(args.objects),
        "policy": args.policy,
        "policy_amplitude": args.policy_amplitude,
        "policy_period_s": args.policy_period,
    }

    frames = 0
    nonzero_raw_frames = 0
    max_contact_count = 0
    with DatasetWriter(args.out, metadata) as writer:
        for _ in range(steps):
            action = apply_action(model, data, policy.action(float(data.time)))
            mujoco.mj_step(model, data)
            raw, contacts = runtime.raw_from_data(data)
            max_contact_count = max(max_contact_count, len(contacts))
            sampled = runtime.sample(raw)
            if sampled is None:
                continue

            detail_N, detail_sdk = runtime.detail(sampled)
            summary = summarize_raw(sampled)
            nonzero_raw_frames += int(summary.total_N > 1.0e-8)
            state = pose_capture.capture(
                data,
                action=action,
                contact_count=max_contact_count,
            )
            max_contact_count = 0
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
            frames += 1

    print(
        f"wrote {args.out} frames={frames} nonzero_raw_frames={nonzero_raw_frames} "
        f"objects={','.join(args.objects)} policy={args.policy}"
    )


if __name__ == "__main__":
    main()
