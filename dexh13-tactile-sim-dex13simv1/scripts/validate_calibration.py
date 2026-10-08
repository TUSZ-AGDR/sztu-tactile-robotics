#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from dexh13sim.calibration_validation import validate_calibration_assets


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate DexH13 taxel templates and sensor calibration metadata.")
    parser.add_argument("--templates", type=Path, default=Path("configs/taxel_templates"))
    parser.add_argument("--sensors", type=Path, default=Path("configs/sensors.yaml"))
    parser.add_argument("--vendor-templates", type=Path, default=None)
    args = parser.parse_args()

    report = validate_calibration_assets(args.templates, args.sensors, args.vendor_templates)
    vendor = "missing" if report.max_vendor_error_m is None else f"{report.max_vendor_error_m:.6e}"
    print(
        f"templates={report.template_count} sensors={report.sensor_count} "
        f"total_taxels={report.total_taxels} max_vendor_error_m={vendor}"
    )


if __name__ == "__main__":
    main()
