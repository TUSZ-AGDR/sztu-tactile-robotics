"""Course scene: real gravity, removable support, and a one-dimensional pinch.

The two active tactile collision surfaces are planar teaching pads. The original
hand meshes remain visible. This intentionally simplifies collision geometry;
it is not a vendor-calibrated sensor or a sim-to-real hand model.
"""
from copy import deepcopy
from pathlib import Path
import json
import sys
import xml.etree.ElementTree as ET
import numpy as np
import mujoco
from scipy.spatial.transform import Rotation

LAB_ROOT = Path(__file__).resolve().parent
SIM_ROOT = LAB_ROOT.parent / "dexh13-tactile-sim-dex13simv1"
if not (SIM_ROOT / "dexh13sim").is_dir():
    raise FileNotFoundError(f"Missing simulation assets at {SIM_ROOT}. Keep lab2 inside the full repository.")
if str(SIM_ROOT) not in sys.path:
    sys.path.insert(0, str(SIM_ROOT))

from dexh13sim.runtime import load_templates
from dexh13sim.sensor_table import SENSOR_TABLE

OBJECT_POSITION = np.array([0.10087, -0.045107, 0.06670])
ACTIVE_SENSORS = ("index_tip", "thumb_proximal")
SIZES = {"box": "0.021 0.019 0.019", "cylinder": "0.023 0.019", "sphere": "0.023"}
# Select using only supported force, never success after releasing the object.
NOMINAL_FIXED_CLOSURE = {"box": .5927, "cylinder": .6070, "sphere": .6115}


def build_model(config):
    root = ET.parse(SIM_ROOT / "assets/dexh13_mjcf/hand.xml").getroot()
    root.find("compiler").set("meshdir", str(SIM_ROOT / "assets/dexh13_raw/dexh13_hand_right_description/meshes"))
    root.remove(root.find("keyframe"))
    option = root.find("option")
    option.set("gravity", "0 0 -9.81")
    option.set("iterations", "100")
    option.set("noslip_iterations", "20")
    templates = load_templates(SIM_ROOT / "configs/taxel_templates")

    reference = mujoco.MjModel.from_xml_path(str(SIM_ROOT / "assets/dexh13_mjcf/hand.xml"))
    data = mujoco.MjData(reference)
    data.qpos[:] = np.r_[[-.35, 1.00872, 1.39496, 0], np.zeros(8), [-.35, 1.012408, .093873, 1.57]]
    mujoco.mj_forward(reference, data)
    for spec in SENSOR_TABLE:
        geom = root.find(f'.//geom[@name="{spec.name}_tactile_geom"]')
        parent = next(body for body in root.iter("body") if geom in list(body))
        visual = deepcopy(geom)
        visual.set("name", f"{spec.name}_visual")
        visual.set("contype", "0")
        visual.set("conaffinity", "0")
        parent.append(visual)
        template = templates[spec.template]
        normal = template.normals.mean(axis=0)
        normal /= np.linalg.norm(normal)
        if spec.name in ACTIVE_SENSORS:
            sid = mujoco.mj_name2id(reference, mujoco.mjtObj.mjOBJ_SITE, f"site_{spec.name}_sensor_frame")
            desired = np.array([.94, .341, 0]) * (1 if spec.name == "thumb_proximal" else -1)
            normal = data.site_xmat[sid].reshape(3, 3).T @ desired
            normal /= np.linalg.norm(normal)
        center = template.xyz_m.mean(axis=0) - .004 * normal
        axis = np.cross([0, 0, 1], normal)
        angle = np.arccos(np.clip(normal[2], -1, 1))
        if np.linalg.norm(axis) < 1e-10:
            quat = np.array([0., 0., 0., 1.]) if normal[2] > 0 else np.array([1., 0., 0., 0.])
        else:
            quat = Rotation.from_rotvec(axis / np.linalg.norm(axis) * angle).as_quat()
        geom.attrib.pop("mesh")
        geom.set("type", "cylinder")
        geom.set("size", ".016 .004")
        geom.set("pos", " ".join(map(str, center)))
        geom.set("quat", " ".join(map(str, [quat[3], *quat[:3]])))
        geom.set("rgba", "0.2 0.65 0.9 0.25")
        geom.set("condim", "6")
        geom.set("priority", "1")
        geom.set("friction", f"{config.friction} .02 .01")
        active = spec.name in ACTIVE_SENSORS
        geom.set("contype", "1" if active else "0")
        geom.set("conaffinity", "8" if active else "0")

    world = root.find("worldbody")
    ET.SubElement(world, "geom", name="lab_floor", type="plane", size=".5 .5 .01",
                  pos="0 0 -.05", contype="4", conaffinity="8", material="mat_floor")
    position = " ".join(map(str, OBJECT_POSITION))
    # A weld supports the object only before release. No pose/velocity writes
    # are allowed after release; xfrc_applied is used for the physical pull.
    ET.SubElement(world, "body", name="lab_support", mocap="true", pos=position)
    body = ET.SubElement(world, "body", name="lab_object", pos=position)
    if config.object_name == "box":
        body.set("quat", ".984808 0 0 .173648")
    ET.SubElement(body, "freejoint", name="lab_object_joint")
    ET.SubElement(body, "geom", name="lab_object_geom", type=config.object_name,
                  size=SIZES[config.object_name], mass=str(config.mass_kg),
                  friction=f"{config.friction} .02 .01", priority="1", condim="6",
                  contype="8", conaffinity="7", solref=".008 1", rgba=".15 .5 .8 1")
    equality = ET.SubElement(root, "equality")
    ET.SubElement(equality, "weld", name="lab_support_weld", body1="lab_object",
                  body2="lab_support", solref=".005 1")
    visual = ET.SubElement(root, "visual")
    ET.SubElement(visual, "global", offwidth="1280", offheight="720")
    return mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"))


