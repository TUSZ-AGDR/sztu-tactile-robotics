from __future__ import annotations

from pathlib import Path
from typing import Any

import h5py
import numpy as np


class DatasetWriter:
    def __init__(self, path: str | Path, metadata: dict[str, Any] | None = None):
        self.path = Path(path)
        self.metadata = metadata or {}
        self.h5: h5py.File | None = None
        self._count = 0

    def __enter__(self) -> "DatasetWriter":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.h5 = h5py.File(self.path, "w")
        tactile = self.h5.create_group("tactile")
        tactile.create_dataset("detail_N", shape=(0, 1140, 3), maxshape=(None, 1140, 3), dtype="float32")
        tactile.create_dataset("detail_sdk", shape=(0, 1140, 3), maxshape=(None, 1140, 3), dtype="float32")
        tactile.create_dataset("raw_sensor_N", shape=(0, 1140, 3), maxshape=(None, 1140, 3), dtype="float32")
        self.h5.create_dataset("time", shape=(0,), maxshape=(None,), dtype="float32")
        self.h5.create_dataset("qpos", shape=(0, 16), maxshape=(None, 16), dtype="float32")

        state = self.h5.create_group("state")
        state.create_dataset("qvel", shape=(0, 16), maxshape=(None, 16), dtype="float32")
        state.create_dataset("action", shape=(0, 16), maxshape=(None, 16), dtype="float32")
        state.create_dataset("sensor_frame_xpos", shape=(0, 11, 3), maxshape=(None, 11, 3), dtype="float32")
        state.create_dataset("sensor_frame_xquat", shape=(0, 11, 4), maxshape=(None, 11, 4), dtype="float32")
        state.create_dataset("object_xpos", shape=(0, 0, 3), maxshape=(None, None, 3), dtype="float32")
        state.create_dataset("object_xquat", shape=(0, 0, 4), maxshape=(None, None, 4), dtype="float32")
        state.create_dataset("object_cvel", shape=(0, 0, 6), maxshape=(None, None, 6), dtype="float32")
        state.create_dataset("contact_count", shape=(0,), maxshape=(None,), dtype="int32")

        meta = self.h5.create_group("metadata")
        for key, value in self.metadata.items():
            meta.attrs[key] = value
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.h5 is not None:
            self.h5.close()
            self.h5 = None

    def append(
        self,
        time_s: float,
        detail_N: np.ndarray,
        detail_sdk: np.ndarray,
        raw_sensor_N: np.ndarray,
        qpos: np.ndarray,
        qvel: np.ndarray | None = None,
        action: np.ndarray | None = None,
        sensor_frame_xpos: np.ndarray | None = None,
        sensor_frame_xquat: np.ndarray | None = None,
        object_xpos: np.ndarray | None = None,
        object_xquat: np.ndarray | None = None,
        object_cvel: np.ndarray | None = None,
        contact_count: int = 0,
    ) -> None:
        if self.h5 is None:
            raise RuntimeError("DatasetWriter must be used as a context manager")

        idx = self._count
        for name in ("detail_N", "detail_sdk", "raw_sensor_N"):
            self.h5[f"tactile/{name}"].resize(idx + 1, axis=0)
        self.h5["time"].resize(idx + 1, axis=0)
        self.h5["qpos"].resize(idx + 1, axis=0)
        for name in ("qvel", "action", "sensor_frame_xpos", "sensor_frame_xquat", "contact_count"):
            self.h5[f"state/{name}"].resize(idx + 1, axis=0)

        object_xpos = empty_object_array(3) if object_xpos is None else np.asarray(object_xpos, dtype=np.float32)
        object_xquat = empty_object_array(4) if object_xquat is None else np.asarray(object_xquat, dtype=np.float32)
        object_cvel = empty_object_array(6) if object_cvel is None else np.asarray(object_cvel, dtype=np.float32)
        self._ensure_object_capacity(object_xpos.shape[0])
        for name in ("object_xpos", "object_xquat", "object_cvel"):
            self.h5[f"state/{name}"].resize(idx + 1, axis=0)

        self.h5["tactile/detail_N"][idx] = np.asarray(detail_N, dtype=np.float32)
        self.h5["tactile/detail_sdk"][idx] = np.asarray(detail_sdk, dtype=np.float32)
        self.h5["tactile/raw_sensor_N"][idx] = np.asarray(raw_sensor_N, dtype=np.float32)
        self.h5["time"][idx] = np.float32(time_s)
        self.h5["qpos"][idx] = np.asarray(qpos, dtype=np.float32)
        self.h5["state/qvel"][idx] = default_array(qvel, (16,))
        self.h5["state/action"][idx] = default_array(action, (16,))
        self.h5["state/sensor_frame_xpos"][idx] = default_array(sensor_frame_xpos, (11, 3))
        self.h5["state/sensor_frame_xquat"][idx] = default_sensor_quat(sensor_frame_xquat)
        self.h5["state/contact_count"][idx] = np.int32(contact_count)

        object_count = object_xpos.shape[0]
        self.h5["state/object_xpos"][idx, :object_count] = object_xpos
        self.h5["state/object_xquat"][idx, :object_count] = object_xquat
        self.h5["state/object_cvel"][idx, :object_count] = object_cvel
        self._count += 1

    def _ensure_object_capacity(self, object_count: int) -> None:
        assert self.h5 is not None
        for name, width in (("object_xpos", 3), ("object_xquat", 4), ("object_cvel", 6)):
            ds = self.h5[f"state/{name}"]
            if ds.shape[1] < object_count:
                ds.resize(object_count, axis=1)


def default_array(value: np.ndarray | None, shape: tuple[int, ...]) -> np.ndarray:
    if value is None:
        return np.zeros(shape, dtype=np.float32)
    return np.asarray(value, dtype=np.float32)


def default_sensor_quat(value: np.ndarray | None) -> np.ndarray:
    if value is None:
        return np.tile(np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32), (11, 1))
    return np.asarray(value, dtype=np.float32)


def empty_object_array(width: int) -> np.ndarray:
    return np.zeros((0, width), dtype=np.float32)
