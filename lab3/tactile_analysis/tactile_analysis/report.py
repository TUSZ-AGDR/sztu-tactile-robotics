"""Command-line recording reports with atomic output directories."""

import json
import csv
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

from .analysis import AnalysisConfig, analyze_trial
from .convert_recording import _check_cancel
from .plotting import save_frame_metrics, save_heatmap, save_summary, save_mat
from .recording import describe_recording


def _figure(rows, cols, size):
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    fig = Figure(figsize=size, layout="constrained")
    FigureCanvasAgg(fig)
    return fig, np.asarray(fig.subplots(rows, cols, squeeze=False))


def _edges(time):
    if len(time) == 1:
        return np.array([time[0] - .5, time[0] + .5])
    return np.r_[time[0] - (time[1] - time[0]) / 2, (time[:-1] + time[1:]) / 2,
                 time[-1] + (time[-1] - time[-2]) / 2]


def _plots(recording, results, directory, cancelled=None, progress=None):
    names = list(results)
    fig, axes = _figure(3, len(names), (6.5 * len(names), 8.5))
    for col, name in enumerate(names):
        r = results[name]
        time = r.frame_metrics["time_s"]
        norm = r.taxel_force_norm
        series = (r.frame_metrics["total_contact_force"], norm.max(axis=1), (norm >= r.summary["contact_threshold"]).sum(axis=1))
        labels = ("Sum above threshold [raw]", "Peak vector norm [raw]", "Taxels above threshold")
        for row, (values, label) in enumerate(zip(series, labels)):
            axes[row, col].plot(time, values, color=("#126d86", "#cf7338", "#126d86")[row], lw=1.2)
            axes[row, col].set_ylabel(label)
            axes[row, col].grid(alpha=.15)
            axes[row, col].set_xlabel("Seconds from this hand's first frame" if r.summary["time_source"] != "frame_index" else "Frame index")
        mode = "UNVERIFIED raw" if r.summary["analysis_mode"] == "unverified_raw_diagnostic" else "raw signal"
        axes[0, col].set_title(f"{name} | {mode}")
    fig.savefig(directory / "overview.png", dpi=130)
    _check_cancel(cancelled)
    if progress:
        progress("原始波形已生成")
    fig, axes = _figure(len(names), 1, (12, 3.6 * len(names)))
    vmax = max(float(r.taxel_force_norm.max()) for r in results.values()) or 1
    for row, name in enumerate(names):
        r = results[name]
        mesh = axes[row, 0].pcolormesh(_edges(r.frame_metrics["time_s"]), np.arange(r.taxel_force_norm.shape[1] + 1) - .5,
                                     r.taxel_force_norm.T, cmap="magma", vmin=0, vmax=vmax, rasterized=True)
        axes[row, 0].set_title(f"{name} | SDK index order, not spatial geometry")
        axes[row, 0].set_ylabel("Taxel index (0-based)")
        axes[row, 0].set_xlabel("Time [s]" if r.summary["time_source"] != "frame_index" else "Frame index")
    fig.colorbar(mesh, ax=axes.ravel().tolist(), label="Vector norm [raw]")
    fig.savefig(directory / "taxel_heatmap.png", dpi=130)
    _check_cancel(cancelled)
    fig, axes = _figure(len(names), 1, (12, 3 * len(names)))
    for row, name in enumerate(names):
        trial, r = recording.trials[name], results[name]
        ax = axes[row, 0]
        if trial.sensor_forces is None:
            ax.text(.5, .5, "No sensor summary stored", ha="center", transform=ax.transAxes)
            continue
        norm = np.linalg.norm(trial.sensor_forces, axis=2)
        mesh = ax.pcolormesh(_edges(r.frame_metrics["time_s"]), np.arange(norm.shape[1] + 1) - .5,
                             norm.T, cmap="viridis", rasterized=True)
        ax.set_title(f"{name} | SDK summary vector norms [raw]")
        ax.set_ylabel("Summary index")
        ax.set_xlabel("Time [s]" if r.summary["time_source"] != "frame_index" else "Frame index")
        fig.colorbar(mesh, ax=ax)
    fig.savefig(directory / "sensor_summary.png", dpi=130)
    _check_cancel(cancelled)
    if progress:
        progress("点位和传感器汇总热力图已生成")
    fig, axes = _figure(1, len(names), (6.5 * len(names), 4.2))
    for col, name in enumerate(names):
        trial = recording.trials[name]
        side = str(trial.hand_side[0]) if trial.hand_side is not None else str(trial.metadata.get("hand_side", name))
        rows = [t for t in recording.temperatures if t["hand_side"] == side]
        ax = axes[0, col]
        if not rows:
            ax.text(.5, .5, "No temperature events stored", ha="center", transform=ax.transAxes)
        else:
            origin = int(trial.timestamps_ns[0]) if trial.timestamps_ns is not None else min(t["timestamp_ns"] for t in rows)
            for sensor in sorted({int(t["sensor_id"]) for t in rows}):
                selected = sorted((t for t in rows if t["sensor_id"] == sensor), key=lambda t: t["timestamp_ns"])
                ax.plot([(t["timestamp_ns"] - origin) / 1e9 for t in selected],
                        [t["temperature_c"] for t in selected], lw=1, label=str(sensor))
            ax.legend(title="Sensor ID", ncol=3, fontsize=7)
        ax.set_title(f"{name} | temperature events, no resampling")
        ax.set_ylabel("SDK temperature [C]")
        ax.set_xlabel("Time [s]")
        ax.grid(alpha=.15)
    fig.savefig(directory / "temperature.png", dpi=130)


