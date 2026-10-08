from __future__ import annotations

from types import SimpleNamespace

import mujoco
import numpy as np

from dexh13sim.pose_capture import PoseCapture
from dexh13sim.sensor_mount import SensorMount


def test_pose_capture_exports_hand_sensor_object_and_contact_state():
    model = mujoco.MjModel.from_xml_path("assets/dexh13_mjcf/interactive_press_scene.xml")
    data = mujoco.MjData(model)
    mujoco.mj_step(model, data)

    mount = SensorMount(model, "configs/sensors.yaml")
    capture = PoseCapture(model, mount, object_body_names=["press_probe"])
    state = capture.capture(data, action=np.arange(16, dtype=np.float32), contact_count=3)

    assert state["qpos"].shape == (16,)
    assert state["qvel"].shape == (16,)
    assert state["action"].shape == (16,)
    assert state["sensor_frame_xpos"].shape == (11, 3)
    assert state["sensor_frame_xquat"].shape == (11, 4)
    assert state["object_xpos"].shape == (1, 3)
    assert state["object_xquat"].shape == (1, 4)
    assert state["object_cvel"].shape == (1, 6)
    assert state["contact_count"] == 3
    assert np.isclose(np.linalg.norm(state["sensor_frame_xquat"], axis=1), 1.0).all()
    assert np.isclose(np.linalg.norm(state["object_xquat"], axis=1), 1.0).all()


def test_pose_capture_reads_named_hand_joints_when_extra_joint_precedes_hand(tmp_path):
    hand_joint_names = [
        "right_index_joint_0", "right_index_joint_1", "right_index_joint_2", "right_index_joint_3",
        "right_middle_joint_0", "right_middle_joint_1", "right_middle_joint_2", "right_middle_joint_3",
        "right_ring_joint_0", "right_ring_joint_1", "right_ring_joint_2", "right_ring_joint_3",
        "right_thumb_joint_0", "right_thumb_joint_1", "right_thumb_joint_2", "right_thumb_joint_3",
    ]
    sites = "\n".join(f'<site name="site_{idx}" pos="0 0 0" />' for idx in range(11))
    joint_bodies = "\n".join(
        f'<body name="body_{idx}" pos="0 0 0"><joint name="{name}" type="hinge" axis="0 0 1" /><geom type="sphere" size="0.001" mass="0.001" /></body>'
        for idx, name in enumerate(hand_joint_names)
    )
    xml = f'''<mujoco model="pose_order_test">
      <worldbody>
        <body name="extra" pos="0 0 0"><joint name="extra_joint" type="slide" axis="1 0 0" /><geom type="sphere" size="0.001" mass="0.001" /></body>
        <body name="hand" pos="0 0 0">
          {joint_bodies}
          {sites}
        </body>
      </worldbody>
    </mujoco>'''
    xml_path = tmp_path / "pose_order_test.xml"
    xml_path.write_text(xml)
    model = mujoco.MjModel.from_xml_path(str(xml_path))
    data = mujoco.MjData(model)
    data.qpos[0] = 99.0
    data.qvel[0] = -99.0
    for idx, name in enumerate(hand_joint_names):
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        data.qpos[model.jnt_qposadr[joint_id]] = float(idx + 1)
        data.qvel[model.jnt_dofadr[joint_id]] = float(idx + 101)
    mujoco.mj_forward(model, data)

    mount = SimpleNamespace(instances=[SimpleNamespace(sensor_id=i, site_id=i) for i in range(11)])
    capture = PoseCapture(model, mount)

    state = capture.capture(data)

    np.testing.assert_allclose(state["qpos"], np.arange(1, 17, dtype=np.float32))
    np.testing.assert_allclose(state["qvel"], np.arange(101, 117, dtype=np.float32))
