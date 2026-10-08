from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from .contact_reader import ContactReader
from .sensor_mount import SensorMount
from .sensor_response import SensorResponse
from .sensor_table import SENSOR_TABLE, SensorSpec, total_taxels
from .tactile_renderer import TactileRenderer
from .tactile_sampler import TactileSampler
from .taxel_template import TaxelTemplate


@dataclass(frozen=True)
class TactileSummary:
    total_N: float
    sensor_sums_N: np.ndarray
    peak_taxel: int
    peak_taxel_N: float
    peak_sensor: SensorSpec | None


def load_templates(root: str | Path = "configs/taxel_templates") -> dict[str, TaxelTemplate]:
    root = Path(root)
    templates: dict[str, TaxelTemplate] = {}
    for template_name in sorted({spec.template for spec in SENSOR_TABLE}):
        expected = next(spec.count for spec in SENSOR_TABLE if spec.template == template_name)
        templates[template_name] = TaxelTemplate.load(root / f"{template_name}.csv", template_name, expected)
    return templates


def load_sensor_matrices(sensors_yaml: str | Path = "configs/sensors.yaml") -> dict[str, np.ndarray]:
    payload = yaml.safe_load(Path(sensors_yaml).read_text(encoding="utf-8"))
    return {
        item["name"]: np.asarray(item["M_sdk_sensor"], dtype=np.float64)
        for item in payload["instances"]
    }


class TactileRuntime:
    def __init__(
        self,
        model: Any,
        sensors_yaml: str | Path = "configs/sensors.yaml",
        calibration_yaml: str | Path = "configs/calibration.yaml",
        templates_dir: str | Path = "configs/taxel_templates",
    ):
        self.model = model
        self.calibration = yaml.safe_load(Path(calibration_yaml).read_text(encoding="utf-8"))
        self.mount = SensorMount(model, sensors_yaml)
        self.templates = load_templates(templates_dir)
        self.reader = ContactReader(
            model,
            self.mount,
            force_on_geom1=self.calibration["global"]["force_on_geom1"],
        )
        self.renderer = TactileRenderer(
            SENSOR_TABLE,
            self.templates,
            self.calibration["templates"],
            total_taxels(),
        )
        self.response = SensorResponse(
            SENSOR_TABLE,
            load_sensor_matrices(sensors_yaml),
            self.calibration["templates"],
            self.calibration["global"]["lsb_per_N"],
            self.calibration["global"]["random_seed"],
        )
        self.sampler = TactileSampler(
            self.calibration["global"]["sim_dt"],
            self.calibration["global"]["tactile_hz"],
            (total_taxels(), 3),
        )

    @property
    def sim_dt(self) -> float:
        return float(self.calibration["global"]["sim_dt"])

    @property
    def tactile_hz(self) -> int:
        return int(self.calibration["global"]["tactile_hz"])

    @property
    def sensor_native_hz(self) -> int:
        return int(self.calibration["global"].get("sensor_native_hz", self.tactile_hz))

    @property
    def tactile_hz_source(self) -> str:
        return str(self.calibration["global"].get("tactile_hz_source", "configured"))

    @property
    def lsb_per_N(self) -> float:
        return float(self.calibration["global"]["lsb_per_N"])

    def raw_from_data(self, data: Any) -> tuple[np.ndarray, list[dict[str, object]]]:
        contacts = self.reader.read(data)
        return self.renderer.render(contacts), contacts

    def sample(self, raw_sensor_N: np.ndarray) -> np.ndarray | None:
        return self.sampler.add(raw_sensor_N)

    def detail(self, raw_sensor_N: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return self.response.apply(raw_sensor_N)


def summarize_raw(raw_sensor_N: np.ndarray) -> TactileSummary:
    magnitudes = np.linalg.norm(raw_sensor_N, axis=1)
    sensor_sums = np.asarray(
        [float(magnitudes[spec.start:spec.end].sum()) for spec in SENSOR_TABLE],
        dtype=np.float64,
    )
    total = float(sensor_sums.sum())
    if total <= 0.0:
        return TactileSummary(0.0, sensor_sums, -1, 0.0, None)

    peak_taxel = int(magnitudes.argmax())
    peak_sensor = next(spec for spec in SENSOR_TABLE if spec.start <= peak_taxel < spec.end)
    return TactileSummary(
        total_N=total,
        sensor_sums_N=sensor_sums,
        peak_taxel=peak_taxel,
        peak_taxel_N=float(magnitudes[peak_taxel]),
        peak_sensor=peak_sensor,
    )


def format_summary(time_s: float, contact_count: int, summary: TactileSummary, record: bool) -> str:
    if summary.peak_sensor is None:
        peak = "none"
    else:
        peak = f"{summary.peak_sensor.sdk_name}/{summary.peak_sensor.name}"
    sensor_bits = " ".join(
        f"{spec.sdk_name}={summary.sensor_sums_N[idx]:.4f}"
        for idx, spec in enumerate(SENSOR_TABLE)
    )
    return (
        f"time={time_s:.3f}s contacts={contact_count} total={summary.total_N:.4f}N "
        f"peak={peak} taxel={summary.peak_taxel} peak_taxel={summary.peak_taxel_N:.4f}N "
        f"record={'on' if record else 'off'} | {sensor_bits}"
    )