def analyze_recording(recording, names, output_root, *, threshold=10.0, smooth_window=1,
                      allow_unverified=False, taxel_area_mm2=None, heatmap_frame="max",
                      export_mat=False, progress=None, cancelled=None):
    if not names or any(name not in recording.trials for name in names):
        raise ValueError("请选择有效的手别 / trial")
    config = AnalysisConfig(contact_threshold=threshold, smooth_window=smooth_window,
                            allow_unverified=allow_unverified, taxel_area_mm2=taxel_area_mm2)
    destination = Path(output_root).resolve()
    if destination.exists():
        raise FileExistsError(f"Analysis output already exists; choose a new --output-dir: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".analysis-", dir=destination.parent))
    try:
        results = {}
        for index, name in enumerate(names):
            _check_cancel(cancelled)
            trial = recording.trials[name]
            result = analyze_trial(trial, config)
            results[name] = result
            # Trial group names may contain '/', while output subfolders must not.
            folder = stage / f"trial_{index + 1:02d}"
            save_summary(result, folder / "summary.json")
            save_frame_metrics(result, folder / "frame_metrics.csv")
            save_heatmap(result, folder / "heatmap_max.png", "max")
            save_heatmap(result, folder / "heatmap_mean.png", "mean")
            if heatmap_frame not in ("max", "mean"):
                save_heatmap(result, folder / f"heatmap_{heatmap_frame}.png", heatmap_frame)
            if export_mat:
                save_mat(result, folder / "analysis.mat")
            if progress:
                progress(index + 1, len(names) + 4, f"已分析 {name}：{trial.n_frames} 帧")
        step = len(names)

        def plotted(message):
            nonlocal step
            step += 1
            if progress:
                progress(step, len(names) + 4, message)

        _plots(recording, results, stage, cancelled, plotted)
        _check_cancel(cancelled)
        report = {"source": str(recording.source), "threshold_raw": threshold,
                  "smooth_window": smooth_window, "allow_unverified": allow_unverified,
                  "trial_folders": {name: f"trial_{i + 1:02d}" for i, name in enumerate(names)},
                  "data_quality": describe_recording(recording),
                  "summaries": {name: r.summary for name, r in results.items()}}
        sides = {str(recording.trials[name].hand_side[0]) if recording.trials[name].hand_side is not None
                 else str(recording.trials[name].metadata.get("hand_side", name)) for name in names}
        rows = [row for row in recording.temperatures if row["hand_side"] in sides]
        report["temperature_summary"] = {}
        for side in sorted(sides):
            selected = [row for row in rows if row["hand_side"] == side]
            if selected:
                values = [float(row["temperature_c"]) for row in selected]
                report["temperature_summary"][side] = {"reading_count": len(values), "min_c": min(values),
                                                         "max_c": max(values), "mean_c": float(np.mean(values))}
        with (stage / "temperature_events.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["timestamp_ns", "hand_side", "finger_name", "sensor_id", "temperature_c"], extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        (stage / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        os.rename(stage, destination)
        if progress:
            progress(len(names) + 4, len(names) + 4, "分析完成，结果已保存")
        return {"output_dir": str(destination), "report": report,
                "images": {key: str(destination / file) for key, file in (
                    ("overview", "overview.png"), ("taxel", "taxel_heatmap.png"),
                    ("sensor", "sensor_summary.png"), ("temperature", "temperature.png"))}}
    finally:
        if stage.exists():
            shutil.rmtree(stage)
