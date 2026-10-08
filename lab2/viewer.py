"""Matplotlib Agg panels embedded in the official passive MuJoCo viewer."""
import os
import sys
from pathlib import Path
import numpy as np
import mujoco
from .scene import LAB_ROOT


def check_display():
    if sys.platform == "darwin":
        import ctypes
        core_graphics = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        count = ctypes.c_uint32()
        error = core_graphics.CGGetActiveDisplayList(0, None, ctypes.byref(count))
        if error or count.value == 0:
            raise RuntimeError("No macOS display is available. Run from a desktop Terminal, or add --headless/--compare.")
    elif sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise RuntimeError("No Linux display is available. Set up a desktop display, or add --headless/--compare.")


def plotting():
    # Configure a writable cache without selecting a GUI matplotlib backend.
    cache = LAB_ROOT / "outputs" / ".matplotlib"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache.parent / ".cache"))
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib import colormaps
    return Figure, FigureCanvasAgg, colormaps


def annotate_events(axis, config):
    axis.axvline(config.release_time_s, color=".45", linestyle=":", label="Release")
    if config.disturbance:
        start = config.release_time_s + config.pull_after_release_s
        axis.axvspan(start, start + config.pull_duration_s, color="orange", alpha=.15, label="Pull")


def plot_episode(result, path):
    Figure, Canvas, _ = plotting()
    fig = Figure(figsize=(10, 6), layout="constrained")
    Canvas(fig)
    axes = fig.subplots(2, 1, sharex=True)
    trace, config = result.trace, result.config
    axes[0].plot(trace["time_s"], trace["grip_force_N"], label=result.controller)
    axes[0].axhline(config.target_force_N, color="green", linestyle="--", label="Target")
    axes[0].axhline(config.force_limit_N, color="red", linestyle="--", label="Limit")
    axes[0].set_ylabel("Grip force (N)")
    axes[1].plot(trace["time_s"], trace["object_height_m"], label="Object height")
    axes[1].axhline(trace["object_height_m"][0] - config.drop_distance_m, color="red", linestyle="--", label="Drop threshold")
    axes[1].set_ylabel("Height (m)")
    axes[1].set_xlabel("Simulation time (s)")
    for axis in axes:
        annotate_events(axis, config)
        axis.grid(alpha=.2)
        axis.legend(loc="best")
    fig.suptitle(result.describe(), fontsize=10)
    fig.savefig(path, dpi=150)


def plot_heatmap(result, path, sensor_index=2):
    from dexh13sim.sensor_table import SENSOR_TABLE
    from dexh13sim.runtime import load_templates
    from .scene import SIM_ROOT
    Figure, Canvas, _ = plotting()
    spec = SENSOR_TABLE[sensor_index]
    template = load_templates(SIM_ROOT / "configs/taxel_templates")[spec.template]
    xyz = template.xyz_m - template.xyz_m.mean(axis=0)
    _, _, axes = np.linalg.svd(xyz, full_matrices=False)
    xy = xyz @ axes[:2].T * 1000
    time_s = result.config.release_time_s + result.config.hold_time_s / 2
    frame_index = int(np.abs(result.trace["time_s"] - time_s).argmin())
    values = result.trace["taxel_normal_N"][frame_index, spec.start:spec.end]
    fig = Figure(figsize=(5, 5), layout="constrained")
    Canvas(fig)
    axis = fig.subplots()
    scatter = axis.scatter(xy[:, 0], xy[:, 1], c=values, cmap="turbo", s=45,
                            vmin=0, vmax=LiveViewer.HEATMAP_MAX_N)
    axis.set_aspect("equal", adjustable="datalim")
    axis.set_xlabel("Template projection (mm)")
    axis.set_ylabel("Template projection (mm)")
    axis.set_title(f"{result.controller}: {spec.name}\nt={result.trace['time_s'][frame_index]:.2f}s")
    fig.colorbar(scatter, ax=axis, label="Normal force / taxel (N)", shrink=.8)
    fig.savefig(path, dpi=150)


