"""Audit real collector streams without asserting contact or physical calibration.

Usage: python examples/audit_recording.py RECORDING_DIR --output-dir REPORT_DIR
Requires NumPy and matplotlib. Raw files are never modified.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tactile_analysis.terminal import ChineseArgumentParser, error_text, hand_name


def stats(values):
    a = np.asarray(values)
    if not a.size:
        return None
    return {k: float(v) for k, v in zip(
        ("min", "p50", "p95", "max"), np.percentile(a, [0, 50, 95, 100]))}


def nearest_offsets(source, target):
    """Signed source minus nearest target host timestamp, allowing target reuse."""
    if not len(source) or not len(target):
        return np.array([], dtype=np.float64)
    if np.any(np.diff(target) <= 0):
        raise ValueError("最近时间匹配要求目标时间戳严格递增")
    upper = np.searchsorted(target, source).clip(0, len(target) - 1)
    lower = (upper - 1).clip(0, len(target) - 1)
    idx = np.where(np.abs(source - target[lower]) <= np.abs(source - target[upper]), lower, upper)
    return (source - target[idx]) / 1e6


def load_streams(root, manifest):
    streams, audit = {}, {"files": [], "issues": []}
    for name, spec in manifest["streams"].items():
        chunks = []
        for chunk in spec["chunks"]:
            file = (root / chunk["file"]).resolve()
            if not file.is_relative_to(root.resolve()):
                raise ValueError("manifest 中的路径超出轨迹目录")
            matches = hashlib.sha256(file.read_bytes()).hexdigest() == chunk["sha256"]
            audit["files"].append({"file": file.name, "sha256_matches": matches})
            if not matches:
                raise ValueError(f"哈希校验不一致：{file.name}")
            with np.load(file, allow_pickle=False) as data:
                arrays = {k: data[k] for k in data.files}
            if set(arrays) != set(spec["fields"]):
                raise ValueError(f"字段不一致：{file.name}")
            for key, field in spec["fields"].items():
                a = arrays[key]
                if a.shape != (chunk["rows"], *field["shape"]):
                    raise ValueError(f"数组形状不一致：{file.name}:{key}")
                # Unicode storage width may vary by chunk with error message length.
                declared = np.dtype(field["dtype"])
                if a.dtype != declared and not (a.dtype.kind == declared.kind == "U"):
                    raise ValueError(f"数组类型不一致：{file.name}:{key}")
                if a.dtype.kind == "f" and not np.isfinite(a).all():
                    audit["issues"].append(f"Nonfinite values: {file.name}:{key}")
            ts = arrays["timestamp_ns"]
            if int(ts[0]) != chunk["first_timestamp_ns"] or int(ts[-1]) != chunk["last_timestamp_ns"]:
                raise ValueError(f"时间戳与 manifest 声明不一致：{file.name}")
            chunks.append(arrays)
        joined = {k: np.concatenate([a[k] for a in chunks]) for k in chunks[0]}
        if len(joined["timestamp_ns"]) != spec["rows"]:
            raise ValueError(f"行数与 manifest 声明不一致：{name}")
        if np.any(np.diff(joined["timestamp_ns"]) <= 0):
            raise ValueError(f"时间戳未严格递增：{name}")
        streams[name] = joined
    return streams, audit


def tactile_metrics(data, side, origin):
    r = data["taxel_raw"]
    if r.dtype != np.int32 or r.shape[1:] != (1140, 3):
        raise ValueError("数据必须为形状为 [T,1140,3] 的 int32 数组")
    if not np.all(data["hand_side"] == side):
        raise ValueError("手别标识不一致")
    ts = data["timestamp_ns"]
    norm = np.linalg.norm(r.astype(np.float64), axis=2)
    nonzero = np.any(r != 0, axis=2)
    counts = nonzero.sum(axis=1)
    latency = (ts - data["query_begin_ns"]) / 1e6
    if np.any(latency < 0):
        raise ValueError("查询耗时不能为负数")
    expected_valid = data["packet_valid"] & data["taxel_valid_mask"].any(axis=1)
    if not np.array_equal(expected_valid, data["sample_valid"]):
        raise ValueError("sample_valid 有效性标记不一致")
    peak_frame, peak_taxel = np.unravel_index(norm.argmax(), norm.shape)
    repeat = np.all(r[1:] == r[:-1], axis=(1, 2))
    longest, run = 1, 1
    for same in repeat:
        run = run + 1 if same else 1
        longest = max(longest, run)
    maxima = norm.max(axis=0)
    top = np.argsort(maxima)[-10:][::-1]
    result = {
        "frames": len(ts), "chunks": None,
        "start_relative_s": float((ts[0] - origin) / 1e9),
        "end_relative_s": float((ts[-1] - origin) / 1e9),
        "duration_s": float((ts[-1] - ts[0]) / 1e9),
        "effective_rate_hz": float((len(ts) - 1) * 1e9 / (ts[-1] - ts[0])),
        "interval_ms": stats(np.diff(ts) / 1e6), "query_duration_ms": stats(latency),
        "packet_valid_frames": int(data["packet_valid"].sum()),
        "sample_valid_frames": int(data["sample_valid"].sum()),
        "verified_taxel_observations": int(data["taxel_valid_mask"].sum()),
        "ever_verified_taxels": int(data["taxel_valid_mask"].any(axis=0).sum()),
        "all_zero_frames": int((counts == 0).sum()),
        "nonzero_taxels_per_frame": stats(counts),
        "ever_nonzero_taxels": int(nonzero.any(axis=0).sum()),
        "always_zero_taxels": int((~nonzero.any(axis=0)).sum()),
        "varying_taxels": int(np.any(np.ptp(r.astype(np.int64), axis=0) > 0, axis=1).sum()),
        "consecutive_identical_raw_frame_pairs": int(repeat.sum()),
        "longest_identical_frame_run": longest,
        "axis_range_counts": {axis: [int(r[:, :, i].min()), int(r[:, :, i].max())]
                              for i, axis in enumerate("xyz")},
        "z_255_frames": int((r[:, :, 2] == 255).any(axis=1).sum()),
        "byte_boundary_observations": {axis: {str(bound): int((r[:, :, i] == bound).sum())
            for bound in bounds} for i, (axis, bounds) in enumerate(zip("xyz", ((-128, 127), (-128, 127), (255,))))},
        "peak_vector_norm_raw": float(norm[peak_frame, peak_taxel]),
        "peak_frame_index": int(peak_frame), "peak_taxel_index": int(peak_taxel),
        "peak_time_relative_s": float((ts[peak_frame] - origin) / 1e9),
        "peak_vector_raw": r[peak_frame, peak_taxel].tolist(),
        "top_taxels": [{"index": int(i), "peak_norm_raw": float(maxima[i]),
                        "nonzero_frame_fraction": float(nonzero[:, i].mean())} for i in top],
        "threshold_sensitivity": {str(th): {"mean_exceeding_taxels": float((norm >= th).sum(axis=1).mean()),
            "peak_exceeding_taxels": int((norm >= th).sum(axis=1).max())} for th in (1, 5, 10, 20, 50, 100)},
        "physical_contact_metrics": None,
        "physical_contact_metrics_reason": "No verified taxels; force, axes and geometry uncalibrated",
    }
    sensor = data["sensor_summary_raw"]
    result["sensor_summary_raw"] = {
        "axis_range_counts": {axis: [int(sensor[:, :, i].min()), int(sensor[:, :, i].max())]
                              for i, axis in enumerate("xyz")},
        "ever_nonzero_sensor_indices": np.flatnonzero(np.any(sensor != 0, axis=(0, 2))).tolist(),
        "per_sensor_peak_norm_raw": np.linalg.norm(sensor.astype(float), axis=2).max(axis=0).tolist(),
    }
    derived = {"timestamp_ns": ts, "time_relative_s": (ts - origin) / 1e9,
               "raw_vector_norm": norm, "raw_norm_sum": norm.sum(axis=1),
               "raw_peak_norm": norm.max(axis=1), "nonzero_taxel_count": counts,
               "query_duration_ms": latency, "packet_valid": data["packet_valid"],
               "sample_valid": data["sample_valid"], "taxel_valid_mask": data["taxel_valid_mask"]}
    return result, derived


def plot_report(streams, derived, temperatures, origin, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import PowerNorm
    fig, axes = plt.subplots(4, 2, figsize=(14, 12), constrained_layout=True, sharex="col")
    for col, side in enumerate(("left", "right")):
        d = derived[side]
        time = d["time_relative_s"]
        axes[0, col].plot(time, d["raw_norm_sum"], lw=1, color="#196b91")
        axes[0, col].set_title(f"{side.title()}: raw diagnostics, all taxels UNVERIFIED")
        axes[0, col].set_ylabel("Sum of vector norms [raw]")
        axes[1, col].plot(time, d["raw_peak_norm"], lw=1, color="#bf5a32")
        axes[1, col].set_ylabel("Peak vector norm [raw]")
        axes[2, col].plot(time, d["nonzero_taxel_count"], lw=1, color="#196b91")
        axes[2, col].set_ylabel("Nonzero taxels (not contact)")
        axes[3, col].plot(time[1:], np.diff(d["timestamp_ns"]) / 1e6, label="Frame interval", lw=1)
        axes[3, col].plot(time, d["query_duration_ms"], label="Tactile query", lw=1)
        axes[3, col].set_ylabel("Duration [ms]")
        axes[3, col].set_xlabel("Host monotonic seconds since recording start")
        axes[3, col].legend(fontsize=8)
        for ax in axes[:, col]:
            ax.grid(alpha=.2)
    fig.savefig(out / "raw_overview.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), constrained_layout=True)
    vmax = max(float(d["raw_vector_norm"].max()) for d in derived.values())
    for ax, side in zip(axes, ("left", "right")):
        d = derived[side]
        # Each column uses its actual host-time bounds; no uniform-rate assumption.
        t = d["time_relative_s"]
        edges = np.r_[t[0] - (t[1] - t[0]) / 2, (t[:-1] + t[1:]) / 2,
                      t[-1] + (t[-1] - t[-2]) / 2]
        mesh = ax.pcolormesh(edges, np.arange(1141) - .5, d["raw_vector_norm"].T,
                            norm=PowerNorm(.5, vmin=0, vmax=vmax), cmap="magma", rasterized=True)
        ax.set_title(f"{side.title()} - taxel index order only; UNVERIFIED data")
        ax.set_ylabel("SDK taxel index (0-based)")
        ax.set_xlabel("Seconds since recording start")
    fig.colorbar(mesh, ax=axes, label="Vector norm [raw counts], sqrt color scale")
    fig.savefig(out / "taxel_index_heatmap.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(14, 4), constrained_layout=True)
    for ax, side in zip(axes, ("left", "right")):
        rows = [r for r in temperatures if r["hand_side"] == side]
        for sensor in sorted({r["sensor_id"] for r in rows}):
            selected = sorted((r for r in rows if r["sensor_id"] == sensor), key=lambda r: r["timestamp_ns"])
            ax.plot([(r["timestamp_ns"] - origin) / 1e9 for r in selected],
                    [r["temperature_c"] for r in selected], lw=1, label=f"sensor {sensor}")
        ax.set_title(f"{side.title()} temperatures (event timestamps)")
        ax.set_xlabel("Seconds since recording start")
        ax.set_ylabel("SDK temperature [C]")
        ax.grid(alpha=.2)
        ax.legend(ncol=3, fontsize=7)
    fig.savefig(out / "temperature.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(2, 3, figsize=(15, 7), constrained_layout=True)
    for row, side in enumerate(("left", "right")):
        sensor = streams[side + "_tactile"]["sensor_summary_raw"]
        t = derived[side]["time_relative_s"]
        edges = np.r_[t[0] - (t[1] - t[0]) / 2, (t[:-1] + t[1:]) / 2,
                      t[-1] + (t[-1] - t[-2]) / 2]
        for col, axis in enumerate("xyz"):
            mesh = axes[row, col].pcolormesh(edges, np.arange(12) - .5, sensor[:, :, col].T,
                                           cmap="RdBu_r", vmin=-255, vmax=255, rasterized=True)
            axes[row, col].set_title(f"{side.title()} SDK sensor summary: {axis}")
            axes[row, col].set_xlabel("Seconds since recording start")
            axes[row, col].set_ylabel("SDK summary index (0-based)")
            axes[row, col].set_yticks(range(11))
    fig.colorbar(mesh, ax=axes, label="Signed SDK summary [raw counts]; uncalibrated")
    fig.savefig(out / "sensor_summary_axes.png", dpi=150)
    plt.close(fig)


def audit_recording(args):
    root, out = args.recording_dir.resolve(), args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((root / "manifest.json").read_text())
    streams, audit = load_streams(root, manifest)
    events = [json.loads(line) for line in (root / manifest["events_file"]).read_text().splitlines() if line.strip()]
    origin = int(manifest["metadata"]["recording_begin_monotonic_ns"])
    temperatures = [{"timestamp_ns": e["timestamp_ns"], "hand_side": e["hand_side"], **r}
                    for e in events if e["event"] == "temperature_reading" for r in e["readings"]]
    summary = {"trajectory_id": manifest["trajectory_id"], "source_dir": str(root),
               "created_utc": manifest["created_utc"], "status": manifest["status"],
               "end_reason": manifest["end_reason"], "recording_error": manifest["recording_error"],
               "training_eligible": manifest["metadata"]["training_eligible"],
               "archive_sha256": None, "integrity": audit, "streams": {}, "tactile": {},
               "events": dict(Counter(e["event"] for e in events)), "temperature": {}}
    archive = root.with_suffix(".zip")
    if archive.exists():
        summary["archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    for name, data in streams.items():
        ts = data["timestamp_ns"]
        s = {"frames": len(ts), "chunks": len(manifest["streams"][name]["chunks"]),
             "start_relative_s": float((ts[0] - origin) / 1e9),
             "end_relative_s": float((ts[-1] - origin) / 1e9),
             "duration_s": float((ts[-1] - ts[0]) / 1e9),
             "effective_rate_hz": float((len(ts) - 1) * 1e9 / (ts[-1] - ts[0])),
             "interval_ms": stats(np.diff(ts) / 1e6)}
        s["boolean_fields"] = {k: {"true": int(v.sum()), "total": int(v.size)}
                               for k, v in data.items() if v.dtype.kind == "b"}
        summary["streams"][name] = s
    derived = {}
    for side in ("left", "right"):
        s, derived[side] = tactile_metrics(streams[side + "_tactile"], side, origin)
        s["chunks"] = len(manifest["streams"][side + "_tactile"]["chunks"])
        ts = streams[side + "_tactile"]["timestamp_ns"]
        s["nearest_hand_state_abs_offset_ms"] = stats(np.abs(nearest_offsets(ts, streams[side + "_hand_state"]["timestamp_ns"])))
        s["nearest_arm_state_abs_offset_ms"] = stats(np.abs(nearest_offsets(ts, streams[side + "_arm_state"]["timestamp_ns"])))
        rows = [r for r in temperatures if r["hand_side"] == side]
        temp = {"event_count": sum(e["event"] == "temperature_reading" and e["hand_side"] == side for e in events),
                "reading_count": len(rows), "range_c": [min(r["temperature_c"] for r in rows), max(r["temperature_c"] for r in rows)],
                "sensors": {}}
        for sensor in sorted({r["sensor_id"] for r in rows}):
            selected = sorted((r for r in rows if r["sensor_id"] == sensor), key=lambda r: r["timestamp_ns"])
            values = [r["temperature_c"] for r in selected]
            temp["sensors"][str(sensor)] = {"finger_name": selected[0]["finger_name"], "range_c": [min(values), max(values)],
                                           "start_c": values[0], "end_c": values[-1]}
        summary["temperature"][side] = temp
        summary["tactile"][side] = s
        np.savez_compressed(out / f"{side}_raw_diagnostics.npz", **derived[side])
    offsets = nearest_offsets(streams["left_tactile"]["timestamp_ns"], streams["right_tactile"]["timestamp_ns"])
    summary["left_to_nearest_right_abs_offset_ms"] = stats(np.abs(offsets))
    summary["events_global_timestamp_reversals"] = int(sum(b["timestamp_ns"] < a["timestamp_ns"] for a, b in zip(events, events[1:])))
    summary["events_before_recording_origin"] = int(sum(e["timestamp_ns"] < origin for e in events))
    (out / "audit_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    plot_report(streams, derived, temperatures, origin, out)
    return {"output_dir": str(out), "hashes_checked": len(audit["files"]),
                      "issues": audit["issues"], "tactile": summary["tactile"],
                      "temperature": summary["temperature"],
                      "nearest_hands_abs_offset_ms": summary["left_to_nearest_right_abs_offset_ms"]}


def main(argv=None):
    parser = ChineseArgumentParser(description="检查真实采集目录的完整性、原始信号、温度与采样时序，不认定物理接触。")
    parser.add_argument("recording_dir", type=Path, help="解压后的采集轨迹目录")
    parser.add_argument("--output-dir", type=Path, required=True, help="诊断报告输出目录")
    parser.add_argument("--json", action="store_true", help="以原有字段输出机器可读 JSON；默认显示中文诊断摘要")
    args = parser.parse_args(argv)
    try:
        result = audit_recording(args)
    except (OSError, ValueError, KeyError, ImportError, IndexError) as exc:
        parser.exit(1, f"诊断失败：{error_text(exc)}\n")
    except KeyboardInterrupt:
        parser.exit(130, "诊断已中断，请检查输出目录中已生成的文件。\n")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"诊断完成，结果目录：{result['output_dir']}")
        print(f"已校验文件哈希：{result['hashes_checked']} 个")
        print(f"完整性检查发现的问题：{len(result['issues'])} 项；详情见 audit_summary.json")
        for side, row in result["tactile"].items():
            print(f"{hand_name(side)}：{row['frames']} 帧；曾出现非零原值的触觉点 {row['ever_nonzero_taxels']} 个")
        print("图表仅用于未验证原始信号诊断，不能据此报告物理接触、压力或面积。")


if __name__ == "__main__":
    main()
