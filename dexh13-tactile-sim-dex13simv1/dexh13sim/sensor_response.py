from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

from .sensor_table import SensorSpec


class SensorResponse:
    def __init__(
        self,
        sensor_specs: Sequence[SensorSpec],
        sensor_matrices: Mapping[str, np.ndarray],
        template_config: Mapping[str, Mapping[str, object]],
        lsb_per_N: float,
        random_seed: int = 0,
    ):
        self.sensor_specs = list(sensor_specs)
        self.sensor_matrices = sensor_matrices
        self.template_config = template_config
        self.lsb_per_N = float(lsb_per_N)
        self.rng = np.random.default_rng(random_seed)

    def apply(self, raw_sensor_N: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        raw = np.asarray(raw_sensor_N, dtype=np.float64)
        if not np.any(raw):
            zeros = np.zeros_like(raw, dtype=np.float32)
            return zeros, zeros
        detail_N = raw.copy()
        for spec in self.sensor_specs:
            config = self.template_config[spec.template]
            values = detail_N[spec.start : spec.end]

            A = np.asarray(config.get("A_matrix", np.eye(3)), dtype=np.float64)
            bias = np.asarray(config.get("bias_N", [0.0, 0.0, 0.0]), dtype=np.float64)
            noise_std = np.asarray(config.get("noise_std_N", [0.0, 0.0, 0.0]), dtype=np.float64)
            M_sdk_sensor = np.asarray(self.sensor_matrices.get(spec.name, np.eye(3)), dtype=np.float64)

            values = (A @ values.T).T + bias
            if np.any(noise_std > 0):
                values += self.rng.normal(0.0, noise_std, size=values.shape)
            values = (M_sdk_sensor @ values.T).T
            detail_N[spec.start : spec.end] = clip_values(values, config.get("clip_N", {}))

        detail_N = detail_N.astype(np.float32)
        detail_sdk = (detail_N * self.lsb_per_N).astype(np.float32)
        return detail_N, detail_sdk


def clip_values(values: np.ndarray, clip_config: object) -> np.ndarray:
    if not isinstance(clip_config, Mapping):
        return values
    clipped = values.copy()
    axes = ("x", "y", "z")
    for axis_idx, axis_name in enumerate(axes):
        if axis_name in clip_config:
            lo, hi = clip_config[axis_name]
            clipped[:, axis_idx] = np.clip(clipped[:, axis_idx], float(lo), float(hi))
    return clipped
