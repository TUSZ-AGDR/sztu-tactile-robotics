from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree


@dataclass
class TaxelTemplate:
    name: str
    xyz_m: np.ndarray
    normals: np.ndarray
    kdtree: cKDTree

    @classmethod
    def load(
        cls,
        path: str | Path,
        name: str | None = None,
        expected_count: int | None = None,
    ) -> "TaxelTemplate":
        path = Path(path)
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        if expected_count is not None and len(rows) != expected_count:
            raise ValueError(f"{path} expected {expected_count} rows, found {len(rows)}")

        taxel_ids = [int(row["taxel_id"]) for row in rows]
        if taxel_ids != list(range(len(rows))):
            raise ValueError(f"{path} taxel_id values must be contiguous from 0")

        xyz_m = np.asarray(
            [
                [float(row["x_mm"]) * 1.0e-3, float(row["y_mm"]) * 1.0e-3, float(row["z_mm"]) * 1.0e-3]
                for row in rows
            ],
            dtype=np.float64,
        )

        has_normals = rows and all(key in rows[0] for key in ("nx", "ny", "nz"))
        if has_normals:
            normals = np.asarray(
                [[float(row["nx"]), float(row["ny"]), float(row["nz"])] for row in rows],
                dtype=np.float64,
            )
        else:
            normals = estimate_normals(xyz_m)

        normals = normalize_vectors(normals, label=f"{path} normals")
        return cls(name=name or path.stem, xyz_m=xyz_m, normals=normals, kdtree=cKDTree(xyz_m))


def normalize_vectors(vectors: np.ndarray, label: str = "vectors") -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1)
    if np.any(norms <= 0):
        raise ValueError(f"{label} contain zero-length vectors")
    return vectors / norms[:, None]


def estimate_normals(xyz_m: np.ndarray, k: int = 8) -> np.ndarray:
    if len(xyz_m) < 3:
        return np.tile(np.array([0.0, 0.0, 1.0]), (len(xyz_m), 1))

    tree = cKDTree(xyz_m)
    centroid = xyz_m.mean(axis=0)
    normals = np.zeros_like(xyz_m, dtype=np.float64)
    k = min(k, len(xyz_m))
    for idx, point in enumerate(xyz_m):
        _, neighbor_idx = tree.query(point, k=k)
        neighbors = xyz_m[np.atleast_1d(neighbor_idx)]
        centered = neighbors - neighbors.mean(axis=0)
        cov = centered.T @ centered
        _, eigvecs = np.linalg.eigh(cov)
        normal = eigvecs[:, 0]
        outward = point - centroid
        if np.dot(normal, outward) < 0:
            normal = -normal
        if abs(np.dot(normal, outward)) < 1.0e-12 and normal[2] < 0:
            normal = -normal
        normals[idx] = normal
    return normalize_vectors(normals, label="estimated normals")
