from __future__ import annotations

from copy import deepcopy
import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import h5py
import numpy as np
import yaml

from .sensor_table import SensorSpec
from .tactile_renderer import TactileRenderer


@dataclass(frozen=True)
class CalibrationSampleSet:
    sensor_id: np.ndarray
    p_sensor: np.ndarray
    f_sensor: np.ndarray
    observed_detail_N: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)

    def validated(self) -> "CalibrationSampleSet":
        sensor_id = np.asarray(self.sensor_id, dtype=np.int32)
        p_sensor = np.asarray(self.p_sensor, dtype=np.float32)
        f_sensor = np.asarray(self.f_sensor, dtype=np.float32)
        observed_detail_N = np.asarray(self.observed_detail_N, dtype=np.float32)
        sample_count = int(sensor_id.shape[0])
        if sensor_id.ndim != 1:
            raise ValueError("sensor_id must have shape (samples,)")
        if p_sensor.shape != (sample_count, 3):
            raise ValueError(f"p_sensor must have shape ({sample_count}, 3)")
        if f_sensor.shape != (sample_count, 3):
            raise ValueError(f"f_sensor must have shape ({sample_count}, 3)")
        if observed_detail_N.ndim != 3 or observed_detail_N.shape[0] != sample_count or observed_detail_N.shape[2] != 3:
            raise ValueError("observed_detail_N must have shape (samples, taxels, 3)")
        if not np.isfinite(p_sensor).all() or not np.isfinite(f_sensor).all() or not np.isfinite(observed_detail_N).all():
            raise ValueError("calibration samples contain non-finite values")
        return CalibrationSampleSet(
            sensor_id=sensor_id,
            p_sensor=p_sensor,
            f_sensor=f_sensor,
            observed_detail_N=observed_detail_N,
            metadata=dict(self.metadata),
        )


@dataclass(frozen=True)
class TemplateFitResult:
    template: str
    sigma_t0: float
    sigma_n0: float
    mse: float
    samples: int
    A_matrix: list[list[float]] | None = None
    bias_N: list[float] | None = None
    fit_axes: list[str] = field(default_factory=lambda: ["x", "y", "z"])


@dataclass(frozen=True)
class CalibrationEvaluationReport:
    samples: int
    mse_N2: float
    rmse_N: float
    mae_N: float
    peak_taxel_accuracy: float


AXIS_NAME_TO_INDEX = {"x": 0, "y": 1, "z": 2}
AXIS_INDEX_TO_NAME = {value: key for key, value in AXIS_NAME_TO_INDEX.items()}


def parse_axis_selection(axes: str | Sequence[str | int] | None) -> tuple[int, ...]:
    if axes is None:
        return (0, 1, 2)
    if isinstance(axes, str):
        compact = axes.replace(",", "").replace(" ", "").lower()
        if compact in {"", "all", "xyz"}:
            items: Sequence[str | int] = ("x", "y", "z")
        else:
            items = tuple(compact)
    else:
        items = axes

    parsed: list[int] = []
    for item in items:
        if isinstance(item, str):
            key = item.strip().lower()
            if key not in AXIS_NAME_TO_INDEX:
                raise ValueError(f"unknown axis {item!r}; expected x, y, z, xyz, or all")
            axis = AXIS_NAME_TO_INDEX[key]
        else:
            axis = int(item)
            if axis not in AXIS_INDEX_TO_NAME:
                raise ValueError(f"unknown axis index {axis}; expected 0, 1, or 2")
        if axis not in parsed:
            parsed.append(axis)
    if not parsed:
        raise ValueError("at least one fit axis is required")
    return tuple(parsed)


def axis_selection_names(axes: str | Sequence[str | int] | None) -> list[str]:
    return [AXIS_INDEX_TO_NAME[index] for index in parse_axis_selection(axes)]


def write_calibration_samples(path: str | Path, samples: CalibrationSampleSet) -> None:
    samples = samples.validated()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as h5:
        contact = h5.create_group("contact")
        contact.create_dataset("sensor_id", data=samples.sensor_id, dtype="int32")
        contact.create_dataset("p_sensor", data=samples.p_sensor, dtype="float32")
        contact.create_dataset("f_sensor", data=samples.f_sensor, dtype="float32")
        observed = h5.create_group("observed")
        observed.create_dataset("detail_N", data=samples.observed_detail_N, dtype="float32")
        metadata = h5.create_group("metadata")
        for key, value in samples.metadata.items():
            metadata.attrs[key] = value


