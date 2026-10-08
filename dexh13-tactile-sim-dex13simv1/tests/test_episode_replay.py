from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from dexh13sim.episode_validation import validate_episode


def test_episode_validation_accepts_recorded_free_object_episode(tmp_path: Path):
    out_path = tmp_path / "free_object_episode.h5"
    subprocess.run(
        [
            sys.executable,
            "scripts/view_tactile_live.py",
            "--headless",
            "--mjcf",
            "assets/dexh13_mjcf/free_object_scene.xml",
            "--steps",
            "400",
            "--object-control",
            "--record",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    report = validate_episode(out_path)

    assert report.frames == 2
    assert report.taxels == 1140
    assert report.objects == 1


def test_replay_episode_headless_steps_through_saved_frames(tmp_path: Path):
    out_path = tmp_path / "free_object_episode.h5"
    subprocess.run(
        [
            sys.executable,
            "scripts/view_tactile_live.py",
            "--headless",
            "--mjcf",
            "assets/dexh13_mjcf/free_object_scene.xml",
            "--steps",
            "400",
            "--object-control",
            "--record",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/replay_episode.py",
            "--headless",
            "--input",
            str(out_path),
            "--mjcf",
            "assets/dexh13_mjcf/free_object_scene.xml",
            "--max-frames",
            "2",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "replayed frames=2" in result.stdout
