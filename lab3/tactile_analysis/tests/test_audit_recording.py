"""Check that raw diagnostics never promote unverified samples to contact."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np


spec = importlib.util.spec_from_file_location(
    "audit_recording", Path(__file__).parents[1] / "examples" / "audit_recording.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AuditRecordingTest(unittest.TestCase):
    def data(self):
        raw = np.zeros((2, 1140, 3), dtype=np.int32)
        raw[:, 10] = [-128, 0, 255]
        return {"taxel_raw": raw, "sensor_summary_raw": np.zeros((2, 11, 3), dtype=np.int32),
                "timestamp_ns": np.array([1_000_000, 101_000_000], dtype=np.int64),
                "query_begin_ns": np.array([0, 100_000_000], dtype=np.int64),
                "hand_side": np.array(["left", "left"]),
                "packet_valid": np.ones(2, dtype=bool), "sample_valid": np.zeros(2, dtype=bool),
                "taxel_valid_mask": np.zeros((2, 1140), dtype=bool)}

    def test_nonzero_unverified_is_diagnostic_only(self):
        data = self.data()
        result, derived = audit.tactile_metrics(data, "left", 0)
        self.assertIsNone(result["physical_contact_metrics"])
        self.assertEqual(result["sample_valid_frames"], 0)
        self.assertEqual(result["ever_nonzero_taxels"], 1)
        self.assertEqual(result["z_255_frames"], 2)
        self.assertFalse(derived["taxel_valid_mask"].any())
        np.testing.assert_array_equal(data["taxel_raw"][:, 10], [[-128, 0, 255]] * 2)

    def test_inconsistent_sample_valid_rejected(self):
        data = self.data()
        data["sample_valid"][:] = True
        with self.assertRaisesRegex(ValueError, "Inconsistent sample_valid"):
            audit.tactile_metrics(data, "left", 0)

    def test_nearest_time_offsets_include_boundaries(self):
        source = np.array([-2, 4, 12], dtype=np.int64) * 1_000_000
        target = np.array([0, 10], dtype=np.int64) * 1_000_000
        np.testing.assert_array_equal(audit.nearest_offsets(source, target), [-2, 4, 2])

    def test_hash_mismatch_rejected_before_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bad.npz").write_bytes(b"corrupted")
            manifest = {"streams": {"left_tactile": {
                "chunks": [{"file": "bad.npz", "sha256": "0" * 64}]}}}
            with self.assertRaisesRegex(ValueError, "Hash mismatch"):
                audit.load_streams(root, manifest)
