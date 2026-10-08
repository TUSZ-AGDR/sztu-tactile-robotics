from pathlib import Path

import h5py
import numpy as np

from dexh13sim.dataset_writer import DatasetWriter


def test_dataset_writer_persists_tactile_frames_and_metadata(tmp_path: Path):
    out_path = tmp_path / "episode.h5"
    with DatasetWriter(out_path, metadata={"sim_dt": 0.0005, "tactile_hz": 10}) as writer:
        writer.append(
            time_s=0.1,
            detail_N=np.ones((1140, 3), dtype=np.float32),
            detail_sdk=np.ones((1140, 3), dtype=np.float32) * 10,
            raw_sensor_N=np.ones((1140, 3), dtype=np.float32) * 2,
            qpos=np.arange(16, dtype=np.float32),
            qvel=np.arange(16, dtype=np.float32) * 0.1,
            action=np.ones(16, dtype=np.float32),
            sensor_frame_xpos=np.ones((11, 3), dtype=np.float32),
            sensor_frame_xquat=np.tile(np.array([1, 0, 0, 0], dtype=np.float32), (11, 1)),
            object_xpos=np.ones((1, 3), dtype=np.float32),
            object_xquat=np.array([[1, 0, 0, 0]], dtype=np.float32),
            object_cvel=np.ones((1, 6), dtype=np.float32),
            contact_count=2,
        )

    with h5py.File(out_path, "r") as h5:
        assert h5["tactile/detail_N"].shape == (1, 1140, 3)
        assert h5["tactile/detail_sdk"].dtype == np.dtype("float32")
        assert h5["tactile/raw_sensor_N"][0, 0, 0] == 2.0
        assert h5["time"][0] == np.float32(0.1)
        assert h5["qpos"].shape == (1, 16)
        assert h5["state/qvel"].shape == (1, 16)
        assert h5["state/action"][0, 0] == 1.0
        assert h5["state/sensor_frame_xpos"].shape == (1, 11, 3)
        assert h5["state/object_xpos"].shape == (1, 1, 3)
        assert h5["state/contact_count"][0] == 2
        assert h5["metadata"].attrs["tactile_hz"] == 10
