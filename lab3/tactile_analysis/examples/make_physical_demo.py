"""Create a four-taxel SYNTHETIC example; its calibration cannot process real data."""

from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tactile_analysis.terminal import ChineseArgumentParser, error_text


def make_demo(directory):
    import h5py

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    trial_path, calibration_path = directory / "synthetic_trial.h5", directory / "synthetic_calibration.npz"
    if trial_path.exists() or calibration_path.exists():
        raise FileExistsError("示例文件已存在，请选择新的输出目录")
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


def main(argv=None):
    parser = ChineseArgumentParser(description="生成四点、三帧的面积与压力合成示例；示例标定不能用于真实数据。")
    parser.add_argument("output_dir", type=Path, help="示例输入文件的保存目录")
    args = parser.parse_args(argv)
    try:
        trial, calibration = make_demo(args.output_dir)
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(1, f"生成示例失败：{error_text(exc)}\n")
    print(f"合成触觉数据已生成：{trial}")
    print(f"合成标定文件已生成：{calibration}")
    print("这组文件仅用于算术练习，不能作为真实硬件的标定结果。")


if __name__ == "__main__":
    main()