def load_calibration_samples_csv(
    path: str | Path,
    total_taxels: int = 1140,
    metadata: Mapping[str, Any] | None = None,
) -> CalibrationSampleSet:
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"{path} contains no calibration rows")

    required = {
        "sample_id",
        "sensor_id",
        "px_m",
        "py_m",
        "pz_m",
        "fx_N",
        "fy_N",
        "fz_N",
        "taxel_id",
        "x_N",
        "y_N",
        "z_N",
    }
    missing = sorted(required - set(rows[0]))
    if missing:
        raise ValueError(f"{path} missing required columns: {', '.join(missing)}")

    sample_order: list[str] = []
    sample_payload: dict[str, dict[str, object]] = {}
    for row_idx, row in enumerate(rows, start=2):
        sample_id = str(row["sample_id"])
        if sample_id not in sample_payload:
            sample_order.append(sample_id)
            sample_payload[sample_id] = {
                "sensor_id": int(row["sensor_id"]),
                "p_sensor": np.asarray([float(row["px_m"]), float(row["py_m"]), float(row["pz_m"])], dtype=np.float32),
                "f_sensor": np.asarray([float(row["fx_N"]), float(row["fy_N"]), float(row["fz_N"])], dtype=np.float32),
                "observed": np.zeros((total_taxels, 3), dtype=np.float32),
                "seen_taxels": set(),
            }
        payload = sample_payload[sample_id]
        _check_consistent_sample_row(path, row_idx, row, payload)
        taxel_id = int(row["taxel_id"])
        if taxel_id < 0 or taxel_id >= total_taxels:
            raise ValueError(f"{path}:{row_idx} taxel_id {taxel_id} outside 0..{total_taxels - 1}")
        seen_taxels = payload["seen_taxels"]
        assert isinstance(seen_taxels, set)
        if taxel_id in seen_taxels:
            raise ValueError(f"{path}:{row_idx} duplicate taxel_id {taxel_id} for sample_id {sample_id}")
        seen_taxels.add(taxel_id)
        observed = payload["observed"]
        assert isinstance(observed, np.ndarray)
        observed[taxel_id] = np.asarray([float(row["x_N"]), float(row["y_N"]), float(row["z_N"])], dtype=np.float32)

    for sample_id in sample_order:
        seen_taxels = sample_payload[sample_id]["seen_taxels"]
        assert isinstance(seen_taxels, set)
        if len(seen_taxels) != total_taxels:
            raise ValueError(
                f"{path} sample_id {sample_id} has {len(seen_taxels)} taxels, expected {total_taxels}"
            )

    merged_metadata = {"source_format": "flat_csv_v1", "source_path": str(path)}
    if metadata:
        merged_metadata.update(dict(metadata))
    return CalibrationSampleSet(
        sensor_id=np.asarray([sample_payload[item]["sensor_id"] for item in sample_order], dtype=np.int32),
        p_sensor=np.stack([sample_payload[item]["p_sensor"] for item in sample_order]).astype(np.float32),
        f_sensor=np.stack([sample_payload[item]["f_sensor"] for item in sample_order]).astype(np.float32),
        observed_detail_N=np.stack([sample_payload[item]["observed"] for item in sample_order]).astype(np.float32),
        metadata=merged_metadata,
    ).validated()


def load_calibration_samples(path: str | Path) -> CalibrationSampleSet:
    with h5py.File(path, "r") as h5:
        for dataset in ("contact/sensor_id", "contact/p_sensor", "contact/f_sensor", "observed/detail_N"):
            if dataset not in h5:
                raise ValueError(f"missing calibration dataset {dataset}")
        metadata = dict(h5["metadata"].attrs) if "metadata" in h5 else {}
        return CalibrationSampleSet(
            sensor_id=h5["contact/sensor_id"][:],
            p_sensor=h5["contact/p_sensor"][:],
            f_sensor=h5["contact/f_sensor"][:],
            observed_detail_N=h5["observed/detail_N"][:],
            metadata=metadata,
        ).validated()


