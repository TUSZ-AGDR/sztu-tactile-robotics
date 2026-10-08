#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from dexh13sim.calibration_fitting import (
    apply_fit_to_calibration,
    fit_rbf_parameters,
    load_calibration_samples,
    write_calibration_yaml,
)
from dexh13sim.runtime import load_templates
from dexh13sim.sensor_table import SENSOR_TABLE


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fit DexH13 tactile RBF and response calibration parameters from measured press samples."
    )
    parser.add_argument("--samples", type=Path, required=True, help="Calibration HDF5 file.")
    parser.add_argument("--calibration", type=Path, default=Path("configs/calibration.yaml"))
    parser.add_argument("--templates", type=Path, default=Path("configs/taxel_templates"))
    parser.add_argument("--out", type=Path, required=True, help="Output fitted calibration YAML.")
    parser.add_argument(
        "--sigma-t",
        type=float,
        nargs="+",
        default=[0.002, 0.003, 0.004, 0.005],
        help="Candidate tangential RBF sigmas in meters.",
    )
    parser.add_argument(
        "--sigma-n",
        type=float,
        nargs="+",
        default=[0.001, 0.0015, 0.002, 0.003],
        help="Candidate normal RBF sigmas in meters.",
    )
    parser.add_argument(
        "--fit-response",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Also fit template-level A_matrix and bias_N for force scale, direction, and offset.",
    )
    parser.add_argument(
        "--response-regularization",
        type=float,
        default=1.0e-8,
        help="Small ridge regularization for fitting A_matrix and bias_N.",
    )
    parser.add_argument(
        "--fit-axes",
        default="xyz",
        help="Observed axes used for fitting. Use z for normal-only, x or y for staged shear fits, or xyz for full fits.",
    )
    parser.add_argument(
        "--lock-rbf",
        action="store_true",
        help="Keep sigma_t0/sigma_n0 from --calibration and only fit response rows for the selected axes.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    calibration = yaml.safe_load(args.calibration.read_text(encoding="utf-8"))
    samples = load_calibration_samples(args.samples)
    templates = load_templates(args.templates)
    fits = fit_rbf_parameters(
        samples,
        SENSOR_TABLE,
        templates,
        calibration["templates"],
        candidate_sigma_t=args.sigma_t,
        candidate_sigma_n=args.sigma_n,
        fit_response=args.fit_response,
        response_regularization=args.response_regularization,
        fit_axes=args.fit_axes,
        lock_rbf=args.lock_rbf,
    )
    fitted = apply_fit_to_calibration(calibration, fits)
    write_calibration_yaml(args.out, fitted)
    for template_name in sorted(fits):
        result = fits[template_name]
        print(
            f"{template_name}: sigma_t0={result.sigma_t0:.6g} "
            f"sigma_n0={result.sigma_n0:.6g} mse={result.mse:.6e} "
            f"samples={result.samples} axes={''.join(result.fit_axes)} "
            f"response={'fit' if result.A_matrix is not None else 'unchanged'}"
        )
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
