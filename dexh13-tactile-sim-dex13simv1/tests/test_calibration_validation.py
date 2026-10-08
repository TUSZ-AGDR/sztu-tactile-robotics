from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from dexh13sim.calibration_validation import validate_calibration_assets


def test_calibration_validation_accepts_current_templates_and_sensor_matrices():
    report = validate_calibration_assets("configs/taxel_templates", "configs/sensors.yaml")

    assert report.template_count == 5
    assert report.sensor_count == 11
    assert report.total_taxels == 1140
    assert report.max_vendor_error_m is None


def test_calibration_validation_compares_vendor_template_directory(tmp_path: Path):
    vendor_dir = tmp_path / "vendor_templates"
    shutil.copytree("configs/taxel_templates", vendor_dir)

    report = validate_calibration_assets("configs/taxel_templates", "configs/sensors.yaml", vendor_dir)

    assert report.max_vendor_error_m == 0.0


def test_validate_calibration_script_reports_ok(tmp_path: Path):
    vendor_dir = tmp_path / "vendor_templates"
    shutil.copytree("configs/taxel_templates", vendor_dir)
    result = subprocess.run(
        [
            sys.executable,
            "scripts/validate_calibration.py",
            "--vendor-templates",
            str(vendor_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "templates=5" in result.stdout
    assert "sensors=11" in result.stdout
    assert "max_vendor_error_m=0.000000e+00" in result.stdout
