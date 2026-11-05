"""Generate clearly labelled synthetic sensor pairs from saved MuJoCo poses.

No hardware access, original file edits, or claim of new measured observations.
The generated geometry is a kinematic replay with fixed fixture translations;
the generated sensor force is an analytic teaching model, not mj_contactForce.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import h5py
import mujoco
import numpy as np

FEATURE_NAMES = [
    "nearest_point_sensor_x_mm", "nearest_point_sensor_y_mm", "nearest_point_sensor_z_mm",
    "normal_sensor_x", "normal_sensor_y", "normal_sensor_z",
    "signed_gap_mm", "gap_velocity_mm_s", "indentation_mm", "geometric_contact",
    "packet_dt_sec",
]
SPLITS = ["train", "train", "train", "validation", "test"]


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sensor_response(features, time, rng):
    """A fixed virtual transducer: nonlinear elasticity, lag, mixing and noise.

    All constants are design choices, not a fit to any held-out measured force.
    N is the nominal unit of this synthetic model, not a calibration claim.
    """
    depth = np.clip(features[:, 8], 0, 1.2)  # mm
    normal_load = 4.0 * depth + 0.8 * depth**2  # N
    position = features[:, :3]
    normal = features[:, 3:6]
    ideal = normal_load[:, None] * normal
    # Smooth, position-dependent lateral response (illustrative, not friction identification).
    ideal[:, 0] += .12 * normal_load * np.sin(position[:, 0] / 7)
    ideal[:, 1] += .08 * normal_load * np.cos(position[:, 1] / 8)
    mixing = np.array([[.92, .10, -.08], [-.06, 1.08, .12], [.09, -.05, .96]])
    target = 4 * np.tanh((ideal @ mixing.T) / 4)
    filtered = np.zeros_like(target)
    state = np.zeros(3)
    for i in range(len(time)):
        dt = time[i] - time[i - 1] if i else np.median(np.diff(time))
        alpha = 1 - np.exp(-dt / .16)
        state = state + alpha * (target[i] - state)
        filtered[i] = state
    output = filtered + np.array([.02, -.01, .03]) + rng.normal(0, .015, filtered.shape)
    return np.round(output / .05) * .05


class SavedReplay:
    def __init__(self, folder):
        if tuple(map(int, mujoco.__version__.split(".")[:2])) < (3, 17):
            raise RuntimeError("Lab 4 mesh-distance replay requires MuJoCo >=3.17; activate the Lab 4 environment and install lab4/requirements.txt")
        self.folder = Path(folder)
        compact = self.folder / "recording.npz"
        if compact.is_file():
            self.record_meta = json.loads((self.folder / "recording.json").read_text())
            model_path = self.folder / self.record_meta["model_path"]
            manifest_path = self.folder / "model_manifest.json"
            self.source_files = {"recording.npz": compact, "recording.json": self.folder / "recording.json",
                                 "model.xml": model_path, "model_manifest.json": manifest_path}
        else:
            model_path = self.folder / "model/model.xml"
            manifest_path = self.folder / "model/model_manifest.json"
            self.source_files = {name: self.folder / name for name in
                                 ["paired.h5", "simulation/simulation.h5", "model/model.xml", "model/model_manifest.json"]}
        self.model = mujoco.MjModel.from_xml_path(str(model_path.resolve()))
        self.data = mujoco.MjData(self.model)
        manifest = json.loads(manifest_path.read_text())
        module = next(item for item in manifest["modules"] if item["module_id"] == 3)
        self.geom = self.model.geom(module["geom"]).id
        self.site = self.model.site("sensor_03").id
        self.body = self.model.body("Ex_Link").id
        self.objects = [i for i in range(self.model.ngeom)
                        if self.model.geom_bodyid[i] == self.body and self.model.geom_contype[i]]
        if not self.objects:
            raise ValueError("Fixture has no collision geometries")
        if compact.is_file():
            with np.load(compact, allow_pickle=False) as recording:
                self.raw_indices = recording["raw_event_index"]
                self.time = recording["time"]
                self.indices = recording["sim_frame_index"]
                self.measured = recording["measured_sdk_N"]
                self.q = recording["q_actual"]
                self.native_force = recording["native_module_force_N"]
                names = recording["joint_names"].tolist()
        else:
            self._load_native_recording()
            names = self.joint_names
        self.adr = [int(self.model.joint(name).qposadr[0]) for name in names]
        self.original_pos = self.model.body_pos[self.body].copy()
        self.data.qpos[self.adr] = self.q[0]
        mujoco.mj_forward(self.model, self.data)
        parent = int(self.model.body_parentid[self.body])
        self.parent_rotation = self.data.xmat[parent].reshape(3, 3).copy()
        if len(self.time) < 8 or not np.all(np.diff(self.time) > 0):
            raise ValueError("Need at least eight monotonic valid packets")

    def _load_native_recording(self):
        with h5py.File(self.folder / "paired.h5") as paired:
            valid = paired["raw_tactile/in_simulation_range"][:].astype(bool)
            force = paired["raw_tactile/module_force_sdk_N"][:, 2]
            valid &= np.isfinite(force).all(axis=1)
            self.raw_indices = np.flatnonzero(valid)
            self.time = paired["raw_tactile/relative_receive_time_sec"][:][valid]
            self.indices = paired["raw_tactile/sim_frame_index"][:][valid]
            self.measured = force[valid]
        with h5py.File(self.folder / "simulation/simulation.h5") as native:
            if np.any(self.indices < 0) or np.any(self.indices >= len(native["time_sec"])):
                raise ValueError("Invalid paired frame index")
            self.q = native["arm/q_actual"][:][self.indices]
            self.native_force = native["tactile/module_force_sensor_N"][:][self.indices, 2]
            self.joint_names = json.loads(native.attrs["joint_names"])

    def geometry(self, world_shift=None, time=None):
        sample_time = self.time if time is None else np.asarray(time)
        if sample_time.shape != self.time.shape or not np.all(np.diff(sample_time) > 0):
            raise ValueError("Geometry timestamps must match poses and increase")
        shift = np.zeros(3) if world_shift is None else np.asarray(world_shift)
        self.model.body_pos[self.body] = self.original_pos + self.parent_rotation.T @ shift
        positions, normals, gaps, world_segments = [], [], [], []
        for q in self.q:
            self.data.qpos[self.adr] = q
            mujoco.mj_forward(self.model, self.data)
            best = None
            for obj in self.objects:
                points = np.zeros(6)
                distance = float(mujoco.mj_geomDistance(self.model, self.data, self.geom, obj, 10., points))
                if best is None or distance < best[0]:
                    best = distance, points.copy()
            distance, points = best
            # Signed distance preserves the surface-normal direction through penetration.
            n = (points[:3] - points[3:]) / distance if abs(distance) > 1e-9 else np.zeros(3)
            if np.linalg.norm(n) < .5:
                raise ValueError("Degenerate closest-point normal; inspect geometry")
            n /= np.linalg.norm(n)
            rotation = self.data.site_xmat[self.site].reshape(3, 3)
            positions.append(rotation.T @ (points[:3] - self.data.site_xpos[self.site]) * 1000)
            normals.append(rotation.T @ n)
            gaps.append(distance * 1000)
            world_segments.append(points)
        gaps = np.asarray(gaps)
        # Backward difference only: features do not use future frames.
        speed = np.r_[0., np.diff(gaps) / np.diff(sample_time)]
        features = np.column_stack([positions, normals, gaps, speed, np.maximum(-gaps, 0), gaps <= 0,
                                    np.r_[0., np.diff(sample_time)]])
        if not np.isfinite(features).all():
            raise ValueError("Nonfinite geometry")
        return features, np.asarray(world_segments)


def write_pack(path, sequences):
    keys = ("x", "y", "time", "source_time", "sequence", "parent", "split", "source_kind", "raw_event_index", "sim_frame_index")
    np.savez_compressed(path, **{key: np.concatenate([row[key] for row in sequences]) for key in keys},
                        feature_names=np.array(FEATURE_NAMES))


def sequence(replay, x, y, name, split, source_kind, time=None):
    count = len(x)
    return dict(x=x.astype(np.float32), y=y.astype(np.float32),
                time=replay.time if time is None else time, source_time=replay.time,
                sequence=np.full(count, name), parent=np.full(count, replay.folder.name),
                split=np.full(count, split), source_kind=np.full(count, source_kind),
                raw_event_index=replay.raw_indices, sim_frame_index=replay.indices)


def prepare(source, out, variants=60, seed=42):
    if variants < 1:
        raise ValueError("variants must be positive")
    folders = sorted(p for p in Path(source).glob("Joint_*")
                     if (p / "recording.npz").is_file() or (p / "paired.h5").is_file())
    if len(folders) != 5:
        raise ValueError("This lesson expects the five verified Joint episode folders")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    rng = np.random.default_rng(seed)
    measured, synthetic, overview = [], [], []
    manifest = dict(schema_version=2, seed=seed, complete=False, feature_names=FEATURE_NAMES,
                    mujoco_version=mujoco.__version__,
                    measured_module_id=3, synthetic_is_hardware_measurement=False,
                    geometry_mode="kinematic replay of saved q_actual; fixed virtual fixture shift per sequence",
                    sensor_model="fixed nonlinear stiffness, cross-axis mixing, 160 ms lag, noise and quantization; see prepare.py",
                    learned_from_measured_force=False, source_batch=Path(source).as_posix(),
                    variation_ranges=dict(requested_depth_mm=[.05, .85], tangent_shift_mm=[-.4, .4],
                                          replay_speed_factor=[.65, 1.5]),
                    split_rule="parents 1-3 train, 4 validation, 5 test; all descendants inherit parent split",
                    sources=[], synthetic_sequences=[])
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for number, folder in enumerate(folders):
        replay = SavedReplay(folder)
        x, segments = replay.geometry()
        measured.append(sequence(replay, x, replay.measured, folder.name, SPLITS[number], "measured_sdk"))
        # Determine motion direction from geometry only, never from measured force.
        k = int(np.argmin(x[:, 6]))
        direction = (segments[k, :3] - segments[k, 3:]) / (x[k, 6] / 1000)
        direction /= np.linalg.norm(direction)
        reference_axis = np.array([0., 1., 0.]) if abs(direction[0]) > .9 else np.array([1., 0., 0.])
        tangent_a = np.cross(direction, reference_axis)
        tangent_a /= np.linalg.norm(tangent_a)
        tangent_b = np.cross(direction, tangent_a)
        manifest["sources"].append(dict(parent=folder.name, split=SPLITS[number], packets=len(x),
            sha256={name: sha256(path) for name, path in replay.source_files.items()}))
        for variant in range(variants):
            desired_depth_mm = float(rng.uniform(.05, .85))
            shift = direction * (float(x[k, 6]) + desired_depth_mm) / 1000
            tangent_mm = rng.uniform(-.4, .4, 2)
            shift += (tangent_mm[0] * tangent_a + tangent_mm[1] * tangent_b) / 1000
            speed_factor = float(rng.uniform(.65, 1.5))
            synthetic_time = replay.time[0] + (replay.time - replay.time[0]) / speed_factor
            sx, _ = replay.geometry(shift, time=synthetic_time)
            sy = sensor_response(sx, synthetic_time, rng)
            name = f"{folder.name}_synthetic_{variant:03d}"
            synthetic.append(sequence(replay, sx, sy, name, SPLITS[number], "synthetic_sensor", synthetic_time))
            manifest["synthetic_sequences"].append(dict(sequence=name, parent=folder.name,
                split=SPLITS[number], fixture_shift_world_m=shift.tolist(),
                tangent_shift_mm=tangent_mm.tolist(), replay_speed_factor=speed_factor,
                requested_depth_mm=desired_depth_mm, min_gap_mm=float(sx[:, 6].min())))
            if variant == 0:
                overview.append((replay, x, sx, sy, synthetic_time))
        print(f"Prepared {folder.name}: {len(x)} measured packets, {variants} synthetic sequences", flush=True)
    write_pack(out / "measured.npz", measured)
    write_pack(out / "synthetic.npz", synthetic)
    plot_overview(overview, out)
    for domain in ("measured", "synthetic"):
        with np.load(out / f"{domain}.npz", allow_pickle=False) as pack:
            np.savez_compressed(out / f"{domain}_sim_inputs.npz",
                                **{key: pack[key] for key in ("x", "time", "sequence", "feature_names")})
    manifest.update(complete=True, measured_packets=sum(len(row["x"]) for row in measured),
                    synthetic_packets=sum(len(row["x"]) for row in synthetic),
                    independent_measured_episodes=5, synthetic_sequence_count=len(synthetic))
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    checksums = {p.name: sha256(p) for p in sorted(out.iterdir()) if p.is_file()}
    (out / "checksums.json").write_text(json.dumps(checksums, indent=2) + "\n")
    return manifest


def plot_overview(rows, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(5, 2, figsize=(12, 12), constrained_layout=True)
    for i, (replay, x, sx, sy, synthetic_time) in enumerate(rows):
        ax = axes[i, 0]
        ax.plot(replay.time, np.linalg.norm(replay.measured, axis=1), label="Measured SDK (nominal N)")
        ax.plot(replay.time, np.linalg.norm(replay.native_force, axis=1), label="Original MuJoCo ID3 force")
        ax.set_title(replay.folder.name + " | " + SPLITS[i]); ax.set_ylabel("Force norm (N)")
        ax.legend(fontsize=8); ax.grid(alpha=.2)
        ax = axes[i, 1]
        ax.plot(synthetic_time, sx[:, 8], color="C1", label="Synthetic indentation")
        other = ax.twinx()
        other.plot(synthetic_time, np.linalg.norm(sy, axis=1), color="C2", label="Synthetic sensor norm")
        ax.set_title("Generated teaching pair; not a hardware measurement")
        ax.set_ylabel("Indentation (mm)", color="C1"); other.set_ylabel("Model N", color="C2")
        ax.legend(loc="upper left", fontsize=7); other.legend(loc="upper right", fontsize=7); ax.grid(alpha=.2)
    axes[-1, 0].set_xlabel("Trigger-relative time (s)")
    axes[-1, 1].set_xlabel("Synthetic time (s; speed-scaled)")
    fig.savefig(out / "data_comparison.png", dpi=140)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("lab4/replay_assets/episodes"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--variants", type=int, default=60)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    prepare(args.source, args.out, args.variants, args.seed)


if __name__ == "__main__":
    main()
