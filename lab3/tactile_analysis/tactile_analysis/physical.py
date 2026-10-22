"""Calibrated normal-force, discrete contact-area and pressure estimates."""

from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

from .plotting import save_frame_metrics, save_summary


@dataclass
class PhysicalResult:
    frame_metrics: dict
    force_vector_n: np.ndarray
    normal_force_n: np.ndarray
    pressure_pa: np.ndarray
    contact_mask: np.ndarray
    valid_mask: np.ndarray
    summary: dict
    metadata: dict

    def to_dict(self):
        return {"summary": self.summary, "metadata": self.metadata}


def _scalar(data, key):
    value = data[key]
    if value.shape != ():
        raise ValueError(f"Calibration {key} must be scalar")
    return value.item()


def _finite_array(data, key, shapes):
    raw = data[key]
    if raw.dtype.kind not in "fiu":
        raise ValueError(f"Calibration {key} must contain real numeric values")
    value = np.asarray(raw, dtype=float)
    if value.shape not in shapes or not np.isfinite(value).all():
        raise ValueError(f"Calibration {key} must be finite with shape in {shapes}")
    return value


def analyze_physical(trial, calibration_path, *, normal_threshold_n=0.1):
    """Intersect source validity with calibration validity; never promote raw masks."""
    if not np.isfinite(normal_threshold_n) or normal_threshold_n <= 0:
        raise ValueError("normal_threshold_n must be finite and positive")
    if trial.timestamps_ns is None or trial.n_frames == 0:
        raise ValueError("Physical analysis requires nonempty data and timestamps_ns")
    if trial.metadata.get("force_unit", "raw") != "raw":
        raise ValueError("Calibration requires raw-count input, not already converted force values")
    if any(v is None for v in (trial.taxel_valid_mask, trial.packet_valid, trial.sample_valid, trial.hand_side)):
        raise ValueError("Physical analysis requires source taxel_valid_mask, packet_valid, sample_valid and hand_side")
    path = Path(calibration_path).resolve()
    calibration_bytes = path.read_bytes()
    n = trial.n_taxels
    with np.load(BytesIO(calibration_bytes), allow_pickle=False) as data:
        version = _scalar(data, "schema_version")
        if type(version) is not int or version != 1:
            raise ValueError("Unsupported calibration schema_version")
        side = str(_scalar(data, "hand_side"))
        if side not in ("left", "right") or not np.all(trial.hand_side == side):
            raise ValueError("Calibration hand_side does not match the selected trial")
        source_kind = str(_scalar(data, "source_kind"))
        if source_kind not in ("measured", "synthetic_demo"):
            raise ValueError("Calibration source_kind must be measured or synthetic_demo")
        if source_kind == "synthetic_demo" and not trial.metadata.get("synthetic_demo", False):
            raise ValueError("Synthetic demo calibration cannot be used on real recordings")
        calibration_id = str(_scalar(data, "calibration_id"))
        if not calibration_id.strip():
            raise ValueError("Calibration calibration_id must not be empty")
        matrix = _finite_array(data, "force_matrix_n_per_count", ((3, 3), (n, 3, 3)))
        bias = _finite_array(data, "bias_counts", ((3,), (n, 3)))
        normals = _finite_array(data, "normal_vectors", ((3,), (n, 3)))
        if not np.allclose(np.linalg.norm(normals, axis=-1), 1.0, atol=1e-6, rtol=0):
            raise ValueError("Calibration normal_vectors must have unit length")
        area = _finite_array(data, "taxel_area_mm2", ((), (n,)))
        if np.any(area <= 0):
            raise ValueError("Calibration taxel_area_mm2 must be positive")
        calibration_valid = data["verified_taxel_mask"]
        if calibration_valid.shape != (n,) or calibration_valid.dtype != np.dtype(bool):
            raise ValueError(f"Calibration verified_taxel_mask must be bool [{n}]")
    valid = (trial.taxel_valid_mask & calibration_valid[None, :]
             & trial.packet_valid[:, None] & trial.sample_valid[:, None])
    frame_valid = valid.any(axis=1)
    if not frame_valid.any():
        raise ValueError("No verified taxels remain. Calibration does not override source validity masks; "
                         "verify acquisition masks and calibration before physical analysis.")
    centered = trial.detail_xyz - bias
    force = np.einsum("ij,tnj->tni", matrix, centered) if matrix.ndim == 2 else np.einsum("nij,tnj->tni", matrix, centered)
    if not np.isfinite(force).all():
        raise ValueError("Calibration produced nonfinite force values")
    signed_normal = np.sum(force * normals, axis=2)
    normal = np.maximum(signed_normal, 0)
    contact = valid & (normal >= normal_threshold_n)
    area_values = np.broadcast_to(area, (n,))
    total_area = (contact * area_values).sum(axis=1)
    normal_sum = np.where(contact, normal, 0).sum(axis=1)
    tangential = np.sqrt(np.maximum(np.sum(force ** 2, axis=2) - signed_normal ** 2, 0))
    tangential_sum = np.where(contact, tangential, 0).sum(axis=1)
    pressure = np.where(valid, np.where(contact, normal / area_values * 1e6, 0), np.nan)
    mean_pressure = np.divide(normal_sum * 1e6, total_area,
                              out=np.full(trial.n_frames, np.nan), where=total_area > 0)
    peak_pressure = np.max(np.where(contact, normal / area_values * 1e6, 0), axis=1)
    peak_pressure[(total_area == 0) | ~frame_valid] = np.nan
    normal_peak = np.max(np.where(contact, normal, 0), axis=1)
    time = (trial.timestamps_ns - trial.timestamps_ns[0]).astype(float) / 1e9
    measurable = lambda values: np.where(frame_valid, values, np.nan)
    metrics = {
        "time_s": time, "sample_valid": frame_valid, "verified_taxel_count": valid.sum(axis=1),
        "active_taxel_count": measurable(contact.sum(axis=1)),
        "contact_area_mm2": measurable(total_area), "normal_force_sum_n": measurable(normal_sum),
        "peak_taxel_normal_force_n": measurable(normal_peak),
        "tangential_magnitude_sum_n": measurable(tangential_sum),
        "mean_pressure_pa": mean_pressure, "mean_pressure_kpa": mean_pressure / 1000,
        "peak_pressure_pa": peak_pressure, "peak_pressure_kpa": peak_pressure / 1000,
    }
    interval_valid = frame_valid[:-1] & frame_valid[1:]
    impulse = np.sum(((normal_sum[:-1] + normal_sum[1:]) / 2 * np.diff(time))[interval_valid])
    duration = np.sum((np.diff(time) * (total_area[1:] > 0))[interval_valid])

    def finite_mean(value):
        value = np.asarray(value)
        return float(value[np.isfinite(value)].mean()) if np.isfinite(value).any() else None

    def finite_max(value):
        value = np.asarray(value)
        return float(value[np.isfinite(value)].max()) if np.isfinite(value).any() else None

    summary = {
        "analysis_mode": "calibrated_physical", "calibration_source_kind": source_kind,
        "calibration_id": calibration_id, "hand_side": side,
        "n_frames": trial.n_frames, "n_taxels": n, "valid_frames": int(frame_valid.sum()),
        "invalid_frames": int((~frame_valid).sum()), "normal_threshold_n": float(normal_threshold_n),
        "force_unit": "N", "pressure_unit": "Pa", "area_unit": "mm2",
        "duration_s": float(time[-1]), "contact_area_mm2_mean": finite_mean(metrics["contact_area_mm2"]),
        "contact_area_mm2_peak": finite_max(metrics["contact_area_mm2"]),
        "normal_force_sum_n_mean": finite_mean(metrics["normal_force_sum_n"]),
        "normal_force_sum_n_peak": finite_max(metrics["normal_force_sum_n"]),
        "mean_pressure_pa_mean": finite_mean(mean_pressure), "peak_pressure_pa": finite_max(peak_pressure),
        "normal_force_impulse_n_s": float(impulse), "contact_duration_s": float(duration),
        "scope": "Verified taxels only; thresholded discrete surface-area estimate; scalar force sums, not a world-frame resultant",
        "invalid_frame_policy": "Keep timestamps; NaN metrics; do not integrate across invalid adjacent frames",
        "no_contact_pressure_policy": "NaN / null when valid contact area is zero",
    }
    return PhysicalResult(metrics, np.where(valid[:, :, None], force, np.nan),
                          np.where(valid, normal, np.nan), pressure, contact, valid, summary,
                          {"calibration_file": str(path), "calibration_sha256": hashlib.sha256(calibration_bytes).hexdigest(),
                           "source_metadata": trial.metadata})


