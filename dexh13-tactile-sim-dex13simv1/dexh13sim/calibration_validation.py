from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from .sensor_table import SENSOR_TABLE, total_taxels
from .taxel_template import TaxelTemplate


@dataclass(frozen=True)
class CalibrationValidationReport:
    template_count: int
    sensor_count: int
    total_taxels: int
    max_vendor_error_m: float | None


def validate_calibration_assets(
    templates_dir: str | Path = "configs/taxel_templates",
    sensors_yaml: str | Path = "configs/sensors.yaml",
    vendor_templates_dir: str | Path | None = None,
) -> CalibrationValidationReport:
    templates_dir = Path(templates_dir)
    template_names = sorted({spec.template for spec in SENSOR_TABLE})
    loaded_templates: dict[str, TaxelTemplate] = {}
    for template_name in template_names:
        expected = next(spec.count for spec in SENSOR_TABLE if spec.template == template_name)
        template = TaxelTemplate.load(templates_dir / f"{template_name}.csv", template_name, expected)
        if not np.isfinite(template.xyz_m).all():
            raise ValueError(f"{template_name} contains non-finite coordinates")
        loaded_templates[template_name] = template

    payload = yaml.safe_load(Path(sensors_yaml).read_text(encoding="utf-8"))
    instances = payload["instances"]
    if len(instances) != len(SENSOR_TABLE):
        raise ValueError(f"expected {len(SENSOR_TABLE)} sensors, found {len(instances)}")
    for item in instances:
        matrix = np.asarray(item["M_sdk_sensor"], dtype=np.float64)
        if matrix.shape != (3, 3):
            raise ValueError(f"{item['name']} M_sdk_sensor must be 3x3")
        if not np.isfinite(matrix).all():
            raise ValueError(f"{item['name']} M_sdk_sensor contains non-finite values")
        if abs(float(np.linalg.det(matrix))) < 1.0e-6:
            raise ValueError(f"{item['name']} M_sdk_sensor is singular")

    max_vendor_error_m: float | None = None
    if vendor_templates_dir is not None:
        vendor_templates_dir = Path(vendor_templates_dir)
        errors = []
        for template_name, template in loaded_templates.items():
            vendor = TaxelTemplate.load(
                vendor_templates_dir / f"{template_name}.csv",
                template_name,
                len(template.xyz_m),
            )
            errors.append(float(np.max(np.abs(template.xyz_m - vendor.xyz_m))))
        max_vendor_error_m = max(errors) if errors else 0.0

    return CalibrationValidationReport(
        template_count=len(loaded_templates),
        sensor_count=len(instances),
        total_taxels=total_taxels(),
        max_vendor_error_m=max_vendor_error_m,
    )
