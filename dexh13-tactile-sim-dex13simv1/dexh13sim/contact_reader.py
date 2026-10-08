from __future__ import annotations

from typing import Any

import numpy as np


class ContactReader:
    def __init__(self, model: Any, mount: Any, force_on_geom1: bool = True):
        self.model = model
        self.mount = mount
        self.force_on_geom1 = force_on_geom1
        self.geom_to_sensor = mount.geom_to_sensor()

    def read(self, data: Any) -> list[dict[str, object]]:
        import mujoco

        contacts: list[dict[str, object]] = []
        for contact_id in range(data.ncon):
            contact = data.contact[contact_id]
            if int(contact.exclude) != 0 or int(contact.efc_address) < 0:
                continue

            geom0, geom1 = int(contact.geom[0]), int(contact.geom[1])
            geom0_sensor = geom0 in self.geom_to_sensor
            geom1_sensor = geom1 in self.geom_to_sensor
            if geom0_sensor == geom1_sensor:
                continue

            force6 = np.zeros(6, dtype=np.float64)
            mujoco.mj_contactForce(self.model, data, contact_id, force6)
            frame = np.asarray(contact.frame, dtype=np.float64).reshape(3, 3)
            f_world = frame.T @ force6[:3]

            force_reference_geom = geom1 if self.force_on_geom1 else geom0
            if not self.force_on_geom1:
                f_world = -f_world

            tactile_geom = geom1 if geom1_sensor else geom0
            if tactile_geom != force_reference_geom:
                f_world = -f_world

            sensor_id = self.geom_to_sensor[tactile_geom]
            T_WS = self.mount.get_world_sensor_pose(sensor_id, data)
            R_WS = T_WS[:3, :3]
            t_WS = T_WS[:3, 3]
            p_world = np.asarray(contact.pos, dtype=np.float64)
            p_sensor = R_WS.T @ (p_world - t_WS)
            f_sensor = R_WS.T @ f_world

            contacts.append(
                {
                    "sensor_id": sensor_id,
                    "p_sensor": p_sensor,
                    "f_sensor": f_sensor,
                    "contact_id": contact_id,
                    "geom0": geom0,
                    "geom1": geom1,
                }
            )
        return contacts
