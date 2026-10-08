#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from dexh13sim.taxel_template import estimate_normals


DEFAULT_SOURCE = Path("assets/dexh13_raw/dexh13_hand_right_description/mjcf_base.xml")
DEFAULT_OUT = Path("configs/taxel_templates")

TEMPLATE_SITES = {
    "IP_M3025": "right_index_ip_site",
    "MP_M2324": "right_index_mp_site",
    "DP_M2826": "right_index_dp_site",
    "IP_L5325": "thumb_pad_site",
    "DP_L3530": "thumb_tip_site",
}

EXPECTED_COUNTS = {
    "IP_M3025": 120,
    "MP_M2324": 60,
    "DP_M2826": 120,
    "IP_L5325": 120,
    "DP_L3530": 120,
}


def collect_sites(source_xml: Path, prefix: str) -> list[tuple[int, tuple[float, float, float]]]:
    root = ET.parse(source_xml).getroot()
    pattern = re.compile(rf"^{re.escape(prefix)}_p(\d+)$")
    sites: list[tuple[int, tuple[float, float, float]]] = []
    for site in root.findall(".//site"):
        name = site.get("name", "")
        match = pattern.match(name)
        if match is None:
            continue
        point_id = int(match.group(1))
        pos = tuple(float(value) for value in site.get("pos", "").split())
        if len(pos) != 3:
            raise ValueError(f"site {name} does not have a 3D pos")
        sites.append((point_id, pos))
    sites.sort(key=lambda item: item[0])
    return sites


def write_template(name: str, sites: list[tuple[int, tuple[float, float, float]]], out_dir: Path) -> None:
    expected = EXPECTED_COUNTS[name]
    if len(sites) != expected:
        raise ValueError(f"{name} expected {expected} sites, found {len(sites)}")
    if [point_id for point_id, _ in sites] != list(range(1, expected + 1)):
        raise ValueError(f"{name} site ids must be contiguous from 1")

    xyz_m = [pos for _, pos in sites]
    normals = estimate_normals(__import__("numpy").asarray(xyz_m, dtype=float))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{name}.csv"
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["taxel_id", "x_mm", "y_mm", "z_mm", "nx", "ny", "nz"])
        for taxel_id, ((_, pos_m), normal) in enumerate(zip(sites, normals)):
            writer.writerow(
                [
                    taxel_id,
                    f"{pos_m[0] * 1000.0:.6f}",
                    f"{pos_m[1] * 1000.0:.6f}",
                    f"{pos_m[2] * 1000.0:.6f}",
                    f"{normal[0]:.9f}",
                    f"{normal[1]:.9f}",
                    f"{normal[2]:.9f}",
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract DexH13 taxel template CSVs from MJCF taxel sites.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    for template_name, site_prefix in TEMPLATE_SITES.items():
        write_template(template_name, collect_sites(args.source, site_prefix), args.out_dir)
        print(f"wrote {args.out_dir / f'{template_name}.csv'}")


if __name__ == "__main__":
    main()
