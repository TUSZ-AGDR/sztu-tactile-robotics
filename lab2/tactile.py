"""Conservative synthetic normal taxels from target-object contacts only."""
import numpy as np
import mujoco
from .scene import SIM_ROOT
from dexh13sim.sensor_mount import SensorMount
from dexh13sim.runtime import load_templates
from dexh13sim.sensor_table import SENSOR_TABLE, total_taxels
from dexh13sim.tactile_renderer import TactileRenderer
import yaml


class TactileReader:
    def __init__(self, scene):
        self.scene = scene
        self.mount = SensorMount(scene.model, SIM_ROOT / "configs/sensors.yaml")
        self.templates = load_templates(SIM_ROOT / "configs/taxel_templates")
        calibration = yaml.safe_load((SIM_ROOT / "configs/calibration.yaml").read_text())
        self.renderer = TactileRenderer(SENSOR_TABLE, self.templates, calibration["templates"], total_taxels())
        self.geom_to_sensor = self.mount.geom_to_sensor()
        self.specs = {spec.sensor_id: spec for spec in SENSOR_TABLE}

    def read(self):
        model, data = self.scene.model, self.scene.data
        normal = np.zeros(total_taxels(), dtype=np.float64)
        sensor_forces = np.zeros(len(SENSOR_TABLE))
        other_support_force = 0.0
        fallback_count = 0
        for contact_id in range(data.ncon):
            contact = data.contact[contact_id]
            if self.scene.object_geom not in contact.geom or contact.efc_address < 0:
                continue
            other = int(contact.geom[0] if contact.geom[1] == self.scene.object_geom else contact.geom[1])
            force = np.zeros(6)
            mujoco.mj_contactForce(model, data, contact_id, force)
            force_N = max(0.0, float(force[0]))
            sensor_id = self.geom_to_sensor.get(other)
            if sensor_id is None:
                other_support_force += force_N
                continue
            spec = self.specs[sensor_id]
            transform = self.mount.get_world_sensor_pose(sensor_id, data)
            point = transform[:3, :3].T @ (contact.pos - transform[:3, 3])
            template = self.templates[spec.template]
            weights = self.renderer._weights(template, self.renderer.template_config[spec.template], point)
            if weights.sum() <= 1e-12:
                # The teaching pad may extend past the original taxel mesh.
                # Assign to its nearest taxel rather than silently losing force.
                weights[int(template.kdtree.query(point)[1])] = 1.0
                fallback_count += 1
            normal[spec.start:spec.end] += force_N * weights / weights.sum()
            sensor_forces[sensor_id] += force_N
        return normal, sensor_forces, other_support_force, fallback_count
