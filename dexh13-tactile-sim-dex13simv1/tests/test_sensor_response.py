import numpy as np

from dexh13sim.sensor_response import SensorResponse
from dexh13sim.sensor_table import SensorSpec


def test_response_applies_axis_matrix_gain_bias_clip_and_sdk_scale():
    specs = [SensorSpec(0, "sensor1", "toy_sensor", "toy", 1, 0, 1)]
    response = SensorResponse(
        sensor_specs=specs,
        sensor_matrices={"toy_sensor": np.eye(3)},
        template_config={
            "toy": {
                "A_matrix": [[2, 0, 0], [0, 1, 0], [0, 0, 1]],
                "bias_N": [1, 0, 0],
                "noise_std_N": [0, 0, 0],
                "clip_N": {"x": [-10, 10], "y": [-10, 10], "z": [0, 25]},
            }
        },
        lsb_per_N=10.0,
        random_seed=0,
    )

    detail_N, detail_sdk = response.apply(np.array([[8.0, -20.0, 30.0]], dtype=np.float32))

    assert np.allclose(detail_N, [[10.0, -10.0, 25.0]])
    assert np.allclose(detail_sdk, [[100.0, -100.0, 250.0]])


def test_response_keeps_zero_raw_frame_zero_even_with_noise_config():
    specs = [SensorSpec(0, "sensor1", "toy_sensor", "toy", 2, 0, 2)]
    response = SensorResponse(
        sensor_specs=specs,
        sensor_matrices={"toy_sensor": np.eye(3)},
        template_config={
            "toy": {
                "A_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                "bias_N": [0, 0, 0],
                "noise_std_N": [0.5, 0.5, 0.5],
                "clip_N": {"x": [-10, 10], "y": [-10, 10], "z": [0, 25]},
            }
        },
        lsb_per_N=10.0,
        random_seed=0,
    )

    detail_N, detail_sdk = response.apply(np.zeros((2, 3), dtype=np.float32))

    assert np.count_nonzero(detail_N) == 0
    assert np.count_nonzero(detail_sdk) == 0
