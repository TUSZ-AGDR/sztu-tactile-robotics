"""One CLI for ZIP/directory/HDF5 raw reports and calibrated physical analysis."""

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import zipfile

import numpy as np

from .physical import analyze_physical, export_physical
from .recording import describe_recording, load_recording
from .report import analyze_recording
from .terminal import ChineseArgumentParser, error_text, print_analysis, print_quality


def _frame(value):
    if value in ("max", "mean"):
        return value
    try:
        frame = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("热力图帧必须为 max、mean 或非负整数")
    if frame < 0:
        raise argparse.ArgumentTypeError("热力图帧号不能为负数")
    return frame


def _parser():
    parser = ChineseArgumentParser(description="分析 DexH13 触觉 ZIP、轨迹目录或 HDF5，生成原始信号诊断或标定后的物理量报告。")
    parser.add_argument("input", type=Path, help="采集 ZIP、包含 manifest.json 的轨迹目录或 HDF5 文件")
    parser.add_argument("--output-dir", type=Path, default=Path("analysis_out"), help="新的输出目录；不会静默覆盖已有结果")
    parser.add_argument("--trial", help="选择 left（左手）、right（右手）、HDF5 数据组名或 all（全部，默认）")
    parser.add_argument("--list-trials", action="store_true", help="校验并读取输入，显示各数据组质量信息，不生成分析报告")
    parser.add_argument("--contact-threshold", type=float, help="原始三轴模长阈值（默认 10），不是标定后的接触阈值")
    parser.add_argument("--allow-unverified", action="store_true", help="显式允许包含未验证条目的原始诊断；物理分析禁止使用")
    parser.add_argument("--smooth-window", type=int, default=1, help="原始模长滑动平均窗口：正奇数，默认 1")
    parser.add_argument("--heatmap-frame", type=_frame, default="max", help="额外原始热力图：max（最大值）、mean（均值）或帧号")
    parser.add_argument("--taxel-positions", type=Path, help="可选的已验证点位布局 .npy，形状为 [N,2] 或 [N,3]，用于原始最大值或均值图")
    parser.add_argument("--taxel-area-mm2", type=float, help="旧版标量面积估计；要求源数据全部有效")
    parser.add_argument("--force-unit", choices=["raw"], default="raw", help="原始模式保留计数单位；物理量分析请使用 --calibration")
    parser.add_argument("--calibration", type=Path, help="所选单手的实测标定 NPZ 文件")
    parser.add_argument("--normal-threshold-n", type=float, help="物理模式的压缩法向力阈值（默认 0.1 N）")
    parser.add_argument("--export-mat", action="store_true", help="同时导出 analysis.mat，需要安装 scipy")
    parser.add_argument("--quiet", action="store_true", help="关闭标准错误流中的进度提示")
    parser.add_argument("--json", action="store_true", help="以原有字段输出机器可读 JSON；默认显示中文结果摘要")
    return parser


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)

    def progress(done, total, message):
        if not args.quiet:
            print(f"[{done}/{total}] {message}", file=sys.stderr)

    try:
        recording = load_recording(args.input, progress=progress)
        quality = describe_recording(recording)
        if args.list_trials:
            info = {"source": str(recording.source), "verified_npz_count": recording.verified_npz_count, "trials": quality}
            if args.json:
                print(json.dumps(info, ensure_ascii=False, indent=2))
            else:
                print_quality(info)
            return 0
        names = list(recording.trials) if args.trial in (None, "all") else [args.trial]
        if any(name not in recording.trials for name in names):
            raise ValueError(f"未知数据组 {args.trial!r}；可用数据组：{list(recording.trials)}")
        if args.calibration:
            if len(names) != 1:
                raise ValueError("每份标定只能分析一只手；请指定 --trial left 或 --trial right")
            if args.allow_unverified or args.contact_threshold is not None or args.taxel_area_mm2 is not None or args.taxel_positions or args.smooth_window != 1 or args.heatmap_frame != "max":
                raise ValueError("物理模式不接受仅用于原始诊断的参数；请使用 --normal-threshold-n 和标定文件中已验证的点面积")
            result = analyze_physical(recording.trials[names[0]], args.calibration,
                                      normal_threshold_n=args.normal_threshold_n if args.normal_threshold_n is not None else .1)
            destination = export_physical(result, args.output_dir, export_mat=args.export_mat)
            answer = {"output_dir": str(destination), "summary": result.summary}
        else:
            if args.normal_threshold_n is not None:
                raise ValueError("使用 --normal-threshold-n 时必须同时提供 --calibration")
            if args.taxel_positions:
                positions = np.load(args.taxel_positions, allow_pickle=False)
                for name in names:
                    recording.trials[name] = replace(recording.trials[name], taxel_positions=positions)
            answer = analyze_recording(recording, names, args.output_dir,
                        threshold=args.contact_threshold if args.contact_threshold is not None else 10,
                        smooth_window=args.smooth_window, allow_unverified=args.allow_unverified,
                        taxel_area_mm2=args.taxel_area_mm2, heatmap_frame=args.heatmap_frame,
                        export_mat=args.export_mat, progress=progress)
        if args.json:
            print(json.dumps(answer, ensure_ascii=False, indent=2, default=str))
        else:
            print_analysis(answer)
        return 0
    except (ValueError, KeyError, OSError, ImportError, IndexError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"分析失败：{error_text(exc)}\n")
    except KeyboardInterrupt:
        parser.exit(130, "分析已中断，未完成的输出已清理。\n")


if __name__ == "__main__":
    raise SystemExit(main())
