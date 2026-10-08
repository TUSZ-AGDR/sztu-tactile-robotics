from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml


@dataclass(frozen=True)
class SensorInstance:
    sensor_id: int
    sdk_name: str
    name: str
    template: str
    parent_body: str
    parent_geom: str
    site_name: str
    M_sdk_sensor: np.ndarray
    geom_id: int
    site_id: int


class SensorMount:
    def __init__(self, model: Any, sensors_yaml: str | Path):
        import mujoco

        with Path(sensors_yaml).open(encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)

        self.instances: list[SensorInstance] = []
        for item in payload["instances"]:
            geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, item["parent_geom"])
            site_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, item["site_name"])
            if geom_id < 0:
                raise ValueError(f"missing MuJoCo geom {item['parent_geom']}")
            if site_id < 0:
                raise ValueError(f"missing MuJoCo site {item['site_name']}")
            self.instances.append(
                SensorInstance(
                    sensor_id=int(item["sensor_id"]),
                    sdk_name=str(item["sdk_name"]),
                    name=str(item["name"]),
                    template=str(item["template"]),
                    parent_body=str(item["parent_body"]),
                    parent_geom=str(item["parent_geom"]),
                    site_name=str(item["site_name"]),
                    M_sdk_sensor=np.asarray(item["M_sdk_sensor"], dtype=np.float64),
                    geom_id=geom_id,
                    site_id=site_id,
                )
            )
        self.by_id = {instance.sensor_id: instance for instance in self.instances}
        self._geom_to_sensor = {instance.geom_id: instance.sensor_id for instance in self.instances}

    def get(self, sensor_id: int) -> SensorInstance:
        return self.by_id[sensor_id]

    def geom_to_sensor(self) -> dict[int, int]:
        return dict(self._geom_to_sensor)

    def get_world_sensor_pose(self, sensor_id: int, data: Any) -> np.ndarray:
        instance = self.by_id[sensor_id]
        t = np.asarray(data.site_xpos[instance.site_id], dtype=np.float64)
        R = np.asarray(data.site_xmat[instance.site_id], dtype=np.float64).reshape(3, 3)
        T = np.eye(4, dtype=np.float64)
        T[:3, :3] = R
        T[:3, 3] = t
        return T
