#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import numpy as np

from dexh13sim.sensor_table import SENSOR_TABLE


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect a DexH13 tactile and pose HDF5 episode.")
    parser.add_argument("--input", type=Path, required=True)
    return parser.parse_args()


def metadata_value(h5: h5py.File, name: str, default: str = "unknown") -> str:
    if "metadata" not in h5:
        return default
    return str(h5["metadata"].attrs.get(name, default))


def peak_sensor_name(taxel_id: int) -> str:
    for spec in SENSOR_TABLE:
        if spec.start <= taxel_id < spec.end:
            return f"{spec.sdk_name}/{spec.name}"
    return "unknown"


def max_range(values: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    return float(np.ptp(values, axis=0).max())


def main() -> None:
    args = parse_args()
    with h5py.File(args.input, "r") as h5:
        time = h5["time"][:]
        raw = h5["tactile/raw_sensor_N"][:]
        contact_count = h5["state/contact_count"][:] if "state/contact_count" in h5 else np.zeros(len(time))
        action = h5["state/action"][:] if "state/action" in h5 else np.zeros((len(time), 16))
        qpos = h5["qpos"][:] if "qpos" in h5 else np.zeros((len(time), 16))
        object_count = h5["state/object_xpos"].shape[1] if "state/object_xpos" in h5 else 0

        magnitudes = np.linalg.norm(raw, axis=2) if raw.size else np.zeros((len(time), 1140))
        frame_sum = magnitudes.sum(axis=1) if magnitudes.size else np.zeros(len(time))
        peak_frame = int(frame_sum.argmax()) if len(frame_sum) else 0
        peak_taxel = int(magnitudes[peak_frame].argmax()) if len(frame_sum) else -1
        peak_total = float(frame_sum[peak_frame]) if len(frame_sum) else 0.0

        duration = float(time[-1] - time[0]) if len(time) > 1 else 0.0
        policy = metadata_value(h5, "policy")
        tactile_hz = metadata_value(h5, "tactile_hz")
        object_names = metadata_value(h5, "object_names", "")

    print(
        f"episode={args.input} frames={len(time)} duration={duration:.3f}s "
        f"tactile_hz={tactile_hz} policy={policy}"
    )
    print(
        f"contact_frames={int(np.count_nonzero(contact_count > 0))} "
        f"max_contact_count={int(contact_count.max()) if len(contact_count) else 0} "
        f"peak_frame={peak_frame} peak_sensor={peak_sensor_name(peak_taxel)} "
        f"peak_taxel={peak_taxel} peak_total_N={peak_total:.6f}"
    )
    print(
        f"action_range={max_range(action):.6f} qpos_range={max_range(qpos):.6f} "
        f"objects={object_count} object_names={object_names}"
    )


if __name__ == "__main__":
    main()
