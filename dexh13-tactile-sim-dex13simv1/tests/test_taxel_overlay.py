from __future__ import annotations

import mujoco
import numpy as np

from dexh13sim.runtime import TactileRuntime
from dexh13sim.sensor_table import total_taxels
from dexh13sim.taxel_overlay import TaxelHeatmapOverlay
from scripts.view_tactile_live import sync_taxel_overlay


def test_taxel_overlay_computes_world_positions_for_all_taxels():
    model = mujoco.MjModel.from_xml_path("assets/dexh13_mjcf/free_object_scene.xml")
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    runtime = TactileRuntime(model)
    overlay = TaxelHeatmapOverlay(runtime.mount, runtime.templates)

    positions = overlay.world_positions(data)

    assert positions.shape == (total_taxels(), 3)
    assert np.isfinite(positions).all()


def test_taxel_overlay_writes_heatmap_geoms_to_user_scene():
    model = mujoco.MjModel.from_xml_path("assets/dexh13_mjcf/free_object_scene.xml")
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    runtime = TactileRuntime(model)
    overlay = TaxelHeatmapOverlay(runtime.mount, runtime.templates, stride=1)
    raw = np.zeros((total_taxels(), 3), dtype=np.float32)
    raw[200, 2] = 2.0
    scene = mujoco.MjvScene(model, maxgeom=total_taxels() + 32)

    overlay.update_scene(scene, data, raw)

    assert scene.ngeom == total_taxels()
    assert float(scene.geoms[200].rgba[0]) > float(scene.geoms[0].rgba[0])
    assert float(scene.geoms[200].size[0]) > float(scene.geoms[0].size[0])


def test_viewer_overlay_sync_can_run_every_step_with_latest_raw_frame():
    class FakeLock:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, tb):
            return None

    class FakeViewer:
        user_scn = object()

        def lock(self):
            return FakeLock()

    class FakeOverlay:
        def __init__(self):
            self.calls = 0

        def update_scene(self, scene, data, raw):
            self.calls += 1

    overlay = FakeOverlay()

    assert sync_taxel_overlay(FakeViewer(), overlay, object(), np.zeros((1140, 3), dtype=np.float32))
    assert sync_taxel_overlay(FakeViewer(), overlay, object(), np.zeros((1140, 3), dtype=np.float32))
    assert overlay.calls == 2
