from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import h5py
import mujoco
import numpy as np

from dexh13sim.sensor_table import SENSOR_TABLE
from scripts.view_tactile_live import ViewerKeyQueue, keycode_to_control_key, parse_args, set_drag_target_visibility


def test_live_viewer_headless_records_sustained_raw_contact(tmp_path: Path):
    out_path = tmp_path / "interactive_live.h5"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/view_tactile_live.py",
            "--headless",
            "--mjcf",
            "assets/dexh13_mjcf/interactive_press_scene.xml",
            "--steps",
            "1600",
            "--no-manual",
            "--no-object-control",
            "--print-every",
            "2",
            "--record",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "record=on" in result.stdout
    assert "peak=sensor3/index_tip" in result.stdout
    with h5py.File(out_path, "r") as h5:
        raw = h5["tactile/raw_sensor_N"][:]
        assert h5["metadata"].attrs["sensor_native_hz"] == 80
        assert h5["metadata"].attrs["tactile_hz"] == 10
        assert h5["metadata"].attrs["tactile_hz_source"] == "sdk_observed_1140_taxels"
        assert raw.shape[1:] == (1140, 3)
        raw_sum = np.linalg.norm(raw, axis=2).sum(axis=1)
        assert int(np.count_nonzero(raw_sum > 1.0e-8)) >= 3

        peak_taxel = int(np.linalg.norm(raw, axis=2).max(axis=0).argmax())
        peak_sensor = next(spec for spec in SENSOR_TABLE if spec.start <= peak_taxel < spec.end)
        assert peak_sensor.sdk_name == "sensor3"


def test_live_viewer_headless_default_does_not_record(tmp_path: Path):
    before = set(tmp_path.iterdir())
    result = subprocess.run(
        [
            sys.executable,
            "scripts/view_tactile_live.py",
            "--headless",
            "--steps",
            "400",
            "--print-every",
            "1",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "record=off" in result.stdout
    assert set(tmp_path.iterdir()) == before


def test_live_viewer_headless_object_control_records_free_object(tmp_path: Path):
    out_path = tmp_path / "free_object_live.h5"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/view_tactile_live.py",
            "--headless",
            "--steps",
            "400",
            "--record",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "control_mode=manual+object" in result.stdout
    with h5py.File(out_path, "r") as h5:
        assert h5["metadata"].attrs["object_names"] == "free_sphere"
        assert h5["metadata"].attrs["manual_mode"] == "jog"
        assert h5["metadata"].attrs["object_control_mode"] == "physical_drag"
        assert h5["state/object_xpos"].shape[1:] == (1, 3)
        assert np.isfinite(h5["state/object_xpos"][:]).all()


def test_drag_target_visibility_is_hidden_by_default_helper():
    model = mujoco.MjModel.from_xml_path("assets/dexh13_mjcf/free_object_scene.xml")
    geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "free_sphere_target_geom")

    assert set_drag_target_visibility(model, visible=False)
    assert float(model.geom_rgba[geom_id, 3]) == 0.0
    assert set_drag_target_visibility(model, visible=True)
    assert float(model.geom_rgba[geom_id, 3]) > 0.0


def test_viewer_key_queue_maps_mujoco_viewer_keys_to_existing_controls():
    queue = ViewerKeyQueue()

    assert keycode_to_control_key(ord("H")) == "h"
    assert keycode_to_control_key(ord("C")) == "c"
    assert keycode_to_control_key(256) == ""

    queue.callback(ord("H"))
    queue.callback(ord("C"))

    assert queue.read_keys() == ["h", "c"]
    assert queue.read_keys() == []


def test_live_viewer_parse_args_accepts_custom_calibration():
    args = parse_args(["--headless", "--calibration", "configs/calibration.fitted.yaml"])

    assert str(args.calibration) == "configs/calibration.fitted.yaml"


def test_live_viewer_interactive_defaults_keep_target_hidden_and_keyboard_visible():
    args = parse_args([])

    assert args.show_drag_target is False
    assert args.preselect_drag_target is True
    assert args.object_step == 0.004
    assert args.object_hold_timeout == 0.20


def test_live_viewer_can_disable_default_mouse_preselection():
    args = parse_args(["--no-preselect-drag-target"])

    assert args.preselect_drag_target is False


def test_plot_episode_writes_png(tmp_path: Path):
    h5_path = tmp_path / "interactive_live.h5"
    png_path = tmp_path / "episode.png"
    subprocess.run(
        [
            sys.executable,
            "scripts/view_tactile_live.py",
            "--headless",
            "--mjcf",
            "assets/dexh13_mjcf/interactive_press_scene.xml",
            "--steps",
            "800",
            "--no-manual",
            "--no-object-control",
            "--record",
            str(h5_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/plot_episode.py",
            "--input",
            str(h5_path),
            "--out",
            str(png_path),
            "--mode",
            "raw",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert str(png_path) in result.stdout
    assert png_path.exists()
    assert png_path.stat().st_size > 1000
