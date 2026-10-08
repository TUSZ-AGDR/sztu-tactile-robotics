import numpy as np

from dexh13sim.sensor_table import SensorSpec
from dexh13sim.tactile_renderer import TactileRenderer


class ToyTemplate:
    xyz_m = np.array([[0.0, 0.0, 0.0], [0.002, 0.0, 0.0]], dtype=np.float64)
    normals = np.array([[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]], dtype=np.float64)


def test_renderer_distributes_contact_force_and_conserves_force():
    specs = [SensorSpec(0, "sensor1", "toy_sensor", "toy", 2, 0, 2)]
    renderer = TactileRenderer(
        sensor_specs=specs,
        templates={"toy": ToyTemplate()},
        template_config={
            "toy": {
                "sigma_t0": 0.003,
                "sigma_n0": 0.0015,
                "outside_reject_dist": 0.01,
                "max_abs_normal_offset": 0.006,
                "min_raw_weight": 1.0e-4,
            }
        },
        total_taxels=2,
    )

    tactile = renderer.render(
        [
            {
                "sensor_id": 0,
                "p_sensor": np.array([0.0, 0.0, 0.0]),
                "f_sensor": np.array([1.0, 2.0, 3.0]),
            }
        ]
    )

    assert tactile.shape == (2, 3)
    assert tactile[0, 2] > tactile[1, 2]
    assert np.allclose(tactile.sum(axis=0), [1.0, 2.0, 3.0])


def test_renderer_rejects_contacts_outside_sensor_patch():
    specs = [SensorSpec(0, "sensor1", "toy_sensor", "toy", 2, 0, 2)]
    renderer = TactileRenderer(
        sensor_specs=specs,
        templates={"toy": ToyTemplate()},
        template_config={
            "toy": {
                "sigma_t0": 0.003,
                "sigma_n0": 0.0015,
                "outside_reject_dist": 0.001,
                "max_abs_normal_offset": 0.006,
                "min_raw_weight": 1.0e-4,
            }
        },
        total_taxels=2,
    )

    tactile = renderer.render(
        [
            {
                "sensor_id": 0,
                "p_sensor": np.array([0.1, 0.0, 0.0]),
                "f_sensor": np.array([1.0, 2.0, 3.0]),
            }
        ]
    )

    assert np.count_nonzero(tactile) == 0
