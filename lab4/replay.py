"""Render original saved poses beside one explicitly synthetic kinematic replay."""
import argparse
import json
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .prepare import SavedReplay


def render(source, data_dir, out, parent_index=1, variant=0):
    out = Path(out)
    if out.exists():
        raise FileExistsError(out)
    manifest = json.loads((Path(data_dir) / "manifest.json").read_text())
    parent = manifest["sources"][parent_index]["parent"]
    variants = [v for v in manifest["synthetic_sequences"] if v["parent"] == parent]
    item = variants[variant]
    replay = SavedReplay(Path(source) / parent)
    with np.load(Path(data_dir) / "synthetic.npz", allow_pickle=False) as data:
        mask = data["sequence"] == item["sequence"]
        synthetic_force = data["y"][mask]
        synthetic_time = data["time"][mask]
    base, _ = replay.geometry()
    synthetic, segments = replay.geometry(item["fixture_shift_world_m"], time=synthetic_time)
    center = segments[int(np.argmin(synthetic[:, 6]))].reshape(2, 3).mean(axis=0)
    camera = mujoco.MjvCamera()
    camera.lookat[:] = center
    camera.distance, camera.azimuth, camera.elevation = .23, 175, -10
    option = mujoco.MjvOption()
    option.geomgroup[3] = 0
    option.sitegroup[:] = 0
    renderer = mujoco.Renderer(replay.model, height=400, width=600)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    frames = []
    try:
        for i, t in enumerate(replay.time):
            panels = []
            for shifted in (False, True):
                shift = np.asarray(item["fixture_shift_world_m"]) if shifted else np.zeros(3)
                replay.model.body_pos[replay.body] = replay.original_pos + replay.parent_rotation.T @ shift
                replay.data.qpos[replay.adr] = replay.q[i]
                mujoco.mj_forward(replay.model, replay.data)
                renderer.update_scene(replay.data, camera=camera, scene_option=option)
                im = Image.fromarray(renderer.render())
                draw = ImageDraw.Draw(im)
                draw.rectangle((0, 0, 600, 73), fill=(20, 25, 32))
                title = "SYNTHETIC kinematic replay" if shifted else "Original saved MuJoCo replay"
                gap = synthetic[i, 6] if shifted else base[i, 6]
                force = synthetic_force[i] if shifted else replay.measured[i]
                label = "Synthetic sensor" if shifted else "Measured SDK"
                current_time = synthetic_time[i] if shifted else t
                draw.text((9, 7), f"{title} | t={current_time:.2f} s", font=font, fill="white")
                draw.text((9, 29), f"ID3 gap: {gap:+.3f} mm | {label}: {np.linalg.norm(force):.2f} N", font=font, fill="#FFD48C")
                line = f"Pose-paired view | synthetic speed {item.get('replay_speed_factor', 1):.2f}x" if shifted else f"Original simulated ID3 force: {np.linalg.norm(replay.native_force[i]):.2f} N"
                draw.text((9, 51), line, font=font, fill="#C4CDD9")
                panels.append(im)
            joined = Image.new("RGB", (1200, 400))
            joined.paste(panels[0], (0, 0)); joined.paste(panels[1], (600, 0))
            frames.append(joined)
    finally:
        renderer.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    durations = np.r_[np.diff(replay.time), np.median(np.diff(replay.time))] * 1000
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=np.maximum(durations, 20).astype(int).tolist(), loop=0)
    frames[int(np.argmin(synthetic[:, 6]))].save(out.with_suffix(".png"))
    print(out)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=Path("lab4/replay_assets/episodes"))
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--parent-index", type=int, default=1)
    p.add_argument("--variant", type=int, default=0)
    a = p.parse_args()
    render(a.source, a.data, a.out, a.parent_index, a.variant)
