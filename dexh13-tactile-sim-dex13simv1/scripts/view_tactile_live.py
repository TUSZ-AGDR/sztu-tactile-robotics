#!/usr/bin/env python
from __future__ import annotations

import argparse
from collections import deque
import select
import sys
import termios
import time
import tty
from pathlib import Path

import mujoco
import numpy as np

from dexh13sim.dataset_writer import DatasetWriter
from dexh13sim.hand_control import POLICY_NAMES, ScriptedHandPolicy, apply_action
from dexh13sim.interactive_control import DEFAULT_PROBE_Z, ManualControlState, apply_manual_control, handle_manual_key, hold_current_manual_target, manual_help
from dexh13sim.object_control import (
    DEFAULT_OBJECT_BODY,
    DEFAULT_OBJECT_POS,
    ObjectControlState,
    apply_object_control,
    halt_object_motion,
    handle_object_key,
    object_help,
    sync_object_control_to_mocap_target,
    sync_object_control_to_body,
    target_body_name_for,
    viewer_is_perturbing_body,
)
from dexh13sim.pose_capture import PoseCapture
from dexh13sim.runtime import TactileRuntime, format_summary, summarize_raw
from dexh13sim.sensor_table import total_taxels
from dexh13sim.taxel_overlay import TaxelHeatmapOverlay


DRAG_TARGET_GEOM_NAME = "free_sphere_target_geom"
DRAG_TARGET_VISIBLE_ALPHA = 0.45
DEFAULT_VIEWER_SCENE = Path("assets/dexh13_mjcf/free_object_scene.xml")


class TerminalKeyReader:
    def __init__(self, enabled: bool):
        self.enabled = bool(enabled and sys.stdin.isatty())
        self._fd: int | None = None
        self._old_attrs: list[object] | None = None

    def __enter__(self) -> "TerminalKeyReader":
        if self.enabled:
            self._fd = sys.stdin.fileno()
            self._old_attrs = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.enabled and self._fd is not None and self._old_attrs is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_attrs)

    def read_keys(self) -> list[str]:
        if not self.enabled:
            return []
        keys: list[str] = []
        while select.select([sys.stdin], [], [], 0.0)[0]:
            keys.append(sys.stdin.read(1))
        return keys


def keycode_to_control_key(keycode: int) -> str:
    if ord("A") <= int(keycode) <= ord("Z"):
        return chr(int(keycode)).lower()
    if 32 <= int(keycode) <= 126:
        return chr(int(keycode))
    return ""


class ViewerKeyQueue:
    def __init__(self) -> None:
        self._keys: deque[str] = deque()

    def callback(self, keycode: int) -> None:
        key = keycode_to_control_key(keycode)
        if key:
            self._keys.append(key)

    def read_keys(self) -> list[str]:
        keys = list(self._keys)
        self._keys.clear()
        return keys


def set_drag_target_visibility(model: mujoco.MjModel, visible: bool) -> bool:
    geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, DRAG_TARGET_GEOM_NAME)
    if geom_id < 0:
        return False
    model.geom_rgba[geom_id, 3] = DRAG_TARGET_VISIBLE_ALPHA if visible else 0.0
    return True


def has_body(model: mujoco.MjModel, body_name: str) -> bool:
    return mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name) >= 0


def select_body_for_mouse_perturb(viewer: object | None, model: mujoco.MjModel, body_name: str) -> bool:
    if viewer is None or getattr(viewer, "perturb", None) is None:
        return False
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name)
    if body_id < 0:
        return False
    viewer.perturb.select = body_id
    return True


