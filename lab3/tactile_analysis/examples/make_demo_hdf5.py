"""Create a small synthetic HDF5 file for trying the CLI."""

from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tactile_analysis.terminal import ChineseArgumentParser, error_text


def make_demo(output) -> None:
    import h5py

    rng = np.random.default_rng(7)
    t, n = 40, 24
    detail = rng.normal(0, 0.01, (t, n, 3))
    detail[12:30, 8:16] += 0.12
    positions = np.array([(x, y) for y in range(4) for x in range(6)], dtype=float)
    with h5py.File(output, "w") as h5:
        h5.create_dataset("detail_xyz", data=detail)
        h5.create_dataset("sensor_forces", data=rng.normal(0, 0.02, (t, 3, 3)))
        h5.create_dataset("temperature", data=np.full((t, 3), 26.0))
        h5.create_dataset("tactile_timestamps_ns", data=np.arange(t, dtype=np.int64) * 100_000_000)
        h5.create_dataset("taxel_positions", data=positions)
        h5.attrs["demo"] = True


def main(argv=None) -> None:
    parser = ChineseArgumentParser(description="生成用于试运行原始触觉分析的合成 HDF5 文件。")
    parser.add_argument("output", nargs="?", type=Path, default=Path("demo_tactile.h5"), help="输出文件（默认 demo_tactile.h5）")
    args = parser.parse_args(argv)
    try:
        make_demo(args.output)
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(1, f"生成示例失败：{error_text(exc)}\n")
    print(f"合成 HDF5 数据已生成：{args.output}")


if __name__ == "__main__":
    main()
