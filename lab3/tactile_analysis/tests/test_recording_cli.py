from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
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

from tactile_analysis import AnalysisConfig, analyze_trial
from tactile_analysis.cli import main
from tactile_analysis.convert_recording import OperationCancelled, convert_recording
from tactile_analysis.recording import load_recording
from tactile_analysis.report import analyze_recording


@unittest.skipIf(h5py is None, "requires CLI extras")
class RecordingCliTest(unittest.TestCase):
    def setUp(self):
        # Reuse the multi-chunk fixture without adding another discovered TestCase.
        import test_convert_recording as fixture_module
        fixture = fixture_module.ConvertRecordingTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.root, self.base = fixture.root, fixture.base
        self.archive = fixture.make_zip()

    def run_cli(self, args, expected=0):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            if expected == 0:
                self.assertEqual(main(args + ["--quiet", "--json"]), 0)
            else:
                with self.assertRaises(SystemExit) as caught:
                    main(args + ["--quiet", "--json"])
                self.assertEqual(caught.exception.code, expected)
        return stdout.getvalue(), stderr.getvalue()

    def test_zip_directory_hdf5_parity_without_qt(self):
        a, b = load_recording(self.archive), load_recording(self.root)
        output = self.base / "converted.h5"
        convert_recording(self.archive, output)
        c = load_recording(output)
        for side in ("left", "right"):
            config = AnalysisConfig(allow_unverified=True)
            reference = analyze_trial(a.trials[side], config)
            for other in (b, c):
                result = analyze_trial(other.trials[side], config)
                self.assertEqual(reference.summary, result.summary)
                for key in reference.frame_metrics:
                    np.testing.assert_array_equal(reference.frame_metrics[key], result.frame_metrics[key])

    def test_list_trials_creates_no_output(self):
        text, _ = self.run_cli([str(self.archive), "--list-trials"])
        info = json.loads(text)
        self.assertEqual(info["verified_npz_count"], 6)
        self.assertEqual([t["trial"] for t in info["trials"]], ["left", "right"])
        self.assertFalse(self.fixture.output.exists())

    def test_raw_cli_all_hands_and_output_contract(self):
        output = self.base / "raw"
        text, _ = self.run_cli([str(self.archive), "--trial", "all", "--allow-unverified",
                                "--contact-threshold", "10", "--heatmap-frame", "1", "--output-dir", str(output)])
        self.assertEqual(json.loads(text)["output_dir"], str(output.resolve()))
        report = json.loads((output / "report.json").read_text())
        self.assertEqual(set(report["summaries"]), {"left", "right"})
        self.assertEqual(report["temperature_summary"]["left"]["reading_count"], 1)
        for filename in ("overview.png", "taxel_heatmap.png", "sensor_summary.png", "temperature.png",
                         "temperature_events.csv", "trial_01/frame_metrics.csv", "trial_01/heatmap_1.png"):
            self.assertTrue((output / filename).exists())
        _, error = self.run_cli([str(self.archive), "--allow-unverified", "--output-dir", str(output)], 1)
        self.assertIn("已存在", error)

    def test_strict_raw_rejects_unverified_and_cleans_output(self):
        output = self.base / "strict"
        _, error = self.run_cli([str(self.archive), "--output-dir", str(output)], 1)
        self.assertIn("allow_unverified", error)
        self.assertFalse(output.exists())
        self.assertFalse(list(self.base.glob(".analysis-*")))

    def test_bad_trial_and_nonfinite_threshold(self):
        _, error = self.run_cli([str(self.archive), "--trial", "missing"], 1)
        self.assertIn("可用数据组", error)
        _, error = self.run_cli([str(self.archive), "--allow-unverified", "--contact-threshold", "nan",
                                 "--output-dir", str(self.base / "nan")], 1)
        self.assertIn("有限", error)

    def test_cancelled_conversion_and_raw_report_publish_nothing(self):
        with self.assertRaises(OperationCancelled):
            convert_recording(self.archive, self.base / "cancelled.h5", cancelled=lambda: True)
        with self.assertRaises(OperationCancelled):
            analyze_recording(load_recording(self.archive), ["left"], self.base / "cancelled", cancelled=lambda: True)
        self.assertFalse((self.base / "cancelled").exists())
        self.assertFalse(list(self.base.glob(".analysis-*")))

    def test_physical_cli_demo_and_raw_flag_rejection(self):
        spec = importlib.util.spec_from_file_location("physical_demo", Path(__file__).parents[1] / "examples/make_physical_demo.py")
        demo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(demo)
        trial, calibration = demo.make_demo(self.base / "demo")
        output = self.base / "physical"
        text, _ = self.run_cli([str(trial), "--trial", "left", "--calibration", str(calibration),
                                "--normal-threshold-n", "0.1", "--output-dir", str(output)])
        self.assertEqual(json.loads(text)["summary"]["contact_area_mm2_peak"], 6)
        _, error = self.run_cli([str(trial), "--calibration", str(calibration), "--allow-unverified",
                                 "--output-dir", str(self.base / "bad-physical")], 1)
        self.assertIn("仅用于原始诊断", error)
