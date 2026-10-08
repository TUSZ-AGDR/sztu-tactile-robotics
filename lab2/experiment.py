"""Repeatable experiment runner; rendering never drives simulation time."""
from dataclasses import replace
from pathlib import Path
import math
import time
import numpy as np
import mujoco
from .config import ExperimentConfig
from .controllers import Observation, fixed_policy, tactile_policy
from .scene import Scene
from .tactile import TactileReader
from .evaluation import Evaluator
from .results import ExperimentResult


class Experiment:
    def __init__(self, config=None, **parameters):
        self.config = replace(config, **parameters) if config is not None else ExperimentConfig(**parameters)
        self.scene = None

    def run(self, controller="tactile", *, headless=False, output_dir=None, keep_open=True):
        config = self.config
        if isinstance(controller, str) and controller not in ("fixed", "tactile"):
            raise ValueError("controller must be fixed, tactile, or a callable")
        if not isinstance(controller, str) and not callable(controller):
            raise TypeError("controller must be a callable or a built-in name")
        name = controller if isinstance(controller, str) else getattr(controller, "__name__", "student")
        scene = self.scene = Scene(config)  # A fresh model, data and RNG for every run.
        tactile = TactileReader(scene)
        evaluator = Evaluator(config, scene.initial_position)
        dt = float(scene.model.opt.timestep)
        steps_per_sample = 2000 // config.tactile_hz
        control_dt = steps_per_sample * dt
        fixed_closure = config.fixed_closure if config.fixed_closure is not None else scene.nominal_fixed_closure
        rng = np.random.default_rng(config.seed)
        closure = 0.0
        accumulator = np.zeros(1140)
        sensor_accumulator = np.zeros(11)
        zero_frame = np.zeros(1140)
        zero_sensors = np.zeros(11)
        observation = self._observation(0, 0, closure, 0, zero_sensors, zero_frame)
        trace = {key: [] for key in (
            "time_s", "tactile_time_s", "phase", "grip_force_N", "raw_grip_force_N",
            "closure", "object_height_m", "other_support_force_N", "support_active",
            "pull_force_N", "taxel_normal_N", "sensor_forces_N", "object_position_m", "qpos")}
        self._record(trace, observation, scene, 0, 0)
        fallback_total = 0
        viewer = None
        try:
            if not headless:
                from .viewer import LiveViewer
                viewer = LiveViewer(scene, tactile, config)
                viewer.update(observation, trace)
            # Window and font initialization must not consume experiment time
            # and cause the opening movement to run in a catch-up burst.
            wall_start = time.perf_counter()
            nsteps = round(config.duration_s / dt)
            last_display_time = -1.0
            for step in range(nsteps):
                t = step * dt
                if viewer is not None and not viewer.is_running():
                    break
                if step % steps_per_sample == 0:
                    if t < config.approach_time_s:
                        rate = 0.0
                    elif controller == "fixed":
                        rate = fixed_policy(observation, fixed_closure, config.max_closure_rate, control_dt)
                    elif controller == "tactile":
                        rate = tactile_policy(observation, config.controller_gain, config.deadband_N)
                    else:
                        rate = float(controller(observation))
                    if not math.isfinite(rate):
                        raise ValueError("student policy returned a non-finite closure rate")
                    rate = float(np.clip(rate, -config.max_closure_rate, config.max_closure_rate))
                    closure = float(np.clip(closure + rate * control_dt, 0, 1))
                scene.apply(closure, config, t)
                mujoco.mj_step(scene.model, scene.data)
                normal, sensors, other_force, fallbacks = tactile.read()
                fallback_total += fallbacks
                raw_force = float(sensors.sum())
                evaluator.update(t, dt, raw_force, scene.data.xpos[scene.object_body], other_force)
                if not np.all(np.isfinite(scene.data.qpos)) or np.any(scene.data.warning.number):
                    raise RuntimeError("MuJoCo reported an unstable simulation; reduce the gain or use preset parameters")
                accumulator += normal
                sensor_accumulator += sensors
                if (step + 1) % steps_per_sample == 0:
                    sample_time = (step + 1) * dt
                    sampled = accumulator / steps_per_sample
                    sampled_sensors = sensor_accumulator / steps_per_sample
                    sampled_raw_force = float(sampled_sensors.sum())
                    observed_force = max(0.0, sampled_raw_force + rng.normal(0, config.noise_std_N))
                    observation = self._observation(sample_time, sample_time, closure, observed_force,
                                                    sampled_sensors, sampled)
                    scene.apply(closure, config, sample_time)
                    self._record(trace, observation, scene, sampled_raw_force, other_force)
                    accumulator.fill(0)
                    sensor_accumulator.fill(0)
                    if viewer is not None and sample_time - last_display_time >= 1 / 15 - 1e-9:
                        viewer.update(observation, trace)
                        last_display_time = sample_time
                if viewer is not None and (step + 1) % steps_per_sample == 0:
                    remaining = (step + 1) * dt - (time.perf_counter() - wall_start)
                    if remaining > 0:
                        time.sleep(remaining)
            metrics = evaluator.summary(float(scene.data.time))
            metrics["taxel_fallback_assignments"] = fallback_total
            metrics["fixed_closure_used"] = fixed_closure if controller == "fixed" else None
            arrays = {key: np.asarray(value) for key, value in trace.items()}
            hold_mask = arrays["time_s"] >= config.release_time_s
            error = arrays["grip_force_N"][hold_mask] - config.target_force_N
            metrics["force_tracking_rmse_N"] = float(np.sqrt(np.mean(error ** 2))) if len(error) else None
            result = ExperimentResult(name, config, metrics, arrays)
            if output_dir is not None:
                result.save(output_dir)
                from .viewer import plot_episode, plot_heatmap
                plot_episode(result, Path(output_dir) / "curves.png")
                plot_heatmap(result, Path(output_dir) / "heatmap.png")
            if viewer is not None:
                viewer.update(observation, trace, result.describe())
                if keep_open:
                    while viewer.is_running():
                        viewer.refresh_if_needed(observation, trace, result.describe())
                        time.sleep(.03)
            return result
        finally:
            if viewer is not None:
                viewer.close()

    def _observation(self, t, tactile_t, closure, grip_force, sensors, taxels):
        # Copies prevent custom policy mutations from corrupting history/score.
        sensors = np.asarray(sensors).copy()
        taxels = np.asarray(taxels).copy()
        sensors.flags.writeable = False
        taxels.flags.writeable = False
        return Observation(t, tactile_t, self.config.phase(t), closure, grip_force,
                           self.config.target_force_N, sensors, taxels)

    def _record(self, trace, obs, scene, raw_force, other_force):
        values = {
            "time_s": obs.time_s, "tactile_time_s": obs.tactile_time_s,
            "phase": obs.phase, "grip_force_N": obs.grip_force_N,
            "raw_grip_force_N": raw_force, "closure": obs.closure,
            "object_height_m": float(scene.data.xpos[scene.object_body, 2]),
            "other_support_force_N": other_force,
            "support_active": bool(scene.data.eq_active[scene.support_eq]),
            "pull_force_N": self.config.pull_force_N if self.config.pulling(obs.time_s) else 0.0,
            "taxel_normal_N": obs.taxel_normal_N.copy(),
            "sensor_forces_N": obs.sensor_forces_N.copy(),
            "object_position_m": scene.data.xpos[scene.object_body].copy(),
            "qpos": scene.data.qpos.copy(),
        }
        for key, value in values.items():
            trace[key].append(value)
