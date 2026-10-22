"""Optional heatmap and CSV/JSON writers."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

from .analysis import AnalysisResult


def _heatmap_array(values: np.ndarray, positions: np.ndarray | None) -> tuple[np.ndarray, str]:
    if positions is None:
        return values.reshape(1, -1), "taxel index"
    xy = positions[:, :2]
    x_unique = np.unique(xy[:, 0])
    y_unique = np.unique(xy[:, 1])
    if len(x_unique) * len(y_unique) == len(values):
        image = np.full((len(y_unique), len(x_unique)), np.nan)
        x_idx = {v: i for i, v in enumerate(x_unique)}
        y_idx = {v: i for i, v in enumerate(y_unique)}
        for value, (x, y) in zip(values, xy):
            image[y_idx[y], x_idx[x]] = value
        return image, "taxel layout"
    return values.reshape(1, -1), "taxel index (positions not rectangular)"


def save_heatmap(result: AnalysisResult, output_path: str | Path, frame: int | str = "max") -> Path:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    values = result.taxel_force_norm
    if isinstance(frame, str):
        selected = np.max(values, axis=0) if frame == "max" else np.mean(values, axis=0)
    else:
        selected = values[int(frame)]
    image, ylabel = _heatmap_array(selected, result.taxel_positions)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig = Figure(figsize=(12, 3.5) if image.shape[0] == 1 else (7, 6))
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    im = ax.imshow(image, aspect="auto", cmap="inferno", interpolation="nearest")
    unverified = result.summary.get("analysis_mode") == "unverified_raw_diagnostic"
    ax.set_title(f"Unverified raw vector norm ({frame})" if unverified else f"Tactile force heatmap ({frame})")
    ax.set_ylabel(ylabel)
    ax.set_xlabel("taxel x / index")
    fig.colorbar(im, ax=ax, label="force norm (raw)")
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    return output


def save_frame_metrics(result: AnalysisResult, output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    names = list(result.frame_metrics)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(names)
        writer.writerows(zip(*(result.frame_metrics[name].tolist() for name in names)))
    return output


def save_summary(result: AnalysisResult, output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return output


def save_mat(result: AnalysisResult, output_path: str | Path) -> Path:
    from scipy.io import savemat

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    savemat(output, {**result.frame_metrics, "taxel_force_norm": result.taxel_force_norm, "contact_mask": result.contact_mask.astype(np.uint8)})
    return output
