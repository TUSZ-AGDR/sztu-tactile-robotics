import tempfile
import unittest
from pathlib import Path

import numpy as np

from tactile_analysis import AnalysisConfig, TactileTrial, analyze_trial


class AnalysisTest(unittest.TestCase):
    def test_metrics_with_calibrated_area(self):
        detail = np.zeros((3, 4, 3), dtype=float)
        detail[:, :2, 0] = 1.0
        trial = TactileTrial(detail, timestamps_ns=np.array([0, 1_000_000_000, 2_000_000_000]))
        result = analyze_trial(trial, AnalysisConfig(contact_threshold=0.5, taxel_area_mm2=2.0))
        self.assertEqual(result.summary["active_taxel_count_peak"], 2)
        self.assertEqual(result.summary["contact_area_mm2_peak"], 4.0)
        self.assertAlmostEqual(result.summary["contact_duration_s"], 2.0)
        self.assertIn("mean_pressure", result.frame_metrics)

    def test_missing_area_is_explicit(self):
        trial = TactileTrial(np.ones((2, 3, 3)))
        result = analyze_trial(trial, AnalysisConfig(contact_threshold=0.1))
        self.assertIsNone(result.summary["contact_area_mm2_mean"])
        self.assertIsNone(result.summary["pressure_unit"])
        self.assertEqual(result.summary["time_source"], "frame_index")
