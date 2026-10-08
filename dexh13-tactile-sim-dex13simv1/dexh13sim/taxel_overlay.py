from __future__ import annotations

from typing import Any

import numpy as np

from .sensor_mount import SensorMount
from .sensor_table import SENSOR_TABLE, total_taxels
from .taxel_template import TaxelTemplate


class TaxelHeatmapOverlay:
    def __init__(
        self,
        mount: SensorMount,
        templates: dict[str, TaxelTemplate],
        stride: int = 1,
        radius_m: float = 0.00075,
        gain: float = 1.0,
    ):
        self.mount = mount
        self.templates = templates
        self.stride = max(1, int(stride))
        self.radius_m = float(radius_m)
        self.gain = float(gain)

    def world_positions(self, data: Any) -> np.ndarray:
        positions = np.zeros((total_taxels(), 3), dtype=np.float64)
        for spec in SENSOR_TABLE:
            instance = self.mount.get(spec.sensor_id)
            template = self.templates[spec.template]
            R = np.asarray(data.site_xmat[instance.site_id], dtype=np.float64).reshape(3, 3)
            t = np.asarray(data.site_xpos[instance.site_id], dtype=np.float64)
            positions[spec.start : spec.end] = template.xyz_m @ R.T + t
        return positions

    def update_scene(self, scene: Any, data: Any, raw_sensor_N: np.ndarray) -> int:
        import mujoco

        positions = self.world_positions(data)
        magnitudes = np.linalg.norm(np.asarray(raw_sensor_N, dtype=np.float64), axis=1)
        max_magnitude = float(magnitudes.max(initial=0.0))
        if max_magnitude > 0.0:
            intensity = np.clip((magnitudes / max_magnitude) * self.gain, 0.0, 1.0)
        else:
            intensity = np.zeros_like(magnitudes)

        scene.ngeom = 0
        mat = np.eye(3, dtype=np.float64).reshape(9)
        count = 0
        maxgeom = len(scene.geoms)
        for taxel_id in range(0, total_taxels(), self.stride):
            if scene.ngeom >= maxgeom:
                break
            value = float(intensity[taxel_id])
            radius = self.radius_m * (0.75 + value)
            rgba = heat_color(value)
            mujoco.mjv_initGeom(
                scene.geoms[scene.ngeom],
                mujoco.mjtGeom.mjGEOM_SPHERE,
                np.asarray([radius, 0.0, 0.0], dtype=np.float64),
                positions[taxel_id],
                mat,
                rgba,
            )
            scene.ngeom += 1
            count += 1
        return count


def heat_color(value: float) -> np.ndarray:
    value = float(np.clip(value, 0.0, 1.0))
    low = np.asarray([0.05, 0.25, 1.0, 0.12], dtype=np.float32)
    high = np.asarray([1.0, 0.05, 0.0, 0.85], dtype=np.float32)
    return low * (1.0 - value) + high * value
