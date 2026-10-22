"""Create a small synthetic HDF5 file for trying the CLI."""

from pathlib import Path
import sys

import numpy as np


def main() -> None:
    import h5py

    output = Path(sys.argv[1] if len(sys.argv) > 1 else "demo_tactile.h5")
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
    print(output)


if __name__ == "__main__":
    main()