class Scene:
    def __init__(self, config):
        self.model = build_model(config)
        self.data = mujoco.MjData(self.model)
        payload = json.loads((LAB_ROOT / "assets" / f"{config.object_name}.json").read_text())
        self.closures = np.asarray(payload["closures"])
        self.joint_targets = np.asarray(payload["joint_targets"])
        self.nominal_fixed_closure = NOMINAL_FIXED_CLOSURE[config.object_name]
        self.object_geom = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "lab_object_geom")
        self.object_body = int(self.model.geom_bodyid[self.object_geom])
        self.support_eq = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_EQUALITY, "lab_support_weld")
        # Start from genuine joint zero, not closure=0 of the pinch preset.
        initial_targets = np.zeros(16) if config.approach_time_s > 0 else self.action(0)
        self.data.qpos[:16] = initial_targets
        self.data.ctrl[:16] = initial_targets
        mujoco.mj_forward(self.model, self.data)
        self.initial_position = self.data.xpos[self.object_body].copy()

    def action(self, closure):
        return np.asarray([np.interp(closure, self.closures, self.joint_targets[:, i]) for i in range(16)])

    def apply(self, closure, config, time_s):
        if time_s < config.approach_time_s:
            # Show joint zero briefly, move smoothly, then let the actuators
            # settle. Move by actuator targets only; never teleport qpos.
            u = np.clip((time_s / config.approach_time_s - .15) / .7, 0, 1)
            blend = u ** 3 * (10 - 15 * u + 6 * u ** 2)
            self.data.ctrl[:16] = blend * self.action(0)
        else:
            self.data.ctrl[:16] = self.action(closure)
        self.data.eq_active[self.support_eq] = int(time_s < config.release_time_s)
        self.data.xfrc_applied[:] = 0
        if config.pulling(time_s):
            self.data.xfrc_applied[self.object_body, 2] = -config.pull_force_N
