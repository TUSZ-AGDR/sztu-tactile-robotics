from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import h5py
import mujoco
import numpy as np

from dexh13sim.hand_control import FINGER_FLEXION_INDICES
from dexh13sim.interactive_control import (
    DEFAULT_PROBE_Z,
    MANUAL_PROBE_LIMITS,
    ManualControlState,
    apply_manual_control,
    current_close_fraction,
    handle_manual_key,
    hold_current_manual_target,
)


def test_manual_control_updates_hand_action_and_probe_joint():
    model = mujoco.MjModel.from_xml_path("assets/dexh13_mjcf/interactive_press_scene.xml")
    data = mujoco.MjData(model)
    state = ManualControlState(close=0.4, probe_z=-0.014)

    action = apply_manual_control(model, data, state)

    press_joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "press_z")
    assert float(np.linalg.norm(action)) > 0.1
    assert data.qpos[model.jnt_qposadr[press_joint]] == np.float64(-0.014)


def test_manual_key_updates_state_without_exceeding_limits():
    state = ManualControlState(close=0.0, probe_z=0.0)

    for _ in range(20):
        state = handle_manual_key(state, "c")
    for _ in range(20):
        state = handle_manual_key(state, "d")

    assert state.close == 1.0
    assert MANUAL_PROBE_LIMITS[0] <= state.probe_z <= MANUAL_PROBE_LIMITS[1]


def test_hold_current_manual_target_stops_chasing_old_close_target():
    model = mujoco.MjModel.from_xml_path("assets/dexh13_mjcf/interactive_press_scene.xml")
    data = mujoco.MjData(model)
    first_flex_joint = FINGER_FLEXION_INDICES["index"][0]
    qposadr = int(model.jnt_qposadr[first_flex_joint])
    data.qpos[qposadr] = 0.3

    held = hold_current_manual_target(model, data, ManualControlState(close=1.0))

    assert held.close == current_close_fraction(model, data)
    assert held.close < 1.0


def test_live_viewer_headless_manual_mode_records_nonzero_action_and_probe_pose(tmp_path: Path):
    out_path = tmp_path / "manual_live.h5"
    subprocess.run(
        [
            sys.executable,
            "scripts/view_tactile_live.py",
            "--headless",
            "--mjcf",
            "assets/dexh13_mjcf/interactive_press_scene.xml",
            "--steps",
            "600",
            "--manual",
            "--no-object-control",
            "--manual-close",
            "0.4",
            "--manual-probe-z",
            "-0.014",
            "--record",
            str(out_path),
            "--objects",
            "press_probe",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    with h5py.File(out_path, "r") as h5:
        assert h5["metadata"].attrs["control_mode"] == "manual"
        assert float(np.linalg.norm(h5["state/action"][:])) > 1.0e-3
        assert h5["state/object_xpos"].shape[1:] == (1, 3)


def test_manual_probe_default_and_clamp_do_not_start_deep_inside_tip():
    model = mujoco.MjModel.from_xml_path("assets/dexh13_mjcf/interactive_press_scene.xml")
    data = mujoco.MjData(model)
    state = ManualControlState(close=0.0, probe_z=-0.026)

    apply_manual_control(model, data, state)
    mujoco.mj_step(model, data)

    press_joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "press_z")
    assert data.qpos[model.jnt_qposadr[press_joint]] >= MANUAL_PROBE_LIMITS[0] - 1.0e-5
    for contact_id in range(data.ncon):
        assert data.contact[contact_id].dist > -0.0015
    assert DEFAULT_PROBE_Z > MANUAL_PROBE_LIMITS[0]
