from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

try:
    import h5py
    import matplotlib
except ImportError:
    h5py = None

from tactile_analysis.io import load_hdf5
from tactile_analysis.physical import analyze_physical, export_physical


@unittest.skipIf(h5py is None, "requires CLI extras")
class PhysicalTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        spec = importlib.util.spec_from_file_location("physical_demo", Path(__file__).parents[1] / "examples/make_physical_demo.py")
        demo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(demo)
        self.h5, self.calibration = demo.make_demo(self.root)
        self.trial = load_hdf5(self.h5, trial="left")

    def change_calibration(self, **changes):
        with np.load(self.calibration, allow_pickle=False) as data:
            arrays = {key: data[key] for key in data.files}
        arrays.update({key: np.asarray(value) for key, value in changes.items()})
        np.savez_compressed(self.calibration, **arrays)

    def test_known_area_normal_force_pressure_and_shear(self):
        r = analyze_physical(self.trial, self.calibration)
        np.testing.assert_allclose(r.frame_metrics["contact_area_mm2"], [0, 4, 6])
        np.testing.assert_allclose(r.frame_metrics["normal_force_sum_n"], [0, 3, 6])
        np.testing.assert_allclose(r.frame_metrics["mean_pressure_kpa"][1:], [750, 1000])
        self.assertTrue(np.isnan(r.frame_metrics["mean_pressure_kpa"][0]))
        self.assertEqual(r.summary["peak_pressure_pa"], 1_500_000)
        self.assertAlmostEqual(r.frame_metrics["tangential_magnitude_sum_n"][1], .3)
        self.assertEqual(r.summary["normal_force_impulse_n_s"], 6)
        self.assertEqual(r.summary["contact_duration_s"], 2)
        self.assertTrue(np.isnan(r.pressure_pa[:, 2]).all())
        self.assertFalse(r.contact_mask[:, 2].any())

    def test_normal_direction_is_not_assumed_to_be_z(self):
        self.change_calibration(normal_vectors=[1., 0., 0.])
        r = analyze_physical(self.trial, self.calibration)
        self.assertAlmostEqual(r.normal_force_n[1, 0], .3)
        self.assertEqual(r.frame_metrics["contact_area_mm2"][1], 2)
        self.assertAlmostEqual(r.frame_metrics["mean_pressure_pa"][1], 150_000)

    def test_bias_and_per_taxel_matrix_are_applied(self):
        matrix = np.tile(np.diag([.2, .3, .4]), (4, 1, 1))
        self.change_calibration(force_matrix_n_per_count=matrix, bias_counts=[0., 0., 10.])
        r = analyze_physical(self.trial, self.calibration)
        self.assertEqual(r.frame_metrics["normal_force_sum_n"][1], 4)
        self.assertEqual(r.frame_metrics["mean_pressure_pa"][1], 2_000_000)

    def test_unequal_areas_use_area_weighted_mean_pressure(self):
        self.change_calibration(taxel_area_mm2=[1., 3., 2., 2.])
        r = analyze_physical(self.trial, self.calibration)
        self.assertEqual(r.frame_metrics["mean_pressure_pa"][1], 750_000)
        self.assertEqual(r.frame_metrics["peak_pressure_pa"][2], 2_000_000)

    def test_invalid_frames_are_nan_and_not_integrated_across(self):
        mask = self.trial.taxel_valid_mask.copy()
        mask[1] = False
        trial = replace(self.trial, taxel_valid_mask=mask, packet_valid=np.array([True, False, True]),
                        sample_valid=np.array([True, False, True]))
        r = analyze_physical(trial, self.calibration)
        self.assertTrue(np.isnan(r.frame_metrics["contact_area_mm2"][1]))
        self.assertTrue(np.isnan(r.frame_metrics["mean_pressure_pa"][1]))
        self.assertEqual(r.summary["normal_force_impulse_n_s"], 0)
        self.assertEqual(r.summary["contact_duration_s"], 0)
        self.assertEqual(r.summary["invalid_frames"], 1)

    def test_calibration_never_promotes_all_false_source_masks(self):
        trial = replace(self.trial, taxel_valid_mask=np.zeros((3, 4), dtype=bool),
                        sample_valid=np.zeros(3, dtype=bool))
        with self.assertRaisesRegex(ValueError, "does not override"):
            analyze_physical(trial, self.calibration)

    def test_no_contact_is_distinct_from_no_valid_data(self):
        r = analyze_physical(replace(self.trial, detail_xyz=np.zeros((3, 4, 3))), self.calibration)
        self.assertEqual(r.summary["valid_frames"], 3)
        self.assertEqual(r.summary["contact_area_mm2_peak"], 0)
        self.assertIsNone(r.summary["mean_pressure_pa_mean"])
        self.assertIsNone(r.summary["peak_pressure_pa"])

    def test_synthetic_calibration_cannot_process_real_recording(self):
        trial = replace(self.trial, metadata={"hand_side": "left"})
        with self.assertRaisesRegex(ValueError, "cannot be used on real"):
            analyze_physical(trial, self.calibration)

    def test_bad_calibration_and_threshold_rejected(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            analyze_physical(self.trial, self.calibration, normal_threshold_n=0)
        self.change_calibration(normal_vectors=[0., 0., 2.])
        with self.assertRaisesRegex(ValueError, "unit length"):
            analyze_physical(self.trial, self.calibration)
        self.change_calibration(normal_vectors=[0., 0., 1.], taxel_area_mm2=float("nan"))
        with self.assertRaisesRegex(ValueError, "finite"):
            analyze_physical(self.trial, self.calibration)

    def test_export_is_readable_and_never_overwrites(self):
        r = analyze_physical(self.trial, self.calibration)
        output = self.root / "result"
        export_physical(r, output)
        data = json.loads((output / "summary.json").read_text())
        self.assertEqual(data["summary"]["contact_area_mm2_peak"], 6)
        for name in ("physical_arrays.npz", "physical_overview.png", "pressure_heatmap.png", "frame_metrics.csv"):
            self.assertTrue((output / name).exists())
        with self.assertRaises(FileExistsError):
            export_physical(r, output)
