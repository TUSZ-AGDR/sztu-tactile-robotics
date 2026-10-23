"""Numerical tactile metrics with explicit calibration semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .io import TactileTrial


@dataclass(frozen=True)
class AnalysisConfig:
    contact_threshold: float = 10.0
    force_unit: str = "raw"
    taxel_area_mm2: float | None = None
    pressure_unit: str = "raw_per_mm2"
    smooth_window: int = 1
    allow_unverified: bool = False

    def __post_init__(self) -> None:
        if not np.isfinite(self.contact_threshold) or self.contact_threshold < 0:
            raise ValueError("contact_threshold 必须为有限且非负的数值")
        if self.taxel_area_mm2 is not None and (not np.isfinite(self.taxel_area_mm2) or self.taxel_area_mm2 <= 0):
            raise ValueError("taxel_area_mm2 必须为有限正数")
        if self.smooth_window < 1 or self.smooth_window % 2 == 0:
            raise ValueError("smooth_window 必须为正奇数")


@dataclass
class AnalysisResult:
    frame_metrics: dict[str, np.ndarray]
    taxel_force_norm: np.ndarray
    contact_mask: np.ndarray
    summary: dict[str, Any]
    taxel_positions: np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"summary": self.summary, "metadata": self.metadata}


def _moving_average(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return values
    pad = window // 2
    padded = np.pad(values, ((pad, pad), (0, 0)), mode="edge")
    kernel = np.ones(window, dtype=np.float64) / window
    return np.stack([np.convolve(padded[:, j], kernel, mode="valid") for j in range(values.shape[1])], axis=1)


def _time_seconds(trial: TactileTrial) -> tuple[np.ndarray, str]:
    if trial.timestamps_ns is None:
        return np.arange(trial.n_frames, dtype=np.float64), "frame_index"
    return (trial.timestamps_ns - trial.timestamps_ns[0]).astype(np.float64) / 1e9, "timestamps_ns"


def _trapz(values: np.ndarray, time_s: np.ndarray) -> float:
    if values.size <= 1:
        return 0.0
    # Keep a small local implementation so both NumPy 1.x and 2.x work;
    # the integration is intentionally one-dimensional here.
    return float(np.sum((values[:-1] + values[1:]) * np.diff(time_s) / 2.0))


def analyze_trial(trial: TactileTrial, config: AnalysisConfig | None = None) -> AnalysisResult:
    config = config or AnalysisConfig()
    quality = (trial.taxel_valid_mask, trial.packet_valid, trial.sample_valid)
    unverified = any(value is not None and not np.all(value) for value in quality)
    if unverified and not config.allow_unverified:
        raise ValueError("数据组包含无效或未验证的样本、触觉点。"
                         "仅在原始诊断时使用 allow_unverified=True（--allow-unverified）；"
                         "默认分析要求所有数据均通过有效性校验。")
    if unverified and (config.force_unit != "raw" or config.taxel_area_mm2 is not None or trial.taxel_area_mm2 is not None):
        raise ValueError("未验证的原始诊断要求 force_unit='raw'，且不能设置触觉点面积")
    time_s, time_source = _time_seconds(trial)
    taxel_force_norm = np.linalg.norm(trial.detail_xyz, axis=2)
    taxel_force_norm = _moving_average(taxel_force_norm, config.smooth_window)
    contact_mask = taxel_force_norm >= config.contact_threshold
    area = trial.taxel_area_mm2 if trial.taxel_area_mm2 is not None else config.taxel_area_mm2
    area_per_frame: np.ndarray | None
    if area is None:
        area_per_frame = None
    else:
        area_values = np.asarray(area, dtype=np.float64)
        active_area = contact_mask * (area_values if area_values.ndim else float(area_values))
        area_per_frame = np.sum(active_area, axis=1)
    total_force = np.sum(taxel_force_norm * contact_mask, axis=1)
    peak_force = np.max(taxel_force_norm, axis=1)
    active_count = np.sum(contact_mask, axis=1).astype(np.int32)
    mean_contact_force = np.divide(total_force, active_count, out=np.zeros_like(total_force), where=active_count > 0)
    metrics: dict[str, np.ndarray] = {
        "time_s": time_s,
        "active_taxel_count": active_count,
        "total_contact_force": total_force,
        "peak_taxel_force": peak_force,
        "mean_contact_force": mean_contact_force,
    }
    if area_per_frame is not None:
        metrics["contact_area_mm2"] = area_per_frame
        metrics["mean_pressure"] = np.divide(total_force, area_per_frame, out=np.zeros_like(total_force), where=area_per_frame > 0)
    if trial.sensor_forces is not None:
        sensor_norm = np.linalg.norm(trial.sensor_forces, axis=2)
        metrics["sensor_total_force"] = np.sum(sensor_norm, axis=1)
        metrics["sensor_peak_force"] = np.max(sensor_norm, axis=1)
    if trial.temperature is not None:
        metrics["temperature_mean"] = np.mean(trial.temperature, axis=1)
        metrics["temperature_max"] = np.max(trial.temperature, axis=1)
    if trial.joint_radians is not None:
        for joint_idx in range(trial.joint_radians.shape[1]):
            metrics[f"joint_{joint_idx:02d}_rad"] = trial.joint_radians[:, joint_idx]
    summary: dict[str, Any] = {
        "n_frames": trial.n_frames,
        "analysis_mode": "unverified_raw_diagnostic" if unverified else "standard",
        "metric_interpretation": "raw threshold exceedance; not verified contact" if unverified else "threshold-based metrics",
        "validity_policy": "allow_unverified" if config.allow_unverified else "require_complete_validity",
        "n_taxels": trial.n_taxels,
        "duration_s": float(time_s[-1] - time_s[0]) if trial.n_frames else 0.0,
        "time_source": time_source,
        "contact_threshold": config.contact_threshold,
        "force_unit": config.force_unit,
        "pressure_unit": config.pressure_unit if area is not None else None,
        "active_taxel_count_mean": float(np.mean(active_count)),
        "active_taxel_count_peak": int(np.max(active_count)),
        "total_contact_force_mean": float(np.mean(total_force)),
        "total_contact_force_peak": float(np.max(total_force)),
        "contact_fraction": float(np.mean(contact_mask)),
        "force_impulse": _trapz(total_force, time_s),
        "contact_duration_s": float(np.sum(np.diff(time_s, prepend=time_s[0]) * (active_count > 0))),
        "contact_area_mm2_mean": None if area_per_frame is None else float(np.mean(area_per_frame)),
        "contact_area_mm2_peak": None if area_per_frame is None else float(np.max(area_per_frame)),
        "mean_pressure_mean": None if area_per_frame is None else float(np.mean(metrics["mean_pressure"])),
    }
    if trial.sensor_forces is not None:
        summary["sensor_total_force_peak"] = float(np.max(metrics["sensor_total_force"]))
    if trial.temperature is not None:
        summary["temperature_mean"] = float(np.mean(trial.temperature))
        summary["temperature_max"] = float(np.max(trial.temperature))
    return AnalysisResult(metrics, taxel_force_norm, contact_mask, summary, trial.taxel_positions, trial.metadata)
