import csv
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import h5py
import mujoco
import numpy as np

from dexh13sim.hand_control import ScriptedHandPolicy, apply_action


def test_generated_taxel_templates_have_expected_counts_and_reference_points():
    root = Path("configs/taxel_templates")
    expected_counts = {
        "IP_M3025.csv": 120,
        "MP_M2324.csv": 60,
        "DP_M2826.csv": 120,
        "IP_L5325.csv": 120,
        "DP_L3530.csv": 120,
    }

    for filename, count in expected_counts.items():
        with (root / filename).open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) == count
        assert [int(row["taxel_id"]) for row in rows] == list(range(count))

    with (root / "IP_M3025.csv").open(newline="", encoding="utf-8") as handle:
        ip_rows = list(csv.DictReader(handle))
    assert ip_rows[0]["x_mm"] == "-11.290000"
    assert ip_rows[0]["y_mm"] == "0.970000"
    assert ip_rows[0]["z_mm"] == "1.650000"


def test_clean_hand_model_has_named_tactile_geoms_and_sensor_frame_sites():
    root = ET.parse("assets/dexh13_mjcf/hand.xml").getroot()
    joints = root.findall(".//joint")
    tactile_geoms = [
        geom for geom in root.findall(".//geom") if geom.get("name", "").endswith("_tactile_geom")
    ]
    sensor_sites = [
        site for site in root.findall(".//site") if site.get("name", "").startswith("site_")
    ]

    assert len(joints) == 16
    assert len(tactile_geoms) == 11
    assert len(sensor_sites) == 11
    assert root.find("sensor") is None


def test_hand_model_has_external_collision_primitive_layer():
    root = ET.parse("assets/dexh13_mjcf/hand.xml").getroot()
    primitive_geoms = [
        geom for geom in root.findall(".//geom") if geom.get("class") == "dexh13_external_collision"
    ]
    mesh_collision_geoms = [
        geom for geom in root.findall(".//geom") if geom.get("class") == "dexh13_collision"
    ]

    primitive_names = {geom.get("name") for geom in primitive_geoms}
    assert primitive_names == {
        "right_palm_link_external_collision_geom",
        "right_index_link_0_external_collision_geom",
        "right_middle_link_0_external_collision_geom",
        "right_ring_link_0_external_collision_geom",
        "right_thumb_link_0_external_collision_geom",
    }
    assert {geom.get("type") for geom in primitive_geoms} <= {"box", "capsule", "sphere"}
    assert not any("_link_2_external_collision_geom" in str(name) for name in primitive_names)
    assert not any("_link_3_external_collision_geom" in str(name) for name in primitive_names)
    assert all(geom.get("mesh") is None for geom in primitive_geoms)
    assert len(mesh_collision_geoms) >= 17


def test_mujoco_hand_and_press_scene_compile():
    hand = mujoco.MjModel.from_xml_path("assets/dexh13_mjcf/hand.xml")
    scene = mujoco.MjModel.from_xml_path("assets/dexh13_mjcf/test_press_scene.xml")
    interactive = mujoco.MjModel.from_xml_path("assets/dexh13_mjcf/interactive_press_scene.xml")
    free_object = mujoco.MjModel.from_xml_path("assets/dexh13_mjcf/free_object_scene.xml")

    assert hand.njnt == 16
    assert hand.nsite == 11
    assert scene.njnt == 17
    assert interactive.njnt == 17
    assert free_object.njnt == 17
    assert mujoco.mj_name2id(free_object, mujoco.mjtObj.mjOBJ_BODY, "free_sphere") >= 0
    free_joint_id = mujoco.mj_name2id(free_object, mujoco.mjtObj.mjOBJ_JOINT, "free_sphere_joint")
    assert free_joint_id >= 0
    assert int(free_object.jnt_type[free_joint_id]) == mujoco.mjtJoint.mjJNT_FREE
    assert free_object.nmocap == 1
    assert mujoco.mj_name2id(free_object, mujoco.mjtObj.mjOBJ_BODY, "free_sphere_target") >= 0
    assert mujoco.mj_name2id(free_object, mujoco.mjtObj.mjOBJ_EQUALITY, "free_sphere_physical_drag") >= 0


def test_press_script_writes_one_tactile_frame(tmp_path: Path):
    out_path = tmp_path / "press.h5"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_press_test.py",
            "--steps",
            "200",
            "--out",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "frames=1" in result.stdout
    with h5py.File(out_path, "r") as h5:
        assert h5["tactile/detail_N"].shape == (1, 1140, 3)
        assert h5["tactile/detail_sdk"].shape == (1, 1140, 3)
        assert h5["tactile/raw_sensor_N"].shape == (1, 1140, 3)
        assert h5["qpos"].shape == (1, 16)
        assert float(np.linalg.norm(h5["state/sensor_frame_xpos"][:])) > 0.0
        assert h5["state/object_xpos"].shape == (1, 1, 3)


def test_hold_open_hand_has_no_startup_self_collision_or_jitter():
    model = mujoco.MjModel.from_xml_path("assets/dexh13_mjcf/hand.xml")
    data = mujoco.MjData(model)
    policy = ScriptedHandPolicy(model, name="hold_open")

    for _ in range(100):
        apply_action(model, data, policy.action(float(data.time)))
        mujoco.mj_step(model, data)

    assert data.ncon == 0
    assert float(np.linalg.norm(data.qvel[:16])) < 1.0e-6


def test_free_object_contacts_non_tactile_palm_collision_primitive():
    model = mujoco.MjModel.from_xml_path("assets/dexh13_mjcf/free_object_scene.xml")
    data = mujoco.MjData(model)
    free_joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "free_sphere_joint")
    qposadr = int(model.jnt_qposadr[free_joint_id])
    data.qpos[qposadr : qposadr + 3] = np.asarray([0.08, 0.0, 0.0275], dtype=np.float64)
    data.qpos[qposadr + 3 : qposadr + 7] = np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
    mujoco.mj_step(model, data)

    palm_geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "right_palm_link_external_collision_geom")
    sphere_geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "free_sphere_geom")
    contacted_pairs = {
        frozenset((int(data.contact[contact_id].geom1), int(data.contact[contact_id].geom2)))
        for contact_id in range(data.ncon)
    }

    assert frozenset((palm_geom_id, sphere_geom_id)) in contacted_pairs