def fit_rbf_parameters(
    samples: CalibrationSampleSet,
    sensor_specs: Sequence[SensorSpec],
    templates: Mapping[str, object],
    template_config: Mapping[str, Mapping[str, object]],
    candidate_sigma_t: Sequence[float],
    candidate_sigma_n: Sequence[float],
    fit_response: bool = False,
    response_regularization: float = 1.0e-8,
    fit_axes: str | Sequence[str | int] | None = None,
    lock_rbf: bool = False,
) -> dict[str, TemplateFitResult]:
    samples = samples.validated()
    selected_axes = parse_axis_selection(fit_axes)
    if not lock_rbf and (not candidate_sigma_t or not candidate_sigma_n):
        raise ValueError("candidate_sigma_t and candidate_sigma_n must not be empty")
    total_taxels = _total_taxels(sensor_specs)
    if samples.observed_detail_N.shape[1:] != (total_taxels, 3):
        raise ValueError(
            f"observed_detail_N must have shape (samples, {total_taxels}, 3), "
            f"got {samples.observed_detail_N.shape}"
        )

    specs_by_id = {int(spec.sensor_id): spec for spec in sensor_specs}
    sample_indices_by_template: dict[str, list[int]] = {}
    for idx, sensor_id in enumerate(samples.sensor_id):
        if int(sensor_id) not in specs_by_id:
            raise ValueError(f"sample {idx} references unknown sensor_id {int(sensor_id)}")
        template_name = specs_by_id[int(sensor_id)].template
        sample_indices_by_template.setdefault(template_name, []).append(idx)

    fits: dict[str, TemplateFitResult] = {}
    for template_name, indices in sample_indices_by_template.items():
        best: TemplateFitResult | None = None
        if lock_rbf:
            if template_name not in template_config:
                raise ValueError(f"missing template config {template_name}")
            sigma_t_candidates = [float(template_config[template_name]["sigma_t0"])]
            sigma_n_candidates = [float(template_config[template_name]["sigma_n0"])]
        else:
            sigma_t_candidates = [float(value) for value in candidate_sigma_t]
            sigma_n_candidates = [float(value) for value in candidate_sigma_n]
        for sigma_t in sigma_t_candidates:
            for sigma_n in sigma_n_candidates:
                config = _candidate_config(template_config, template_name, float(sigma_t), float(sigma_n))
                renderer = TactileRenderer(sensor_specs, templates, config, total_taxels)
                predicted_values, target_values = _template_value_pairs(
                    samples, specs_by_id, renderer, template_name, indices
                )
                A_matrix = np.eye(3, dtype=np.float64)
                bias_N = np.zeros(3, dtype=np.float64)
                if fit_response:
                    base_A_matrix, base_bias_N = _response_from_config(template_config, template_name)
                    A_matrix, bias_N = _fit_affine_response(
                        predicted_values,
                        target_values,
                        regularization=float(response_regularization),
                        axes=selected_axes,
                        base_A_matrix=base_A_matrix,
                        base_bias_N=base_bias_N,
                    )
                    predicted_values = _apply_affine_response(predicted_values, A_matrix, bias_N)
                mse = _mean_squared_error(predicted_values, target_values, axes=selected_axes)
                if best is None or mse < best.mse:
                    best = TemplateFitResult(
                        template=template_name,
                        sigma_t0=float(sigma_t),
                        sigma_n0=float(sigma_n),
                        mse=float(mse),
                        samples=len(indices),
                        A_matrix=A_matrix.tolist() if fit_response else None,
                        bias_N=bias_N.tolist() if fit_response else None,
                        fit_axes=axis_selection_names(selected_axes),
                    )
        assert best is not None
        fits[template_name] = best
    return fits


def evaluate_rbf_fit(
    samples: CalibrationSampleSet,
    sensor_specs: Sequence[SensorSpec],
    templates: Mapping[str, object],
    template_config: Mapping[str, Mapping[str, object]],
    axes: str | Sequence[str | int] | None = None,
) -> CalibrationEvaluationReport:
    samples = samples.validated()
    selected_axes = parse_axis_selection(axes)
    total_taxels = _total_taxels(sensor_specs)
    if samples.observed_detail_N.shape[1:] != (total_taxels, 3):
        raise ValueError(
            f"observed_detail_N must have shape (samples, {total_taxels}, 3), "
            f"got {samples.observed_detail_N.shape}"
        )
    specs_by_id = {int(spec.sensor_id): spec for spec in sensor_specs}
    renderer = TactileRenderer(sensor_specs, templates, template_config, total_taxels)
    squared_error = 0.0
    absolute_error = 0.0
    values = 0
    peak_matches = 0
    for idx, sensor_id_value in enumerate(samples.sensor_id):
        sensor_id = int(sensor_id_value)
        if sensor_id not in specs_by_id:
            raise ValueError(f"sample {idx} references unknown sensor_id {sensor_id}")
        spec = specs_by_id[sensor_id]
        predicted = renderer.render(
            [
                {
                    "sensor_id": sensor_id,
                    "p_sensor": samples.p_sensor[idx],
                    "f_sensor": samples.f_sensor[idx],
                }
            ]
        )
        target = samples.observed_detail_N[idx]
        A_matrix, bias_N = _response_from_config(template_config, spec.template)
        predicted_values = _apply_affine_response(predicted[spec.start : spec.end], A_matrix, bias_N)
        target_values = target[spec.start : spec.end]
        delta = predicted_values - target_values
        selected_delta = delta[:, selected_axes]
        squared_error += float(np.sum(selected_delta * selected_delta))
        absolute_error += float(np.sum(np.abs(selected_delta)))
        values += int(selected_delta.size)
        predicted_peak = int(np.linalg.norm(predicted_values[:, selected_axes], axis=1).argmax())
        target_peak = int(np.linalg.norm(target_values[:, selected_axes], axis=1).argmax())
        peak_matches += int(predicted_peak == target_peak)
    if values <= 0:
        raise ValueError("no values available for calibration evaluation")
    mse = squared_error / values
    mae = absolute_error / values
    if mse < 1.0e-12:
        mse = 0.0
    if mae < 1.0e-6:
        mae = 0.0
    return CalibrationEvaluationReport(
        samples=int(samples.sensor_id.shape[0]),
        mse_N2=float(mse),
        rmse_N=float(np.sqrt(mse)),
        mae_N=float(mae),
        peak_taxel_accuracy=float(peak_matches / max(1, int(samples.sensor_id.shape[0]))),
    )


