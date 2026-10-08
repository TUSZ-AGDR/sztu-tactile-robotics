#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from dexh13sim.calibration_fitting import load_calibration_samples_csv, write_calibration_samples


def parse_key_value(items: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"metadata item must use key=value format: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"metadata key is empty in {item}")
        parsed[key] = value
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert flat DexH13 tactile calibration CSV to HDF5 samples.")
    parser.add_argument("--input", type=Path, required=True, help="Flat calibration CSV.")
    parser.add_argument("--out", type=Path, required=True, help="Output calibration HDF5.")
    parser.add_argument("--total-taxels", type=int, default=1140)
    parser.add_argument(
        "--metadata",
        action="append",
        default=[],
        help="Metadata entry in key=value format. Can be repeated.",
    )
    args = parser.parse_args()

    samples = load_calibration_samples_csv(
        args.input,
        total_taxels=args.total_taxels,
        metadata=parse_key_value(args.metadata),
    )
    write_calibration_samples(args.out, samples)
    print(
        f"wrote {args.out} samples={len(samples.sensor_id)} "
        f"taxels={samples.observed_detail_N.shape[1]} source={args.input}"
    )


if __name__ == "__main__":
    main()
