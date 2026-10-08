"""CLI: python lab2/run.py [--headless] [--compare]."""
from pathlib import Path
import argparse
import shutil
import subprocess
import sys
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lab2 import Experiment, ExperimentConfig
from lab2.results import save_comparison


def ensure_macos_gui(headless):
    if headless:
        return
    from lab2.viewer import check_display
    check_display()
    if sys.platform != "darwin":
        return
    from mujoco import viewer
    if getattr(viewer, "_MJPYTHON", None) is not None:
        return
    executable = Path(sys.executable).parent / "mjpython"
    launcher = str(executable) if executable.exists() else shutil.which("mjpython")
    if launcher is None:
        raise RuntimeError("macOS GUI requires mjpython. Install lab2/requirements.txt in the active environment.")
    raise SystemExit(subprocess.call([launcher, str(Path(sys.argv[0]).resolve()), *sys.argv[1:]]))


def main(argv=None, config=None):
    config = config or ExperimentConfig()
    parser = argparse.ArgumentParser(description="Lab 2: fixed closure vs tactile feedback")
    parser.add_argument("--controller", choices=("fixed", "tactile", "student"), default="tactile")
    parser.add_argument("--object", dest="object_name", choices=("box", "cylinder", "sphere"), default=config.object_name)
    parser.add_argument("--target-force", dest="target_force_N", type=float, default=config.target_force_N)
    parser.add_argument("--mass", dest="mass_kg", type=float, default=config.mass_kg)
    parser.add_argument("--friction", type=float, default=config.friction)
    parser.add_argument("--fixed-closure", type=float, default=config.fixed_closure)
    parser.add_argument("--gain", dest="controller_gain", type=float, default=config.controller_gain)
    parser.add_argument("--noise", dest="noise_std_N", type=float, default=config.noise_std_N)
    parser.add_argument("--seed", type=int, default=config.seed)
    parser.add_argument("--pull-force", dest="pull_force_N", type=float, default=config.pull_force_N)
    parser.add_argument("--disturbance", action=argparse.BooleanOptionalAction, default=config.disturbance)
    parser.add_argument("--headless", action="store_true", help="Run without graphics; still save curves")
    parser.add_argument("--compare", action="store_true", help="Run both baselines headlessly under identical conditions")
    parser.add_argument("--include-student", action="store_true", help="Also compare student_policy.py")
    parser.add_argument("--close-on-finish", action="store_true")
    parser.add_argument("--out", type=Path, help="Result folder; default is a new lab2/outputs run")
    args = parser.parse_args(argv)
    parameters = {key: getattr(args, key) for key in (
        "object_name", "target_force_N", "mass_kg", "friction", "fixed_closure",
        "controller_gain", "noise_std_N", "seed", "pull_force_N", "disturbance")}
    from dataclasses import replace
    config = replace(config, **parameters)
    headless = args.headless or args.compare
    ensure_macos_gui(headless)
    output = args.out or Path(__file__).resolve().parent / "outputs" / f"{config.object_name}-{uuid.uuid4().hex[:8]}"
    output = output.resolve()
    if args.compare:
        controllers = ["fixed", "tactile"]
        if args.include_student:
            controllers.append("student")
    else:
        controllers = [args.controller]
    results = []
    for name in controllers:
        controller = name
        if name == "student":
            from lab2.student_policy import policy
            controller = policy
        result = Experiment(config).run(controller, headless=headless,
                    output_dir=output / name, keep_open=not args.close_on_finish)
        if name == "student":
            result.controller = "student"
            result.save(output / name)
            from lab2.viewer import plot_episode, plot_heatmap
            plot_episode(result, output / name / "curves.png")
            plot_heatmap(result, output / name / "heatmap.png")
        print(result.describe())
        results.append(result)
    if args.compare:
        save_comparison(results, output)
    print(f"Results: {output}")
    return results


if __name__ == "__main__":
    main()
