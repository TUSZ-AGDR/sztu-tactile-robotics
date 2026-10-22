"""High-level file-to-artifacts pipeline."""

from __future__ import annotations

from pathlib import Path

from .analysis import AnalysisConfig, AnalysisResult, analyze_trial
from .io import load_hdf5
from .plotting import save_frame_metrics, save_heatmap, save_mat, save_summary


def analyze_hdf5(
    path: str | Path,
    *,
    config: AnalysisConfig | None = None,
    output_dir: str | Path | None = None,
    trial: str | None = None,
    heatmap_frame: int | str = "max",
    export_mat: bool = False,
) -> AnalysisResult:
    result = analyze_trial(load_hdf5(path, trial=trial), config=config)
    if output_dir is None:
        return result
    output = Path(output_dir)
    save_summary(result, output / "summary.json")
    save_frame_metrics(result, output / "frame_metrics.csv")
    try:
        save_heatmap(result, output / f"heatmap_{heatmap_frame}.png", frame=heatmap_frame)
        if heatmap_frame != "mean":
            save_heatmap(result, output / "heatmap_mean.png", frame="mean")
    except ImportError:
        (output / "heatmap_skipped.txt").write_text("Install matplotlib to export PNG heatmaps.\n", encoding="utf-8")
    if export_mat:
        save_mat(result, output / "analysis.mat")
    return result