def export_physical(result, output_dir, *, export_mat=False):
    destination = Path(output_dir).resolve()
    if destination.exists():
        raise FileExistsError(f"Analysis output already exists; choose a new --output-dir: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".physical-", dir=destination.parent))
    try:
        save_summary(result, stage / "summary.json")
        save_frame_metrics(result, stage / "frame_metrics.csv")
        np.savez_compressed(stage / "physical_arrays.npz", force_vector_n=result.force_vector_n,
                            normal_force_n=result.normal_force_n, pressure_pa=result.pressure_pa,
                            contact_mask=result.contact_mask, effective_valid_mask=result.valid_mask,
                            time_s=result.frame_metrics["time_s"])
        from .report import _figure, _edges
        fig, axes = _figure(3, 1, (11, 9))
        time = result.frame_metrics["time_s"]
        for ax, key, label in zip(axes.ravel(), ("contact_area_mm2", "normal_force_sum_n", "mean_pressure_kpa"),
                                 ("Contact area [mm2]", "Sum of normal forces [N]", "Mean pressure [kPa]")):
            ax.plot(time, result.frame_metrics[key], lw=1.3, color="#126d86")
            ax.set_ylabel(label)
            ax.set_xlabel("Time [s]")
            ax.grid(alpha=.2)
        fig.savefig(stage / "physical_overview.png", dpi=140)
        fig, axes = _figure(1, 1, (12, 4))
        mesh = axes[0, 0].pcolormesh(_edges(time), np.arange(result.pressure_pa.shape[1] + 1) - .5,
                                    result.pressure_pa.T / 1000, cmap="magma", rasterized=True)
        axes[0, 0].set_xlabel("Time [s]")
        axes[0, 0].set_ylabel("Taxel index (0-based)")
        axes[0, 0].set_title("Calibrated normal pressure; unverified taxels are blank")
        fig.colorbar(mesh, ax=axes[0, 0], label="Pressure [kPa]")
        fig.savefig(stage / "pressure_heatmap.png", dpi=140)
        if export_mat:
            from scipy.io import savemat
            savemat(stage / "analysis.mat", {**result.frame_metrics, "normal_force_n": result.normal_force_n,
                                            "pressure_pa": result.pressure_pa, "contact_mask": result.contact_mask.astype(np.uint8)})
        os.rename(stage, destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return destination