def apply_fit_to_calibration(calibration: Mapping[str, Any], fits: Mapping[str, TemplateFitResult]) -> dict[str, Any]:
    updated = deepcopy(dict(calibration))
    templates = updated.setdefault("templates", {})
    for template_name, result in fits.items():
        if template_name not in templates:
            templates[template_name] = {}
        templates[template_name]["sigma_t0"] = float(result.sigma_t0)
        templates[template_name]["sigma_n0"] = float(result.sigma_n0)
        templates[template_name]["fit_mse"] = float(result.mse)
        templates[template_name]["fit_samples"] = int(result.samples)
        if result.A_matrix is not None:
            templates[template_name]["A_matrix"] = result.A_matrix
        if result.bias_N is not None:
            templates[template_name]["bias_N"] = result.bias_N
    return updated


def write_calibration_yaml(path: str | Path, calibration: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(dict(calibration), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _total_taxels(sensor_specs: Sequence[SensorSpec]) -> int:
    if not sensor_specs:
        raise ValueError("sensor_specs must not be empty")
    return max(int(spec.end) for spec in sensor_specs)


def _candidate_config(
    template_config: Mapping[str, Mapping[str, object]],
    template_name: str,
    sigma_t: float,
    sigma_n: float,
) -> dict[str, dict[str, object]]:
    config = {name: dict(values) for name, values in template_config.items()}
    if template_name not in config:
        raise ValueError(f"missing template config {template_name}")
    config[template_name]["sigma_t0"] = sigma_t
    config[template_name]["sigma_n0"] = sigma_n
    return config


def _check_consistent_sample_row(path: Path, row_idx: int, row: Mapping[str, str], payload: Mapping[str, object]) -> None:
    sensor_id = int(payload["sensor_id"])
    p_sensor = np.asarray(payload["p_sensor"], dtype=np.float32)
    f_sensor = np.asarray(payload["f_sensor"], dtype=np.float32)
    row_sensor_id = int(row["sensor_id"])
    row_p = np.asarray([float(row["px_m"]), float(row["py_m"]), float(row["pz_m"])], dtype=np.float32)
    row_f = np.asarray([float(row["fx_N"]), float(row["fy_N"]), float(row["fz_N"])], dtype=np.float32)
    if row_sensor_id != sensor_id:
        raise ValueError(f"{path}:{row_idx} inconsistent sensor_id for sample_id {row['sample_id']}")
    if not np.allclose(row_p, p_sensor):
        raise ValueError(f"{path}:{row_idx} inconsistent p_sensor for sample_id {row['sample_id']}")
    if not np.allclose(row_f, f_sensor):
        raise ValueError(f"{path}:{row_idx} inconsistent f_sensor for sample_id {row['sample_id']}")


def _template_value_pairs(
    samples: CalibrationSampleSet,
    specs_by_id: Mapping[int, SensorSpec],
    renderer: TactileRenderer,
    template_name: str,
    indices: Sequence[int],
) -> tuple[np.ndarray, np.ndarray]:
    predicted_blocks: list[np.ndarray] = []
    target_blocks: list[np.ndarray] = []
    for idx in indices:
        sensor_id = int(samples.sensor_id[idx])
        spec = specs_by_id[sensor_id]
        if spec.template != template_name:
            continue
        predicted = renderer.render(
            [
                {
                    "sensor_id": sensor_id,
                    "p_sensor": samples.p_sensor[idx],
                    "f_sensor": samples.f_sensor[idx],
                }
            ]
        )
        target = samples.observed_detail_N[idx]
        predicted_blocks.append(np.asarray(predicted[spec.start : spec.end], dtype=np.float64))
        target_blocks.append(np.asarray(target[spec.start : spec.end], dtype=np.float64))
    if not predicted_blocks:
        raise ValueError(f"no samples available for template {template_name}")
    return np.concatenate(predicted_blocks, axis=0), np.concatenate(target_blocks, axis=0)


def _fit_affine_response(
    predicted_values: np.ndarray,
    target_values: np.ndarray,
    regularization: float,
    axes: Sequence[int],
    base_A_matrix: np.ndarray | None = None,
    base_bias_N: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    predicted = np.asarray(predicted_values, dtype=np.float64)
    target = np.asarray(target_values, dtype=np.float64)
    if predicted.ndim != 2 or predicted.shape[1] != 3:
        raise ValueError("predicted_values must have shape (values, 3)")
    if target.shape != predicted.shape:
        raise ValueError("target_values must have the same shape as predicted_values")

    if base_A_matrix is None:
        A_matrix = np.eye(3, dtype=np.float64)
    else:
        A_matrix = np.asarray(base_A_matrix, dtype=np.float64).copy()
    if base_bias_N is None:
        bias_N = np.zeros(3, dtype=np.float64)
    else:
        bias_N = np.asarray(base_bias_N, dtype=np.float64).copy()
    if A_matrix.shape != (3, 3):
        raise ValueError(f"base_A_matrix must have shape (3, 3), got {A_matrix.shape}")
    if bias_N.shape != (3,):
        raise ValueError(f"base_bias_N must have shape (3,), got {bias_N.shape}")

    design = np.concatenate([predicted, np.ones((predicted.shape[0], 1), dtype=np.float64)], axis=1)
    selected_axes = parse_axis_selection(axes)
    for axis in selected_axes:
        target_axis = target[:, axis]
        if regularization > 0.0:
            lhs = design.T @ design
            ridge = np.eye(lhs.shape[0], dtype=np.float64) * regularization
            ridge[-1, -1] = 0.0
            rhs = design.T @ target_axis
            try:
                weights = np.linalg.solve(lhs + ridge, rhs)
            except np.linalg.LinAlgError:
                weights = np.linalg.lstsq(design, target_axis, rcond=None)[0]
        else:
            weights = np.linalg.lstsq(design, target_axis, rcond=None)[0]
        A_matrix[axis, :] = weights[:3]
        bias_N[axis] = weights[3]
    return A_matrix, bias_N


def _apply_affine_response(values: np.ndarray, A_matrix: np.ndarray, bias_N: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    A = np.asarray(A_matrix, dtype=np.float64)
    bias = np.asarray(bias_N, dtype=np.float64)
    if A.shape != (3, 3):
        raise ValueError(f"A_matrix must have shape (3, 3), got {A.shape}")
    if bias.shape != (3,):
        raise ValueError(f"bias_N must have shape (3,), got {bias.shape}")
    return values @ A.T + bias


def _response_from_config(
    template_config: Mapping[str, Mapping[str, object]],
    template_name: str,
) -> tuple[np.ndarray, np.ndarray]:
    config = template_config.get(template_name, {})
    A_matrix = np.asarray(config.get("A_matrix", np.eye(3)), dtype=np.float64)
    bias_N = np.asarray(config.get("bias_N", [0.0, 0.0, 0.0]), dtype=np.float64)
    if A_matrix.shape != (3, 3):
        raise ValueError(f"{template_name}.A_matrix must have shape (3, 3), got {A_matrix.shape}")
    if bias_N.shape != (3,):
        raise ValueError(f"{template_name}.bias_N must have shape (3,), got {bias_N.shape}")
    return A_matrix, bias_N


def _mean_squared_error(
    predicted_values: np.ndarray,
    target_values: np.ndarray,
    axes: str | Sequence[str | int] | None = None,
) -> float:
    delta = np.asarray(predicted_values, dtype=np.float64) - np.asarray(target_values, dtype=np.float64)
    selected_axes = parse_axis_selection(axes)
    delta = delta[:, selected_axes]
    if delta.size <= 0:
        raise ValueError("no values available for mean squared error")
    return float(np.mean(delta * delta))
