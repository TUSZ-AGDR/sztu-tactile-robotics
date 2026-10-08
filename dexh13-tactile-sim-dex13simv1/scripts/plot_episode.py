#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from dexh13sim.sensor_table import SENSOR_TABLE


DATASETS = {
    "raw": "tactile/raw_sensor_N",
    "detail": "tactile/detail_N",
    "sdk": "tactile/detail_sdk",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot DexH13 tactile episode summaries.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=sorted(DATASETS), default="raw")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = DATASETS[args.mode]
    with h5py.File(args.input, "r") as h5:
        values = h5[dataset][:]
        time = h5["time"][:]

    magnitudes = np.linalg.norm(values, axis=2)
    frame_sum = magnitudes.sum(axis=1)
    peak_frame = int(frame_sum.argmax()) if len(frame_sum) else 0
    sensor_sums = np.asarray(
        [magnitudes[:, spec.start:spec.end].sum(axis=1) for spec in SENSOR_TABLE],
        dtype=np.float64,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(12, 7), dpi=150)
    grid = fig.add_gridspec(2, 2, height_ratios=[1, 1.1])

    ax0 = fig.add_subplot(grid[0, 0])
    ax0.plot(time, frame_sum, color="#1f77b4", linewidth=2)
    if len(time):
        ax0.axvline(time[peak_frame], color="#d62728", linewidth=1.2, alpha=0.8)
    ax0.set_title(f"{args.mode} tactile response")
    ax0.set_xlabel("time (s)")
    ax0.set_ylabel(f"sum |{args.mode}|")
    ax0.grid(True, alpha=0.25)

    ax1 = fig.add_subplot(grid[0, 1])
    labels = [spec.sdk_name for spec in SENSOR_TABLE]
    ax1.bar(labels, sensor_sums[:, peak_frame] if len(time) else np.zeros(len(labels)), color="#2ca02c")
    ax1.set_title(f"sensor response at peak frame {peak_frame}")
    ax1.set_ylabel(f"sum |{args.mode}|")
    ax1.tick_params(axis="x", rotation=45)

    ax2 = fig.add_subplot(grid[1, :])
    ax2.plot(magnitudes[peak_frame] if len(time) else np.zeros(1140), color="#d62728", linewidth=1.2)
    for spec in SENSOR_TABLE:
        ax2.axvline(spec.start, color="k", alpha=0.08, linewidth=0.8)
    ax2.set_title("peak frame taxel magnitude, 1140 taxels")
    ax2.set_xlabel("taxel index in SDK layout")
    ax2.set_ylabel(f"|{args.mode}|")
    ax2.grid(True, alpha=0.2)

    fig.tight_layout()
    fig.savefig(args.out)
    print(f"wrote {args.out} peak_frame={peak_frame} peak_sum={float(frame_sum[peak_frame]) if len(frame_sum) else 0.0:.6f}")


if __name__ == "__main__":
    main()
