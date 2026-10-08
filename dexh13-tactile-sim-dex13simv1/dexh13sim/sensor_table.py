from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SensorSpec:
    sensor_id: int
    sdk_name: str
    name: str
    template: str
    count: int
    start: int
    end: int


SENSOR_TABLE: tuple[SensorSpec, ...] = (
    SensorSpec(0, "sensor1", "index_proximal", "IP_M3025", 120, 0, 120),
    SensorSpec(1, "sensor2", "index_middle", "MP_M2324", 60, 120, 180),
    SensorSpec(2, "sensor3", "index_tip", "DP_M2826", 120, 180, 300),
    SensorSpec(3, "sensor4", "middle_proximal", "IP_M3025", 120, 300, 420),
    SensorSpec(4, "sensor5", "middle_middle", "MP_M2324", 60, 420, 480),
    SensorSpec(5, "sensor6", "middle_tip", "DP_M2826", 120, 480, 600),
    SensorSpec(6, "sensor7", "ring_proximal", "IP_M3025", 120, 600, 720),
    SensorSpec(7, "sensor8", "ring_middle", "MP_M2324", 60, 720, 780),
    SensorSpec(8, "sensor9", "ring_tip", "DP_M2826", 120, 780, 900),
    SensorSpec(9, "sensor10", "thumb_proximal", "IP_L5325", 120, 900, 1020),
    SensorSpec(10, "sensor11", "thumb_tip", "DP_L3530", 120, 1020, 1140),
)

SENSOR_BY_ID = {spec.sensor_id: spec for spec in SENSOR_TABLE}
SENSOR_BY_NAME = {spec.name: spec for spec in SENSOR_TABLE}


def total_taxels() -> int:
    return SENSOR_TABLE[-1].end
