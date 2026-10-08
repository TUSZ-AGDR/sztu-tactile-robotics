from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import h5py
import numpy as np
import yaml


def test_collect_episode_writes_synchronized_state_schema(tmp_path: Path):
    out_path = tmp_path / "episode.h5"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/collect_episode.py",
            "--steps",
            "1000",
            "--out",
            str(out_path),
            "--objects",
            "press_probe",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "frames=5" in result.stdout
    with h5py.File(out_path, "r") as h5:
        assert h5["tactile/raw_sensor_N"].shape == (5, 1140, 3)
        assert h5["qpos"].shape == (5, 16)
        assert h5["state/qvel"].shape == (5, 16)
        assert h5["state/action"].shape == (5, 16)
        assert h5["state/sensor_frame_xpos"].shape == (5, 11, 3)
        assert h5["state/sensor_frame_xquat"].shape == (5, 11, 4)
        assert h5["state/object_xpos"].shape == (5, 1, 3)
        assert h5["state/object_xquat"].shape == (5, 1, 4)
        assert h5["state/object_cvel"].shape == (5, 1, 6)
        assert h5["state/contact_count"].shape == (5,)
        assert h5["metadata"].attrs["object_names"] == "press_probe"
        assert np.count_nonzero(h5["state/contact_count"][:] > 0) >= 3
        assert np.linalg.norm(h5["state/sensor_frame_xpos"][:]) > 0


def test_collect_episode_records_scripted_hand_policy(tmp_path: Path):
    out_path = tmp_path / "policy_episode.h5"
    subprocess.run(
        [
            sys.executable,
            "scripts/collect_episode.py",
            "--steps",
            "2000",
            "--policy",
            "sine_close",
            "--policy-amplitude",
            "0.5",
            "--policy-period",
            "1.0",
            "--out",
            str(out_path),
            "--objects",
            "press_probe",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    with h5py.File(out_path, "r") as h5:
        action = h5["state/action"][:]
        qpos = h5["qpos"][:]
        assert h5["metadata"].attrs["policy"] == "sine_close"
        assert float(np.ptp(action, axis=0).max()) > 1.0e-2
        assert float(np.ptp(qpos, axis=0).max()) > 1.0e-4


def test_collect_episode_accepts_custom_calibration_path(tmp_path: Path):
    calibration = yaml.safe_load(Path("configs/calibration.yaml").read_text(encoding="utf-8"))
    calibration["global"]["tactile_hz"] = 20
    calibration_path = tmp_path / "calibration_20hz.yaml"
    calibration_path.write_text(yaml.safe_dump(calibration, sort_keys=False), encoding="utf-8")
    out_path = tmp_path / "custom_calibration_episode.h5"

    subprocess.run(
        [
            sys.executable,
            "scripts/collect_episode.py",
            "--steps",
            "200",
            "--calibration",
            str(calibration_path),
            "--out",
            str(out_path),
            "--objects",
            "press_probe",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    with h5py.File(out_path, "r") as h5:
        assert h5["time"].shape == (2,)
        assert h5["metadata"].attrs["tactile_hz"] == 20
        assert h5["metadata"].attrs["calibration_path"] == str(calibration_path)


def test_live_record_uses_synchronized_state_schema(tmp_path: Path):
    out_path = tmp_path / "live.h5"
    subprocess.run(
        [
            sys.executable,
            "scripts/view_tactile_live.py",
            "--headless",
            "--mjcf",
            "assets/dexh13_mjcf/interactive_press_scene.xml",
            "--steps",
            "600",
            "--no-manual",
            "--no-object-control",
            "--policy",
            "index_tap",
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
        assert h5["state/qvel"].shape[0] == h5["tactile/raw_sensor_N"].shape[0]
        assert h5["state/object_xpos"].shape[1:] == (1, 3)
        assert h5["metadata"].attrs["object_names"] == "press_probe"
        assert h5["metadata"].attrs["policy"] == "index_tap"
        assert float(np.linalg.norm(h5["state/action"][:])) > 1.0e-3
