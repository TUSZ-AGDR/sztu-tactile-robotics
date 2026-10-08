"""Regenerate the checked-in closure trajectories (maintainer tool)."""
from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np
import mujoco
from scipy.optimize import brentq, least_squares
from lab2.scene import build_model, LAB_ROOT
from lab2.config import ExperimentConfig


def build(object_name):
    model = build_model(ExperimentConfig(object_name=object_name))
    data = mujoco.MjData(model)
    object_geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "lab_object_geom")
    q = np.r_[[-.35, 1., 1.39496, 0], np.zeros(8), [-.35, 1.012408, .035296, 1.57]]
    geoms = [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, name)
             for name in ("index_tip_tactile_geom", "thumb_proximal_tactile_geom")]
    for joint, geom, bounds in ((1, geoms[0], (.6, 1.4)), (14, geoms[1], (0, .4))):
        def distance(angle):
            q[joint] = angle
            data.qpos[:16] = q
            mujoco.mj_forward(model, data)
            return mujoco.mj_geomDistance(model, data, object_geom, geom, .2, None)
        q[joint] = brentq(distance, *bounds)
    data.qpos[:16] = q
    mujoco.mj_forward(model, data)
    positions = data.geom_xpos[geoms].copy()
    direction = positions[1] - positions[0]
    direction /= np.linalg.norm(direction)
    closures = np.linspace(0, 1, 21)
    frames = []
    max_error = 0.0
    for closure in closures:
        command = q.copy()
        for geom, indices, sign, position in (
                (geoms[0], [0, 1, 2, 3], 1, positions[0]),
                (geoms[1], [12, 13, 14], -1, positions[1])):
            target = position + sign * (closure - .5) * .012 * direction
            def residual(angles):
                command[indices] = angles
                data.qpos[:16] = command
                mujoco.mj_forward(model, data)
                return np.r_[data.geom_xpos[geom] - target, .00001 * (angles - q[indices])]
            fit = least_squares(residual, q[indices],
                bounds=([-.35, *([0] * (len(indices) - 1))], [.35, *([1.57] * (len(indices) - 1))]),
                max_nfev=300, gtol=1e-12, ftol=1e-12, xtol=1e-12)
            command[indices] = fit.x
            max_error = max(max_error, float(np.linalg.norm(residual(fit.x)[:3])))
        frames.append(command.copy())
    path = LAB_ROOT / "assets" / f"{object_name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"object_name": object_name, "collision_model": "planar teaching pads",
               "max_ik_error_m": max_error, "closures": closures.tolist(),
               "joint_targets": np.asarray(frames).tolist()}
    path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"{object_name}: {path.name}, max IK position error {max_error:.6f} m")


if __name__ == "__main__":
    for object_name in ("box", "cylinder", "sphere"):
        build(object_name)
