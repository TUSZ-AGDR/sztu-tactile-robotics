"""Physics acceptance checks, not just mirrors of controller implementation."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np
import pytest
from lab2 import Experiment, ExperimentConfig
from lab2.evaluation import Evaluator
from lab2.scene import Scene
from lab2.tactile import TactileReader


@pytest.mark.parametrize("object_name", ["box", "cylinder", "sphere"])
def test_default_feedback_really_holds_released_object(object_name):
    experiment = Experiment(object_name=object_name)
    result = experiment.run(headless=True)
    assert result.metrics["success"], result.describe()
    assert result.metrics["held_time_s"] == pytest.approx(3)
    assert not experiment.scene.data.eq_active.any()
    released = result.trace["time_s"] > result.config.release_time_s + 1e-9
    assert not result.trace["support_active"][released].any()
    assert result.trace["pull_force_N"].max() == pytest.approx(.1)
    assert np.max(np.abs(result.trace["taxel_normal_N"].sum(axis=1) - result.trace["raw_grip_force_N"])) < 1e-8
    assert result.metrics["taxel_fallback_assignments"] == 0
    np.testing.assert_array_equal(result.trace["qpos"][0, :16], np.zeros(16))
    approaching = result.trace["time_s"] < result.config.approach_time_s
    assert not result.trace["closure"][approaching].any()
    assert np.max(np.abs(np.diff(result.trace["qpos"][approaching, :16], axis=0))) < .1
    assert np.max(np.abs(result.trace["qpos"][approaching, :16])) > .5


def test_open_hand_fails_even_if_palm_eventually_catches_object():
    result = Experiment(fixed_closure=0.05).run("fixed", headless=True)
    assert not result.metrics["success"]
    assert "dropped" in result.metrics["reasons"] or "external_support" in result.metrics["reasons"]
    assert result.metrics["held_time_s"] < 3


def test_overclosing_is_scored_from_raw_contact_forces():
    result = Experiment(fixed_closure=.95).run("fixed", headless=True)
    assert not result.metrics["success"]
    assert "force_limit" in result.metrics["reasons"]
    assert result.metrics["peak_force_N"] > result.config.force_limit_N
    assert result.metrics["longest_overforce_s"] >= result.config.overforce_duration_s


def test_same_experiment_restarts_rng_model_and_sampler():
    experiment = Experiment(noise_std_N=.1, seed=7)
    first = experiment.run(headless=True)
    second = experiment.run(headless=True)
    for key in first.trace:
        np.testing.assert_array_equal(first.trace[key], second.trace[key])
    assert first.metrics == second.metrics


def test_no_contact_means_zero_taxels_and_no_self_contact_force():
    scene = Scene(ExperimentConfig())
    taxels, sensors, other_force, _ = TactileReader(scene).read()
    assert not taxels.any() and not sensors.any() and other_force == 0


def test_scoring_rejects_external_support_and_tolerates_short_force_spike():
    config = ExperimentConfig()
    evaluator = Evaluator(config, np.array([0., 0., .1]))
    evaluator.update(0, .0005, 100, np.array([0., 0., .1]), 0)
    evaluator.update(.0005, .0005, 0, np.array([0., 0., .1]), 0)
    assert "force_limit" not in evaluator.reasons
    for _ in range(50):
        evaluator.update(config.release_time_s + .1, .0005, 4, np.array([0., 0., .1]), 1)
    assert "external_support" in evaluator.reasons


def test_nonfinite_student_action_is_rejected():
    with pytest.raises(ValueError, match="non-finite"):
        Experiment().run(lambda obs: float("nan"), headless=True)


def test_policy_only_receives_readonly_tactile_not_object_ground_truth():
    observed = []
    def inspect(obs):
        observed.append(obs)
        assert not hasattr(obs, "object_position_m")
        with pytest.raises(ValueError):
            obs.taxel_normal_N[0] = 1000
        return 0
    # Avoid a long run just for checking the observation boundary.
    config = ExperimentConfig(approach_time_s=0, release_time_s=.1, hold_time_s=.1, disturbance=False)
    Experiment(config).run(inspect, headless=True)
    assert observed


def test_resources_resolve_from_another_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    scene = Scene(ExperimentConfig())
    assert scene.model.nq == 23
    assert tuple(scene.model.opt.gravity) == (0, 0, -9.81)


def test_csv_json_and_npz_can_be_read_without_pickle(tmp_path):
    result = Experiment(approach_time_s=0, release_time_s=.1, hold_time_s=.1, disturbance=False).run(headless=True)
    result.save(tmp_path)
    import json
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["controller"] == "tactile"
    with np.load(tmp_path / "episode.npz", allow_pickle=False) as archive:
        np.testing.assert_array_equal(archive["taxel_normal_N"], result.trace["taxel_normal_N"])
    assert (tmp_path / "trace.csv").read_text().startswith("time_s,tactile_time_s,phase")


def test_dashboard_pixels_and_3d_taxels_without_opengl(monkeypatch, tmp_path):
    # Exercise the actual panel drawing and MuJoCo geometry creation. Only the
    # native window transport is replaced; this is not a real GUI smoke test.
    from contextlib import nullcontext
    import mujoco
    from mujoco import viewer as mjviewer
    from lab2 import viewer
    scene = Scene(ExperimentConfig())
    reader = TactileReader(scene)
    class Handle:
        def __init__(self):
            self.cam = mujoco.MjvCamera()
            self.user_scn = mujoco.MjvScene(scene.model, maxgeom=2000)
            self.viewport = mujoco.MjrRect(0, 0, 1200, 800)
        def lock(self): return nullcontext()
        def is_running(self): return True
        def sync(self): pass
        def close(self): pass
        def set_texts(self, text): self.text = text
        def set_images(self, pair):
            rect, image = pair
            assert image.shape == (rect.height, rect.width, 3)
            assert image.dtype == np.uint8
            self.image = image
    handle = Handle()
    monkeypatch.setattr(viewer, "check_display", lambda: None)
    monkeypatch.setattr(mjviewer, "launch_passive", lambda *a, **kw: handle)
    live = viewer.LiveViewer(scene, reader, ExperimentConfig())
    experiment = Experiment()
    obs = experiment._observation(0, 0, 0, 0, np.zeros(11), np.zeros(1140))
    trace = {"time_s": [0], "grip_force_N": [0], "object_height_m": [.0667]}
    live.update(obs, trace)
    assert handle.user_scn.ngeom == 1140
    assert handle.image.std() > 10
    from matplotlib import image as mpl_image
    mpl_image.imsave(tmp_path / "dashboard-default.png", handle.image)
    live.on_key(ord("]"))
    assert live.sensor_index == 3
    live.refresh_if_needed(obs, trace, "PASS | finished")
    assert "4/11" in live.figure.axes[0].get_title()
    # Finished physics still permits key-driven panel redraw without stepping.
    time_before, qpos_before = scene.data.time, scene.data.qpos.copy()
    previous_pixels = handle.image.copy()
    live.on_key(ord("N"))
    live.refresh_if_needed(obs, trace, "PASS | finished")
    assert "5/11" in live.figure.axes[0].get_title()
    assert not np.array_equal(previous_pixels, handle.image)
    assert scene.data.time == time_before
    np.testing.assert_array_equal(scene.data.qpos, qpos_before)
    live.on_key(ord("P"))
    live.refresh_if_needed(obs, trace, "PASS | finished")
    assert "4/11" in live.figure.axes[0].get_title()
    # Small resized windows are a common source of image/viewport mismatch.
    handle.viewport = mujoco.MjrRect(0, 0, 701, 513)
    live.refresh_if_needed(obs, trace, "PASS | finished")
    mpl_image.imsave(tmp_path / "dashboard.png", handle.image)


def test_finished_runner_services_panel_redraw_without_advancing_physics(monkeypatch):
    from lab2 import viewer
    experiment = Experiment(approach_time_s=0, release_time_s=.02,
                            hold_time_s=.02, disturbance=False)
    class Window:
        def __init__(self, scene, *args):
            self.scene = scene
            self.running = True
            self.finished_time = None
            self.refresh_count = 0
        def is_running(self): return self.running
        def update(self, obs, trace, result_text=None):
            if result_text is not None:
                self.finished_time = self.scene.data.time
        def refresh_if_needed(self, obs, trace, result_text=None):
            assert self.finished_time is not None
            assert self.scene.data.time == self.finished_time
            self.refresh_count += 1
            self.running = False
        def close(self): pass
    windows = []
    def open_window(*args):
        window = Window(*args)
        windows.append(window)
        return window
    monkeypatch.setattr(viewer, "LiveViewer", open_window)
    result = experiment.run(headless=False)
    assert result.metrics["completed"]
    assert windows[0].refresh_count == 1