def plot_comparison(results, path):
    Figure, Canvas, _ = plotting()
    fig = Figure(figsize=(10, 6), layout="constrained")
    Canvas(fig)
    axes = fig.subplots(2, 1, sharex=True)
    config = results[0].config
    for result in results:
        t = result.trace["time_s"]
        axes[0].plot(t, result.trace["grip_force_N"], label=result.controller)
        axes[1].plot(t, result.trace["object_height_m"], label=result.controller)
    axes[0].axhline(config.target_force_N, color="green", linestyle="--", label="Target")
    axes[0].axhline(config.force_limit_N, color="red", linestyle="--", label="Limit")
    axes[1].axhline(results[0].trace["object_height_m"][0] - config.drop_distance_m,
                    color="red", linestyle="--", label="Drop threshold")
    axes[0].set_ylabel("Grip force (N)")
    axes[1].set_ylabel("Height (m)")
    axes[1].set_xlabel("Simulation time (s)")
    for axis in axes:
        annotate_events(axis, config)
        axis.grid(alpha=.2)
        axis.legend(loc="best")
    fig.suptitle(f"Lab 2: {config.object_name}, mass={config.mass_kg:g} kg, friction={config.friction:g}")
    fig.savefig(path, dpi=150)


class LiveViewer:
    HEATMAP_MAX_N = 0.25

    def __init__(self, scene, tactile, config):
        check_display()
        from mujoco import viewer
        if not all(hasattr(viewer.Handle, method) for method in ("set_images", "set_texts")):
            raise RuntimeError("Lab 2 needs the official mujoco==3.8.0 viewer overlays. Install lab2/requirements.txt.")
        self.scene, self.tactile, self.config = scene, tactile, config
        self.sensor_index = 2
        self._rendered_selection = None
        self._rendered_viewport = None
        self.handle = viewer.launch_passive(scene.model, scene.data, key_callback=self.on_key,
                                            show_left_ui=False, show_right_ui=False)
        with self.handle.lock():
            self.handle.cam.lookat[:] = [.12, -.03, .045]
            self.handle.cam.distance = .36
            self.handle.cam.azimuth = 130
            self.handle.cam.elevation = -35
        from dexh13sim.sensor_table import SENSOR_TABLE
        from dexh13sim.taxel_overlay import TaxelHeatmapOverlay
        self.specs = SENSOR_TABLE
        self.overlay = TaxelHeatmapOverlay(tactile.mount, tactile.templates)
        Figure, Canvas, colormaps = plotting()
        self.figure = Figure(figsize=(4, 7), dpi=128, layout="constrained")
        self.canvas = Canvas(self.figure)
        self.colormap = colormaps["turbo"]
        self.projected = {}
        for template_name, template in tactile.templates.items():
            xyz = template.xyz_m - template.xyz_m.mean(axis=0)
            _, _, axes = np.linalg.svd(xyz, full_matrices=False)
            uv = xyz @ axes[:2].T
            self.projected[template_name] = uv * 1000

    def on_key(self, key):
        if key in (ord("]"), ord("N"), ord("n")):
            self.sensor_index = (self.sensor_index + 1) % 11
        elif key in (ord("["), ord("P"), ord("p")):
            self.sensor_index = (self.sensor_index - 1) % 11

    def is_running(self):
        return self.handle.is_running()

    def refresh_if_needed(self, obs, trace, result_text=None):
        """Keep sensor selection and resize responsive after physics stops."""
        rect = self.handle.viewport
        viewport = (rect.left, rect.bottom, rect.width, rect.height)
        if self.sensor_index != self._rendered_selection or viewport != self._rendered_viewport:
            self.update(obs, trace, result_text)
        else:
            self.sync()

    def update(self, obs, trace, result_text=None):
        if not self.is_running():
            return
        rect = self.handle.viewport
        selected = self.sensor_index
        width = min(480, max(240, int(rect.width * .38)))
        height = max(240, int(rect.height))
        # Binary-exact inches avoid the 455/456-pixel rounding mismatch that
        # the passive viewer rejects for overlay images.
        self.figure.set_size_inches(width / 128, height / 128, forward=False)
        self.figure.clear()
        heat, force, position = self.figure.subplots(3, 1, gridspec_kw={"height_ratios": [1.3, 1, 1]})
        spec = self.specs[selected]
        xy = self.projected[spec.template]
        scatter = heat.scatter(xy[:, 0], xy[:, 1], c=obs.taxel_normal_N[spec.start:spec.end],
            s=18, cmap=self.colormap, vmin=0, vmax=self.HEATMAP_MAX_N)
        heat.set_aspect("equal", adjustable="box")
        heat.set_title(f"{selected + 1}/{len(self.specs)}: {spec.name}\nP previous / N next", fontsize=7.5)
        heat.set_xlabel("Projection / mm", fontsize=6)
        heat.tick_params(labelsize=6)
        colorbar = self.figure.colorbar(scatter, ax=heat, shrink=.8)
        colorbar.set_label("N / taxel", fontsize=7)
        colorbar.ax.tick_params(labelsize=6)
        t = trace["time_s"]
        measured, = force.plot(t, trace["grip_force_N"], color="royalblue", linewidth=1.4, label="Measured")
        target = force.axhline(self.config.target_force_N, color="green", linestyle="--", label="Target")
        limit = force.axhline(self.config.force_limit_N, color="red", linestyle="--", label="Limit")
        force.set_ylabel("Grip / N", fontsize=7)
        force.set_ylim(0, max(self.config.force_limit_N * 1.15, max(trace["grip_force_N"]) * 1.1))
        position.plot(t, trace["object_height_m"], color="royalblue")
        position.axhline(self.scene.initial_position[2] - self.config.drop_distance_m, color="red", linestyle="--")
        position.set_ylabel("Height / m", fontsize=7)
        position.set_xlabel("Time / s", fontsize=7)
        for axis in (force, position):
            annotate_events(axis, self.config)
            axis.set_xlim(0, self.config.duration_s)
            axis.tick_params(labelsize=6)
            axis.grid(alpha=.2)
        force.legend(handles=[measured, target, limit], fontsize=5.5, loc="upper right")
        self.canvas.draw()
        rgb = np.ascontiguousarray(np.asarray(self.canvas.buffer_rgba())[:, :, :3])
        self.handle.set_images((mujoco.MjrRect(rect.left + rect.width - width, rect.bottom, width, height), rgb))
        text = result_text or (f"{obs.phase} | t={obs.time_s:.2f}s | closure={obs.closure:.3f} "
                              f"| force={obs.grip_force_N:.2f}N | tactile t={obs.tactile_time_s:.2f}s")
        self.handle.set_texts((None, None, "Lab 2", text))
        positions = self.overlay.world_positions(self.scene.data)
        colors = self.colormap(np.clip(obs.taxel_normal_N / self.HEATMAP_MAX_N, 0, 1))
        with self.handle.lock():
            scene = self.handle.user_scn
            scene.ngeom = 0
            for index, (point, color) in enumerate(zip(positions, colors)):
                if scene.ngeom >= len(scene.geoms):
                    break
                rgba = color.copy()
                rgba[3] = .25 if obs.taxel_normal_N[index] < 1e-5 else .95
                mujoco.mjv_initGeom(scene.geoms[scene.ngeom], mujoco.mjtGeom.mjGEOM_SPHERE,
                    np.array([.0008, 0., 0.]), point, np.eye(3).ravel(), rgba)
                scene.ngeom += 1
        self.sync()
        self._rendered_selection = selected
        self._rendered_viewport = (rect.left, rect.bottom, rect.width, rect.height)

    def sync(self):
        self.handle.sync()

    def close(self):
        self.handle.close()
