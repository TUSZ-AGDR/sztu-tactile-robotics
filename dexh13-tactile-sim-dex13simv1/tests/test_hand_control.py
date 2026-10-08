from __future__ import annotations

import mujoco
import yaml
import numpy as np

from dexh13sim.hand_control import POLICY_NAMES, ScriptedHandPolicy, apply_action


def test_sine_close_policy_changes_action_inside_ctrl_range():
    model = mujoco.MjModel.from_xml_path("assets/dexh13_mjcf/interactive_press_scene.xml")
    policy = ScriptedHandPolicy(model, name="sine_close", amplitude=0.5, period_s=1.0)

    action0 = policy.action(0.0)
    action1 = policy.action(0.25)

    assert action0.shape == (16,)
    assert np.linalg.norm(action1 - action0) > 1.0e-3
    assert np.all(action1 >= model.actuator_ctrlrange[:, 0] - 1.0e-6)
    assert np.all(action1 <= model.actuator_ctrlrange[:, 1] + 1.0e-6)


def test_apply_action_writes_model_controls():
    model = mujoco.MjModel.from_xml_path("assets/dexh13_mjcf/interactive_press_scene.xml")
    data = mujoco.MjData(model)
    action = ScriptedHandPolicy(model, name="index_tap", amplitude=0.4, period_s=1.0).action(0.25)

    applied = apply_action(model, data, action)

    np.testing.assert_allclose(data.ctrl[:16], applied)
    assert np.count_nonzero(applied) > 0


def test_sim_config_uses_available_hand_policy():
    config = yaml.safe_load(open("configs/sim.yaml", encoding="utf-8"))

    assert config["control"]["policy"] in POLICY_NAMES
