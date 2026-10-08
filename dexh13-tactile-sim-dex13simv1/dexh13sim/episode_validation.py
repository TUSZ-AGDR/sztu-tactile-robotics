from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import h5py


@dataclass(frozen=True)
class EpisodeValidationReport:
    frames: int
    taxels: int
    objects: int


REQUIRED_DATASETS = (
    "time",
    "qpos",
    "tactile/detail_N",
    "tactile/detail_sdk",
    "tactile/raw_sensor_N",
    "state/qvel",
    "state/action",
    "state/sensor_frame_xpos",
    "state/sensor_frame_xquat",
    "state/object_xpos",
    "state/object_xquat",
    "state/object_cvel",
    "state/contact_count",
)


def validate_episode(path: str | Path) -> EpisodeValidationReport:
    with h5py.File(path, "r") as h5:
        for name in REQUIRED_DATASETS:
            if name not in h5:
                raise ValueError(f"missing dataset {name}")

        frames = int(h5["time"].shape[0])
        if frames <= 0:
            raise ValueError("episode contains no frames")
        for name in REQUIRED_DATASETS:
            if int(h5[name].shape[0]) != frames:
                raise ValueError(f"{name} frame count does not match time")

        if h5["qpos"].shape[1:] != (16,):
            raise ValueError("qpos must have shape (frames, 16)")
        if h5["tactile/raw_sensor_N"].shape[1:] != (1140, 3):
            raise ValueError("raw_sensor_N must have shape (frames, 1140, 3)")
        if h5["state/sensor_frame_xpos"].shape[1:] != (11, 3):
            raise ValueError("sensor_frame_xpos must have shape (frames, 11, 3)")
        if h5["state/sensor_frame_xquat"].shape[1:] != (11, 4):
            raise ValueError("sensor_frame_xquat must have shape (frames, 11, 4)")

        return EpisodeValidationReport(
            frames=frames,
            taxels=int(h5["tactile/raw_sensor_N"].shape[1]),
            objects=int(h5["state/object_xpos"].shape[1]),
        )
