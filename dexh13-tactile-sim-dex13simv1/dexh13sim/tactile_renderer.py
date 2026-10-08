from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

from .sensor_table import SensorSpec


class TactileRenderer:
    def __init__(
        self,
        sensor_specs: Sequence[SensorSpec],
        templates: Mapping[str, object],
        template_config: Mapping[str, Mapping[str, object]],
        total_taxels: int,
    ):
        self.sensor_specs = {spec.sensor_id: spec for spec in sensor_specs}
        self.templates = templates
        self.template_config = template_config
        self.total_taxels = total_taxels

    def render(self, contacts: Sequence[Mapping[str, object]]) -> np.ndarray:
        tactile = np.zeros((self.total_taxels, 3), dtype=np.float32)
        for contact in contacts:
            sensor_id = int(contact["sensor_id"])
            spec = self.sensor_specs[sensor_id]
            template = self.templates[spec.template]
            config = self.template_config[spec.template]

            p_sensor = np.asarray(contact["p_sensor"], dtype=np.float64)
            f_sensor = np.asarray(contact["f_sensor"], dtype=np.float64)
            weights = self._weights(template, config, p_sensor)
            weight_sum = weights.sum()
            if weight_sum <= float(config.get("min_raw_weight", 1.0e-12)):
                continue

            normalized = weights / weight_sum
            tactile[spec.start : spec.end] += (normalized[:, None] * f_sensor).astype(np.float32)
        return tactile

    @staticmethod
    def _weights(template: object, config: Mapping[str, object], p_sensor: np.ndarray) -> np.ndarray:
        xyz_m = np.asarray(template.xyz_m, dtype=np.float64)
        normals = np.asarray(template.normals, dtype=np.float64)
        delta = p_sensor[None, :] - xyz_m
        normal_offset = np.einsum("ij,ij->i", delta, normals)
        distance_sq = np.einsum("ij,ij->i", delta, delta)
        tangential_sq = np.maximum(distance_sq - normal_offset * normal_offset, 0.0)

        sigma_t = float(config["sigma_t0"])
        sigma_n = float(config["sigma_n0"])
        outside_reject_dist = float(config["outside_reject_dist"])
        max_abs_normal_offset = float(config["max_abs_normal_offset"])

        valid = (np.sqrt(distance_sq) <= outside_reject_dist) & (
            np.abs(normal_offset) <= max_abs_normal_offset
        )
        weights = np.zeros(len(xyz_m), dtype=np.float64)
        weights[valid] = np.exp(
            -0.5 * ((tangential_sq[valid] / (sigma_t * sigma_t)) + (normal_offset[valid] ** 2 / (sigma_n * sigma_n)))
        )
        return weights
