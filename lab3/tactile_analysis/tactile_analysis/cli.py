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


def _frame(value):
    if value in ("max", "mean"):
        return value
    try:
        frame = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("heatmap frame must be max, mean or a non-negative integer")
    if frame < 0:
        raise argparse.ArgumentTypeError("heatmap frame must be non-negative")
    return frame


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Recording ZIP, manifest directory, or HDF5")
    parser.add_argument("--output-dir", type=Path, default=Path("analysis_out"), help="New output directory; never silently overwritten")
    parser.add_argument("--trial", help="left, right, a HDF5 trial name, or all (default: all)")
    parser.add_argument("--list-trials", action="store_true", help="Validate/read input and print quality info without analysis")
    parser.add_argument("--contact-threshold", type=float, help="Raw vector norm threshold (default: 10); not a calibrated contact threshold")
    parser.add_argument("--allow-unverified", action="store_true", help="Explicit raw diagnostics including unverified entries; forbidden for physical analysis")
    parser.add_argument("--smooth-window", type=int, default=1, help="Raw norm moving average: positive odd integer, default 1")
    parser.add_argument("--heatmap-frame", type=_frame, default="max", help="Additional raw heatmap frame: max, mean or index")
    parser.add_argument("--taxel-positions", type=Path, help="Optional verified N-by-2/3 layout.npy for raw max/mean maps")
    parser.add_argument("--taxel-area-mm2", type=float, help="Legacy scalar area proxy; requires complete source validity")
    parser.add_argument("--force-unit", choices=["raw"], default="raw", help="Raw mode never relabels counts as N; use --calibration for physical quantities")
    parser.add_argument("--calibration", type=Path, help="Measured calibration NPZ for one selected hand")
    parser.add_argument("--normal-threshold-n", type=float, help="Physical compressive normal force threshold (default: 0.1 N)")
    parser.add_argument("--export-mat", action="store_true", help="Also write analysis.mat; requires scipy")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress messages on stderr")
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
            print(json.dumps({"source": str(recording.source), "verified_npz_count": recording.verified_npz_count,
                              "trials": quality}, ensure_ascii=False, indent=2))
            return 0
        names = list(recording.trials) if args.trial in (None, "all") else [args.trial]
        if any(name not in recording.trials for name in names):
            raise ValueError(f"Unknown trial {args.trial!r}; available: {list(recording.trials)}")
        if args.calibration:
            if len(names) != 1:
                raise ValueError("Physical analysis requires one hand per calibration; pass --trial left or --trial right")
            if args.allow_unverified or args.contact_threshold is not None or args.taxel_area_mm2 is not None or args.taxel_positions or args.smooth_window != 1 or args.heatmap_frame != "max":
                raise ValueError("Physical mode does not accept raw-only options; use --normal-threshold-n and the calibration's verified areas")
            result = analyze_physical(recording.trials[names[0]], args.calibration,
                                      normal_threshold_n=args.normal_threshold_n if args.normal_threshold_n is not None else .1)
            destination = export_physical(result, args.output_dir, export_mat=args.export_mat)
            answer = {"output_dir": str(destination), "summary": result.summary}
        else:
            if args.normal_threshold_n is not None:
                raise ValueError("--normal-threshold-n requires --calibration")
            if args.taxel_positions:
                positions = np.load(args.taxel_positions, allow_pickle=False)
                for name in names:
                    recording.trials[name] = replace(recording.trials[name], taxel_positions=positions)
            answer = analyze_recording(recording, names, args.output_dir,
                        threshold=args.contact_threshold if args.contact_threshold is not None else 10,
                        smooth_window=args.smooth_window, allow_unverified=args.allow_unverified,
                        taxel_area_mm2=args.taxel_area_mm2, heatmap_frame=args.heatmap_frame,
                        export_mat=args.export_mat, progress=progress)
        print(json.dumps(answer, ensure_ascii=False, indent=2, default=str))
        return 0
    except (ValueError, KeyError, OSError, ImportError, IndexError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Analysis failed: {exc}\n")
    except KeyboardInterrupt:
        parser.exit(130, "Analysis interrupted; unfinished output was cleaned up.\n")


if __name__ == "__main__":
    raise SystemExit(main())
