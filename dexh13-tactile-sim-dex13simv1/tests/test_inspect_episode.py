from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_inspect_episode_reports_tactile_and_state_summary(tmp_path: Path):
    h5_path = tmp_path / "episode.h5"
    subprocess.run(
        [
            sys.executable,
            "scripts/collect_episode.py",
            "--steps",
            "1000",
            "--policy",
            "sine_close",
            "--policy-period",
            "1.0",
            "--out",
            str(h5_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/inspect_episode.py",
            "--input",
            str(h5_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "frames=5" in result.stdout
    assert "policy=sine_close" in result.stdout
    assert "peak_sensor=sensor3/index_tip" in result.stdout
    assert "action_range=" in result.stdout
    assert "qpos_range=" in result.stdout
