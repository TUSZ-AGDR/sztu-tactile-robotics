import numpy as np

from dexh13sim.tactile_sampler import TactileSampler


def test_sampler_outputs_one_average_frame_every_200_steps():
    sampler = TactileSampler(sim_dt=0.0005, tactile_hz=10, shape=(2, 3))

    frame = None
    for step in range(199):
        frame = sampler.add(np.full((2, 3), step, dtype=np.float32))
        assert frame is None

    frame = sampler.add(np.full((2, 3), 199, dtype=np.float32))

    assert frame is not None
    assert frame.dtype == np.float32
    assert np.allclose(frame, np.full((2, 3), 99.5, dtype=np.float32))
    assert sampler.frames_emitted == 1
