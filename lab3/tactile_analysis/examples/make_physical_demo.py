"""Create a four-taxel SYNTHETIC example; its calibration cannot process real data."""

import argparse
from pathlib import Path

import h5py
import numpy as np


def make_demo(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    trial_path, calibration_path = directory / "synthetic_trial.h5", directory / "synthetic_calibration.npz"
    if trial_path.exists() or calibration_path.exists():
        raise FileExistsError("Demo files already exist; choose a new output directory")
    raw = np.zeros((3, 4, 3), dtype=np.int32)
    raw[1, 0] = [3, 0, 10]
    raw[1, 1, 2] = 20
    raw[1, 2, 2] = 1000
    raw[2, :, 2] = [20, 30, 1000, 10]
    verified = np.array([True, True, False, True])
    with h5py.File(trial_path, "w") as f:
        group = f.create_group("trials/left")
        group.create_dataset("taxel_raw", data=raw)
        group.create_dataset("timestamp_ns", data=np.array([0, 1_000_000_000, 2_000_000_000], dtype=np.int64))
        group.create_dataset("taxel_valid_mask", data=np.tile(verified, (3, 1)))
        group.create_dataset("packet_valid", data=np.ones(3, dtype=bool))
        group.create_dataset("sample_valid", data=np.ones(3, dtype=bool))
        group.create_dataset("hand_side", data=np.array(["left"] * 3, dtype=object), dtype=h5py.string_dtype())
        group.attrs["synthetic_demo"] = True
        group.attrs["hand_side"] = "left"
    np.savez_compressed(calibration_path, schema_version=np.array(1), hand_side=np.array("left"),
                        source_kind=np.array("synthetic_demo"), calibration_id=np.array("four-taxel-arithmetic-example"),
                        force_matrix_n_per_count=np.eye(3) * .1, bias_counts=np.zeros(3),
                        normal_vectors=np.array([0., 0., 1.]), taxel_area_mm2=np.array(2.),
                        verified_taxel_mask=verified)
    return trial_path, calibration_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    for path in make_demo(args.output_dir):
        print(path)


if __name__ == "__main__":
    main()
