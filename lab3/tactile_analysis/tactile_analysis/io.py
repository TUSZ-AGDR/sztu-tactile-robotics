"""Input adapters for HDF5 and NumPy trial files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class TactileTrial:
    """Canonical in-memory representation of one tactile trial."""

    detail_xyz: np.ndarray
    sensor_forces: np.ndarray | None = None
    temperature: np.ndarray | None = None
    timestamps_ns: np.ndarray | None = None
    joint_radians: np.ndarray | None = None
    taxel_positions: np.ndarray | None = None
    taxel_area_mm2: float | np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    taxel_valid_mask: np.ndarray | None = None
    packet_valid: np.ndarray | None = None
    sample_valid: np.ndarray | None = None
    query_begin_ns: np.ndarray | None = None
    hand_side: np.ndarray | None = None

    def __post_init__(self) -> None:
        self.detail_xyz = np.asarray(self.detail_xyz, dtype=np.float64)
        if self.detail_xyz.ndim != 3 or self.detail_xyz.shape[2] != 3:
            raise ValueError("detail_xyz 的形状必须为 [T,N,3]")
        if not np.isfinite(self.detail_xyz).all():
            raise ValueError("detail_xyz 包含 NaN 或 Inf")
        frames = self.detail_xyz.shape[0]
        for name, shape in (("taxel_valid_mask", (frames, self.n_taxels)),
                            ("packet_valid", (frames,)), ("sample_valid", (frames,))):
            value = getattr(self, name)
            if value is not None:
                value = np.asarray(value)
                if value.dtype != np.dtype(bool) or value.shape != shape:
                    raise ValueError(f"{name} 必须为形状为 {shape} 的布尔数组")
                setattr(self, name, value)
        if all(v is not None for v in (self.taxel_valid_mask, self.packet_valid, self.sample_valid)):
            expected = self.packet_valid & self.taxel_valid_mask.any(axis=1)
            if not np.array_equal(expected, self.sample_valid):
                raise ValueError("sample_valid 与 packet_valid、taxel_valid_mask 不一致")
        if self.hand_side is not None:
            self.hand_side = np.asarray(self.hand_side, dtype="U")
            if self.hand_side.shape != (frames,) or not np.isin(self.hand_side, ["left", "right"]).all():
                raise ValueError("hand_side 必须由 left/right 组成，长度为 T")
        for name in ("sensor_forces", "temperature", "joint_radians"):
            value = getattr(self, name)
            if value is not None:
                value = np.asarray(value, dtype=np.float64)
                if value.shape[0] != frames:
                    raise ValueError(f"{name} 的帧数必须与 detail_xyz 相同")
                if not np.isfinite(value).all():
                    raise ValueError(f"{name} 包含 NaN 或 Inf")
                setattr(self, name, value)
        if self.timestamps_ns is not None:
            self.timestamps_ns = np.asarray(self.timestamps_ns, dtype=np.int64).reshape(-1)
            if self.timestamps_ns.size != frames:
                raise ValueError("timestamps_ns 的长度必须为 T")
            if frames > 1 and not np.all(np.diff(self.timestamps_ns) > 0):
                raise ValueError("timestamps_ns 必须严格递增")
        if self.query_begin_ns is not None:
            self.query_begin_ns = np.asarray(self.query_begin_ns)
            if self.query_begin_ns.dtype != np.dtype("int64") or self.query_begin_ns.shape != (frames,):
                raise ValueError("query_begin_ns 必须为长度为 T 的 int64 数组")
            if np.any(self.query_begin_ns < 0) or (self.timestamps_ns is not None and np.any(self.query_begin_ns > self.timestamps_ns)):
                raise ValueError("query_begin_ns 不能为负数，也不能晚于 timestamps_ns")
        if self.taxel_positions is not None:
            self.taxel_positions = np.asarray(self.taxel_positions, dtype=np.float64)
            if self.taxel_positions.ndim != 2 or self.taxel_positions.shape[0] != self.n_taxels:
                raise ValueError("taxel_positions 的形状必须为 [N,2] 或 [N,3]")
            if self.taxel_positions.shape[1] not in (2, 3):
                raise ValueError("taxel_positions 必须包含二维或三维坐标")
            if not np.isfinite(self.taxel_positions).all():
                raise ValueError("taxel_positions 包含 NaN 或 Inf")
        if self.taxel_area_mm2 is not None:
            area = np.asarray(self.taxel_area_mm2, dtype=np.float64)
            if not np.isfinite(area).all():
                raise ValueError("taxel_area_mm2 必须为有限数值")
            if area.ndim == 0:
                if float(area) <= 0:
                    raise ValueError("taxel_area_mm2 必须为正数")
            elif area.shape != (self.n_taxels,) or np.any(area <= 0):
                raise ValueError("taxel_area_mm2 必须为正标量或长度为 N 的正数数组")
            self.taxel_area_mm2 = float(area) if area.ndim == 0 else area

    @property
    def n_frames(self) -> int:
        return int(self.detail_xyz.shape[0])

    @property
    def n_taxels(self) -> int:
        return int(self.detail_xyz.shape[1])


_ALIASES: dict[str, tuple[str, ...]] = {
    "detail_xyz": ("detail_xyz", "taxel_raw", "tactile/detail_xyz", "tactile/taxel_force_vectors", "taxel_force_vectors", "detail"),
    "sensor_forces": ("sensor_forces", "sensor_summary_raw", "tactile/sensor_forces", "forces", "sensor_force"),
    "temperature": ("temperature", "tactile/temperature", "temperatures"),
    "timestamps_ns": ("tactile_timestamps_ns", "timestamp_ns", "timestamps_ns", "timestamps", "time/tactile_timestamps_ns"),
    "joint_radians": ("joint_radians", "joints/positions", "joint_positions"),
    "taxel_positions": ("taxel_positions", "calibration/taxel_positions", "layout/taxel_positions"),
    "taxel_area_mm2": ("taxel_area_mm2", "calibration/taxel_area_mm2", "layout/taxel_area_mm2"),
    "taxel_valid_mask": ("taxel_valid_mask",),
    "packet_valid": ("packet_valid",),
    "sample_valid": ("sample_valid",),
    "query_begin_ns": ("query_begin_ns",),
    "hand_side": ("hand_side",),
}


def _read_h5_value(root: Any, names: tuple[str, ...]) -> Any | None:
    for name in names:
        if name in root:
            obj = root[name]
            if hasattr(obj, "shape"):
                return obj.asstr()[()] if obj.dtype.kind == "O" and hasattr(obj, "asstr") else obj[()]
    return None


def _select_group(handle: Any, trial: str | None) -> Any:
    if trial:
        for path in (trial, f"trials/{trial}"):
            if path in handle:
                return handle[path]
        raise KeyError(f"未找到数据组：{trial}")
    if "trials" in handle:
        trials = handle["trials"]
        keys = list(trials.keys())
        if len(keys) != 1:
            raise ValueError("HDF5 包含多个数据组；请传入 trial=... 指定数据组")
        return trials[keys[0]]
    return handle


def load_hdf5(path: str | Path, trial: str | None = None) -> TactileTrial:
    """Load one trial from an HDF5 file using flexible dataset aliases."""
    try:
        import h5py
    except ImportError as exc:  # pragma: no cover - depends on optional package
        raise ImportError("读取 HDF5 需要 h5py；请安装 tactile-hdf5-analysis[hdf5]") from exc
    with h5py.File(path, "r") as handle:
        root = _select_group(handle, trial)
        values = {key: _read_h5_value(root, aliases) for key, aliases in _ALIASES.items()}
        if values["detail_xyz"] is None:
            raise KeyError("缺少必需的 HDF5 数据集：detail_xyz")
        metadata = {str(k): v.item() if hasattr(v, "item") else v for k, v in root.attrs.items()}
        return TactileTrial(**values, metadata=metadata)


def load_npz(path: str | Path) -> TactileTrial:
    """Load the current collector's NPZ-compatible arrays for local validation."""
    with np.load(path, allow_pickle=False) as data:
        values = {key: next((data[name] for name in names if name in data), None)
                  for key, names in _ALIASES.items()}
        if values["detail_xyz"] is None:
            raise KeyError("缺少必需的 NPZ 数组：detail_xyz")
        return TactileTrial(**values)
