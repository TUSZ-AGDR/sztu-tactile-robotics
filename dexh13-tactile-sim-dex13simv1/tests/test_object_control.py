from __future__ import annotations

import mujoco
import numpy as np

from dexh13sim.object_control import (
    MAX_PHYSICAL_DRAG_PENETRATION_M,
    ObjectControlState,
    apply_object_control,
    handle_object_key,
    halt_object_motion,
    mocap_id_for_body,
    sync_object_control_to_mocap_target,
    sync_object_control_to_body,
    target_body_name_for,
    viewer_is_perturbing_body,
)
from dexh13sim.interactive_control import ManualControlState, apply_manual_control
from dexh13sim.runtime import TactileRuntime, summarize_raw
from scripts import view_tactile_live


def test_object_control_moves_mocap_target_without_teleporting_free_body():
    model = mujoco.MjModel.from_xml_path("assets/dexh13_mjcf/free_object_scene.xml")
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "free_sphere")
    initial_body_pos = np.asarray(data.xpos[body_id]).copy()
    state = ObjectControlState(body_name="free_sphere", pos=(0.219, -0.0315, 0.018))

    apply_object_control(model, data, state)

    mocap_id = mocap_id_for_body(model, "free_sphere_target")
    assert np.allclose(data.mocap_pos[mocap_id], state.pos, atol=1.0e-6)
    assert np.allclose(data.xpos[body_id], initial_body_pos, atol=1.0e-6)


def test_object_keys_step_position_in_xyz_without_touching_hand_state():
    state = ObjectControlState(body_name="free_sphere", pos=(0.0, 0.0, 0.0), step=0.002)

    state = handle_object_key(state, "l")
    state = handle_object_key(state, "i")
    state = handle_object_key(state, "m")

    assert state.pos == (0.002, 0.002, 0.002)


def test_sync_object_control_to_body_keeps_drag_target_at_mouse_perturbed_body():
    model = mujoco.MjModel.from_xml_path("assets/dexh13_mjcf/free_object_scene.xml")
    data = mujoco.MjData(model)
    free_joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "free_sphere_joint")
    qposadr = int(model.jnt_qposadr[free_joint_id])
    data.qpos[qposadr : qposadr + 3] = np.asarray([0.23, -0.02, 0.03])
    mujoco.mj_forward(model, data)

    state = sync_object_control_to_body(model, data, ObjectControlState(body_name="free_sphere"))
    mocap_id = mocap_id_for_body(model, "free_sphere_target")

    assert np.allclose(state.pos, data.xpos[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "free_sphere")])
    assert np.allclose(data.mocap_pos[mocap_id], state.pos)


def test_viewer_is_perturbing_body_matches_selected_active_body():
    model = mujoco.MjModel.from_xml_path("assets/dexh13_mjcf/free_object_scene.xml")
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "free_sphere")
    perturb = mujoco.MjvPerturb()
    perturb.select = body_id
    perturb.active = 1
    viewer = type("Viewer", (), {"perturb": perturb})()

    assert viewer_is_perturbing_body(viewer, model, "free_sphere")
    assert not viewer_is_perturbing_body(viewer, model, "right_palm_link")


def test_default_free_object_first_hand_contact_is_tactile_not_hidden_collision():
    model = mujoco.MjModel.from_xml_path("assets/dexh13_mjcf/free_object_scene.xml")
    data = mujoco.MjData(model)
    runtime = TactileRuntime(model)
    object_state = ObjectControlState(body_name="free_sphere")
    apply_object_control(model, data, object_state)

    first_object_contact: tuple[str, str] | None = None
    first_tactile_total = 0.0
    for step in range(1200):
        close = min(1.0, step / 600.0)
        apply_manual_control(model, data, ManualControlState(close=close))
        apply_object_control(model, data, object_state)
        mujoco.mj_step(model, data)
        raw, _ = runtime.raw_from_data(data)
        tactile_total = summarize_raw(raw).total_N
        if tactile_total > 1.0e-8:
            first_tactile_total = tactile_total
            break
        for contact_id in range(data.ncon):
            contact = data.contact[contact_id]
            geom1 = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, contact.geom1) or ""
            geom2 = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, contact.geom2) or ""
            if "free_sphere_geom" in {geom1, geom2}:
                first_object_contact = (geom1, geom2)
                break
        if first_object_contact is not None:
            break

    assert first_object_contact is None, f"object was blocked by hidden non-tactile contact {first_object_contact}"
    assert first_tactile_total > 1.0e-8


