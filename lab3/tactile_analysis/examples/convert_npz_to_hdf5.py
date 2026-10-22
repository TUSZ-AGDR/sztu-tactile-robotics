"""Convert one current DexH13 NPZ trial into the analysis HDF5 layout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tactile_analysis.io import load_npz


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("npz", type=Path)
    parser.add_argument("hdf5", type=Path)
    parser.add_argument("--metadata-json", type=Path)
    args = parser.parse_args()
    try:
        import h5py
    except ImportError as exc:
        raise SystemExit("Install tactile-hdf5-analysis[hdf5] to convert files") from exc
    trial = load_npz(args.npz)
    metadata = {}
    if args.metadata_json:
        metadata = json.loads(args.metadata_json.read_text(encoding="utf-8"))
    with h5py.File(args.hdf5, "w") as handle:
        handle.create_dataset("detail_xyz", data=trial.detail_xyz)
        if trial.sensor_forces is not None:
            handle.create_dataset("sensor_forces", data=trial.sensor_forces)
        if trial.temperature is not None:
            handle.create_dataset("temperature", data=trial.temperature)
        if trial.timestamps_ns is not None:
            handle.create_dataset("tactile_timestamps_ns", data=trial.timestamps_ns)
        if trial.joint_radians is not None:
            handle.create_dataset("joint_radians", data=trial.joint_radians)
        for name in ("taxel_valid_mask", "packet_valid", "sample_valid", "query_begin_ns"):
            value = getattr(trial, name)
            if value is not None:
                handle.create_dataset(name, data=value)
        if trial.hand_side is not None:
            handle.create_dataset("hand_side", data=trial.hand_side.astype(object), dtype=h5py.string_dtype("utf-8"))
        for key, value in metadata.get("session_meta", metadata).items():
            if isinstance(value, (str, int, float, bool)):
                handle.attrs[key] = value
    print(args.hdf5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