def sync_taxel_overlay(viewer: object | None, overlay: TaxelHeatmapOverlay | None, data: mujoco.MjData, raw_sensor_N: np.ndarray) -> bool:
    if viewer is None or overlay is None or getattr(viewer, "user_scn", None) is None:
        return False
    with viewer.lock():
        overlay.update_scene(viewer.user_scn, data, raw_sensor_N)
    return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live DexH13 tactile viewer and terminal monitor.")
    parser.add_argument("--mjcf", type=Path, default=DEFAULT_VIEWER_SCENE)
    parser.add_argument("--calibration", type=Path, default=Path("configs/calibration.yaml"))
    parser.add_argument("--headless", action="store_true", help="Run without opening the MuJoCo viewer.")
    parser.add_argument("--steps", type=int, default=None, help="Number of MuJoCo steps to run. Viewer mode runs until closed by default.")
    parser.add_argument("--record", type=Path, default=None, help="Optional HDF5 output path. Defaults to no saving.")
    parser.add_argument("--objects", nargs="*", default=None, help="MuJoCo body names to record when --record is set.")
    parser.add_argument("--print-every", type=int, default=1, help="Print every N tactile frames.")
    parser.add_argument("--realtime", action="store_true", help="Sleep between steps to approximate real time in headless mode.")
    parser.add_argument("--policy", choices=POLICY_NAMES, default="hold_open", help="Scripted 16-DoF hand control policy.")
    parser.add_argument("--policy-amplitude", type=float, default=0.45, help="Policy amplitude as a 0..1 fraction of joint control range.")
    parser.add_argument("--policy-period", type=float, default=2.0, help="Policy cycle period in seconds.")
    parser.add_argument("--manual", action=argparse.BooleanOptionalAction, default=True, help="Use terminal keyboard/manual hand control. Enabled by default for live viewing.")
    parser.add_argument("--manual-mode", choices=("jog", "position"), default="jog", help="Manual hand semantics: jog stops on release; position keeps chasing the last target.")
    parser.add_argument("--manual-hold-timeout", type=float, default=0.08, help="Seconds after the last hand jog key before the target is locked to the current pose.")
    parser.add_argument("--manual-close", type=float, default=0.0, help="Initial manual hand close fraction, 0 open to 1 closed.")
    parser.add_argument("--manual-probe-z", type=float, default=DEFAULT_PROBE_Z, help="Initial manual press probe slide joint position.")
    parser.add_argument("--object-control", action=argparse.BooleanOptionalAction, default=True, help="Use keyboard/mouse-compatible physical-drag control for a freejoint object. Enabled by default.")
    parser.add_argument("--object-body", default=DEFAULT_OBJECT_BODY, help="Freejoint object body name controlled by --object-control.")
    parser.add_argument("--object-x", type=float, default=DEFAULT_OBJECT_POS[0], help="Initial controlled object x position.")
    parser.add_argument("--object-y", type=float, default=DEFAULT_OBJECT_POS[1], help="Initial controlled object y position.")
    parser.add_argument("--object-z", type=float, default=DEFAULT_OBJECT_POS[2], help="Initial controlled object z position.")
    parser.add_argument("--object-step", type=float, default=0.004, help="Controlled object keyboard step in meters.")
    parser.add_argument("--object-hold-timeout", type=float, default=0.20, help="Seconds after the last object jog key before the drag target is locked to the current object pose.")
    parser.add_argument("--show-drag-target", action="store_true", help="Show the yellow mocap drag target used by --object-control.")
    parser.add_argument("--preselect-drag-target", action=argparse.BooleanOptionalAction, default=True, help="Preselect the hidden mocap drag target for MuJoCo mouse perturbing. Enabled by default; use --no-preselect-drag-target to hide MuJoCo's perturb marker.")
    parser.add_argument("--taxel-overlay", action=argparse.BooleanOptionalAction, default=True, help="Draw a live taxel heatmap overlay in the MuJoCo viewer. Enabled by default.")
    parser.add_argument("--taxel-overlay-stride", type=int, default=1, help="Draw every Nth taxel when --taxel-overlay is enabled.")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    model = mujoco.MjModel.from_xml_path(str(args.mjcf))
    set_drag_target_visibility(model, args.show_drag_target)
    data = mujoco.MjData(model)
    runtime = TactileRuntime(model, calibration_yaml=args.calibration)
    object_control_enabled = bool(args.object_control and has_body(model, args.object_body) and has_body(model, f"{args.object_body}_target"))
    overlay_enabled = bool(args.taxel_overlay and not args.headless)
    overlay = TaxelHeatmapOverlay(runtime.mount, runtime.templates, stride=args.taxel_overlay_stride) if overlay_enabled else None
    if args.objects is None:
        if object_control_enabled:
            args.objects = [args.object_body]
        elif mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "press_probe") >= 0:
            args.objects = ["press_probe"]
        elif mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, DEFAULT_OBJECT_BODY) >= 0:
            args.objects = [DEFAULT_OBJECT_BODY]
        else:
            args.objects = []
    pose_capture = PoseCapture(model, runtime.mount, args.objects)
    policy = ScriptedHandPolicy(
        model,
        name=args.policy,
        amplitude=args.policy_amplitude,
        period_s=args.policy_period,
    )
    manual_state = ManualControlState(close=args.manual_close, probe_z=args.manual_probe_z).clipped()
    object_state = ObjectControlState(
        body_name=args.object_body,
        pos=(args.object_x, args.object_y, args.object_z),
        step=args.object_step,
    ).normalized()
    object_target_body = target_body_name_for(args.object_body)
    control_mode = "manual" if args.manual else "policy"
    if object_control_enabled:
        control_mode = f"{control_mode}+object"

    if args.headless and args.steps is None:
        args.steps = int(5.0 / runtime.sim_dt)

    metadata = {
        "sim_dt": runtime.sim_dt,
        "sensor_native_hz": runtime.sensor_native_hz,
        "tactile_hz": runtime.tactile_hz,
        "tactile_hz_source": runtime.tactile_hz_source,
        "lsb_per_N": runtime.lsb_per_N,
        "mjcf_path": str(args.mjcf),
        "calibration_path": str(args.calibration),
        "mode": "live",
        "object_names": ",".join(args.objects),
        "policy": args.policy,
        "policy_amplitude": args.policy_amplitude,
        "policy_period_s": args.policy_period,
        "control_mode": control_mode,
        "manual_close": manual_state.close,
        "manual_mode": args.manual_mode,
        "manual_hold_timeout": args.manual_hold_timeout,
        "manual_probe_z": manual_state.probe_z,
        "object_control": bool(object_control_enabled),
        "object_control_mode": "physical_drag" if object_control_enabled else "none",
        "object_body": args.object_body,
        "object_step": object_state.step,
        "object_hold_timeout": args.object_hold_timeout,
    }
    writer_context = DatasetWriter(args.record, metadata) if args.record else None
    writer = writer_context.__enter__() if writer_context is not None else None

    viewer = None
    viewer_keys = ViewerKeyQueue()
    if not args.headless:
        from mujoco import viewer as mujoco_viewer

        try:
            viewer = mujoco_viewer.launch_passive(model, data, key_callback=viewer_keys.callback)
        except RuntimeError as exc:
            if sys.platform == "darwin" and "mjpython" in str(exc):
                mjpython = Path(sys.executable).with_name("mjpython")
                command = f"{mjpython} scripts/view_tactile_live.py" if mjpython.exists() else "mjpython scripts/view_tactile_live.py"
                raise SystemExit(
                    "ERROR: MuJoCo passive viewer requires mjpython on macOS. "
                    f"Run `{command}` for GUI live viewing, or add `--headless` when using regular python."
                )
            raise
        if object_control_enabled and args.preselect_drag_target:
            with viewer.lock():
                select_body_for_mouse_perturb(viewer, model, object_target_body)

    print(
        f"DexH13 live tactile monitor started record={'on' if args.record else 'off'} "
        f"mjcf={args.mjcf} policy={args.policy} control_mode={control_mode} taxel_overlay={'on' if overlay else 'off'}",
        flush=True,
    )
    if args.manual:
        print(manual_help(), flush=True)
    if args.object_control and not object_control_enabled:
        print(f"object control disabled; {args.object_body} or {args.object_body}_target is not in {args.mjcf}", flush=True)
    if object_control_enabled:
        print(object_help(), flush=True)
        if not args.show_drag_target:
            print("drag target hidden and preselected for mouse perturbing; use Ctrl+right-drag in MuJoCo to move it. Add --no-preselect-drag-target to disable the perturb marker.", flush=True)

    keyboard = TerminalKeyReader(enabled=args.manual or object_control_enabled)
    steps = 0
    tactile_frames = 0
    max_contact_count = 0
    latest_overlay_raw = np.zeros((total_taxels(), 3), dtype=np.float32)
    hand_jog_active = False
    last_hand_jog_key_time: float | None = None
    object_jog_active = False
    last_object_jog_key_time: float | None = None
    try:
        with keyboard:
            while True:
                if args.steps is not None and steps >= args.steps:
                    break
                if viewer is not None and not viewer.is_running():
                    break

                start = time.perf_counter()
                keys = keyboard.read_keys() + viewer_keys.read_keys()
                hand_jog_key_seen = False
                object_jog_key_seen = False
                for key in keys:
                    if args.manual:
                        if key in {"c", "o", "a", "s"}:
                            hand_jog_key_seen = True
                        manual_state = handle_manual_key(manual_state, key)
                    if object_control_enabled:
                        if key in {"h", "l", "k", "i", "n", "m"}:
                            object_jog_key_seen = True
                        object_state = handle_object_key(object_state, key)
                if manual_state.quit_requested:
                    break
                if args.manual and args.manual_mode == "jog":
                    now = time.perf_counter()
                    if hand_jog_key_seen:
                        hand_jog_active = True
                        last_hand_jog_key_time = now
                    elif (
                        hand_jog_active
                        and last_hand_jog_key_time is not None
                        and now - last_hand_jog_key_time >= max(0.0, args.manual_hold_timeout)
                    ):
                        manual_state = hold_current_manual_target(model, data, manual_state)
                        hand_jog_active = False
                if object_control_enabled:
                    now = time.perf_counter()
                    if object_jog_key_seen:
                        object_jog_active = True
                        last_object_jog_key_time = now
                    elif (
                        object_jog_active
                        and last_object_jog_key_time is not None
                        and now - last_object_jog_key_time >= max(0.0, args.object_hold_timeout)
                    ):
                        object_state = halt_object_motion(model, data, object_state)
                        object_jog_active = False

                if args.manual:
                    action = apply_manual_control(model, data, manual_state)
                else:
                    action = apply_action(model, data, policy.action(float(data.time)))
                if object_control_enabled:
                    object_state = apply_object_control(model, data, object_state)

                mujoco.mj_step(model, data)
                raw, contacts = runtime.raw_from_data(data)
                max_contact_count = max(max_contact_count, len(contacts))
                sampled = runtime.sample(raw)
                steps += 1

                if sampled is not None:
                    latest_overlay_raw = sampled
                    tactile_frames += 1
                    detail_N, detail_sdk = runtime.detail(sampled)
                    summary = summarize_raw(sampled)
                    line = format_summary(float(data.time), max_contact_count, summary, bool(args.record))
                    if args.manual:
                        line = f"{line} manual_close={manual_state.close:.2f} probe_z={manual_state.probe_z:.4f}"
                    if object_control_enabled:
                        line = f"{line} target=({object_state.pos[0]:.3f},{object_state.pos[1]:.3f},{object_state.pos[2]:.3f})"

                    if writer is not None:
                        state = pose_capture.capture(
                            data,
                            action=action,
                            contact_count=max_contact_count,
                        )
                        writer.append(
                            time_s=float(data.time),
                            detail_N=detail_N,
                            detail_sdk=detail_sdk,
                            raw_sensor_N=sampled,
                            qpos=state["qpos"],
                            qvel=state["qvel"],
                            action=state["action"],
                            sensor_frame_xpos=state["sensor_frame_xpos"],
                            sensor_frame_xquat=state["sensor_frame_xquat"],
                            object_xpos=state["object_xpos"],
                            object_xquat=state["object_xquat"],
                            object_cvel=state["object_cvel"],
                            contact_count=state["contact_count"],
                        )
                    max_contact_count = 0

                    if tactile_frames % max(1, args.print_every) == 0:
                        print(line, flush=True)

                    if viewer is not None:
                        viewer.set_texts((None, None, "DexH13 tactile", line))

                sync_taxel_overlay(viewer, overlay, data, latest_overlay_raw)
                if viewer is not None:
                    viewer.sync()
                    if object_control_enabled and viewer_is_perturbing_body(viewer, model, object_target_body):
                        object_state = sync_object_control_to_mocap_target(model, data, object_state)
                    elif object_control_enabled and viewer_is_perturbing_body(viewer, model, args.object_body):
                        object_state = sync_object_control_to_body(model, data, object_state)
                if viewer is not None or args.realtime:
                    elapsed = time.perf_counter() - start
                    time.sleep(max(0.0, runtime.sim_dt - elapsed))
    finally:
        if viewer is not None:
            viewer.close()
        if writer_context is not None:
            writer_context.__exit__(None, None, None)

    print(f"finished steps={steps} tactile_frames={tactile_frames} record={'on' if args.record else 'off'}", flush=True)


if __name__ == "__main__":
    main()