def test_select_body_for_mouse_perturb_preselects_free_object():
    model = mujoco.MjModel.from_xml_path("assets/dexh13_mjcf/free_object_scene.xml")
    perturb = mujoco.MjvPerturb()
    viewer = type("Viewer", (), {"perturb": perturb})()
    target_body = target_body_name_for("free_sphere")

    assert hasattr(view_tactile_live, "select_body_for_mouse_perturb")
    assert view_tactile_live.select_body_for_mouse_perturb(viewer, model, target_body)
    assert perturb.select == mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, target_body)
    assert not view_tactile_live.select_body_for_mouse_perturb(viewer, model, "missing_body")


def test_sync_object_control_to_mocap_target_keeps_keyboard_state_after_mouse_drag():
    model = mujoco.MjModel.from_xml_path("assets/dexh13_mjcf/free_object_scene.xml")
    data = mujoco.MjData(model)
    mocap_id = mocap_id_for_body(model, "free_sphere_target")
    data.mocap_pos[mocap_id] = np.asarray([0.24, -0.01, 0.04])
    data.mocap_quat[mocap_id] = np.asarray([1.0, 0.0, 0.0, 0.0])

    state = sync_object_control_to_mocap_target(model, data, ObjectControlState(body_name="free_sphere"))

    assert np.allclose(state.pos, [0.24, -0.01, 0.04])
    assert np.allclose(state.quat, [1.0, 0.0, 0.0, 0.0])


def test_halt_object_motion_locks_target_to_body_and_zeroes_freejoint_velocity():
    model = mujoco.MjModel.from_xml_path("assets/dexh13_mjcf/free_object_scene.xml")
    data = mujoco.MjData(model)
    free_joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "free_sphere_joint")
    qposadr = int(model.jnt_qposadr[free_joint_id])
    dofadr = int(model.jnt_dofadr[free_joint_id])
    data.qpos[qposadr : qposadr + 3] = np.asarray([0.225, -0.02, 0.032])
    data.qvel[dofadr : dofadr + 6] = np.asarray([0.3, -0.2, 0.1, 1.0, 0.5, -0.25])
    mujoco.mj_forward(model, data)

    state = halt_object_motion(model, data, ObjectControlState(body_name="free_sphere", pos=(0.3, 0.1, 0.1)))
    mocap_id = mocap_id_for_body(model, "free_sphere_target")

    assert np.allclose(state.pos, data.xpos[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "free_sphere")])
    assert np.allclose(data.mocap_pos[mocap_id], state.pos)
    assert np.allclose(data.qvel[dofadr : dofadr + 6], 0.0)


def test_physical_drag_contact_solver_blocks_deep_hand_penetration():
    model = mujoco.MjModel.from_xml_path("assets/dexh13_mjcf/free_object_scene.xml")
    data = mujoco.MjData(model)

    apply_object_control(model, data, ObjectControlState(body_name="free_sphere", pos=(0.08, 0.0, -0.02)))
    for _ in range(800):
        mujoco.mj_step(model, data)

    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "free_sphere")
    assert np.linalg.norm(data.xpos[body_id] - np.asarray([0.08, 0.0, -0.02])) > 0.03
    for contact_id in range(data.ncon):
        assert data.contact[contact_id].dist >= -MAX_PHYSICAL_DRAG_PENETRATION_M - 1.0e-6
