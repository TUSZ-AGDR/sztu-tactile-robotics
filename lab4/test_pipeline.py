"""Checks for leakage, causal windows and frozen pretrained modules."""
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np
import torch

from .data import load_windows
from .models import Autoencoder, LatentTranslator
from .prepare import SavedReplay


class PipelineTests(unittest.TestCase):
    def test_unsupported_replay_version_fails_before_reading_geometry(self):
        with patch("lab4.prepare.mujoco.__version__", "3.8.0"):
            with self.assertRaisesRegex(RuntimeError, "Lab 4 environment"):
                SavedReplay("unused-path")

    def pack(self, path, leak=False):
        n = 24
        values = np.arange(n, dtype=np.float32)
        np.savez(path, x=np.column_stack([values, values / 2]),
                 y=np.column_stack([values, values * 2, values * 3]),
                 time=np.tile(np.arange(8) / 10, 3), sequence=np.repeat(["a", "b", "c"], 8),
                 parent=np.repeat(["p1", "p1" if leak else "p2", "p3"], 8),
                 split=np.repeat(["train", "validation", "test"], 8),
                 source_kind=np.full(n, "synthetic_sensor"), feature_names=np.array(["x", "y"]))

    def test_windows_are_causal_and_do_not_cross_episode_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.npz"
            self.pack(path)
            data = load_windows(path, window=3)
        self.assertEqual(len(data["indices"]), 18)
        for rows in data["indices"]:
            self.assertEqual(rows[0] // 8, rows[-1] // 8)
            np.testing.assert_array_equal(rows, np.arange(rows[-1] - 2, rows[-1] + 1))
        np.testing.assert_allclose(data["x_scaler"].mean, [3.5, 1.75])
        # Validation/test values are much larger and must not alter this mean.
        self.assertEqual(data["target"][-1, 0], 23)

    def test_augmented_parent_split_leakage_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.npz"
            self.pack(path, leak=True)
            with self.assertRaisesRegex(ValueError, "Parent leakage"):
                load_windows(path)

    def test_only_latent_mapping_is_updated(self):
        torch.manual_seed(5)
        sa, ra = Autoencoder(12, 8), Autoencoder(9, 4)
        model = LatentTranslator(sa, ra)
        before = {name: p.detach().clone() for name, p in model.named_parameters()}
        optimizer = torch.optim.Adam(model.mapping.parameters(), lr=.01)
        optimizer.zero_grad()
        model.objective(torch.randn(10, 12), torch.randn(10, 9)).backward()
        optimizer.step()
        changed = []
        for name, p in model.named_parameters():
            if not torch.equal(before[name], p):
                changed.append(name)
        self.assertTrue(changed)
        self.assertTrue(all(name.startswith("mapping.") for name in changed))
        # Inference takes simulation input only.
        self.assertEqual(tuple(model(torch.randn(2, 12)).shape), (2, 9))


if __name__ == "__main__":
    unittest.main()
