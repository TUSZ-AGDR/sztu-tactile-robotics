#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from dexh13sim.calibration_fitting import evaluate_rbf_fit, load_calibration_samples
from dexh13sim.runtime import load_templates
from dexh13sim.sensor_table import SENSOR_TABLE


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate DexH13 tactile RBF calibration against samples.")
    parser.add_argument("--samples", type=Path, required=True, help="Calibration HDF5 file.")
    parser.add_argument("--calibration", type=Path, default=Path("configs/calibration.yaml"))
    parser.add_argument("--templates", type=Path, default=Path("configs/taxel_templates"))
    parser.add_argument(
        "--axes",
        default="xyz",
        help="Observed axes used for metrics. Use z for normal-only evaluation, x/y for staged shear checks, or xyz.",
    )
    args = parser.parse_args()

    samples = load_calibration_samples(args.samples)
    calibration = yaml.safe_load(args.calibration.read_text(encoding="utf-8"))
    templates = load_templates(args.templates)
    report = evaluate_rbf_fit(samples, SENSOR_TABLE, templates, calibration["templates"], axes=args.axes)
    print(
        f"samples={report.samples} mse_N2={report.mse_N2:.6e} "
        f"rmse_N={report.rmse_N:.6e} mae_N={report.mae_N:.6e} "
        f"peak_taxel_accuracy={report.peak_taxel_accuracy:.6f}"
    )


if __name__ == "__main__":
    main()
