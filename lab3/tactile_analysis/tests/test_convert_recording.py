import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import numpy as np

try:
    import h5py
except ImportError:
    h5py = None

from tactile_analysis import AnalysisConfig, analyze_trial, load_hdf5, load_npz
from tactile_analysis.convert_recording import convert_recording


@unittest.skipIf(h5py is None, "requires h5py")
class ConvertRecordingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "recording"
        self.root.mkdir()
        self.output = self.base / "output.h5"
        self.manifest = {"schema_version": 1, "trajectory_id": "fixture", "metadata": {},
                         "events_file": "events.jsonl", "streams": {}}
        for side in ("left", "right"):
            arrays = []
            for start in (10, 30):
                raw = np.zeros((2, 1140, 3), dtype=np.int32)
                raw[:, 10] = [-128, 127, 255]
                arrays.append({"taxel_raw": raw, "sensor_summary_raw": np.zeros((2, 11, 3), dtype=np.int32),
                               "timestamp_ns": np.array([start, start + 10], dtype=np.int64),
                               "query_begin_ns": np.array([start - 1, start + 9], dtype=np.int64),
                               "taxel_valid_mask": np.zeros((2, 1140), dtype=bool),
                               "packet_valid": np.ones(2, dtype=bool), "sample_valid": np.zeros(2, dtype=bool),
                               "hand_side": np.array([side, side])})
            self.add_stream(side + "_tactile", arrays)
        self.add_stream("auxiliary", [
            {"timestamp_ns": np.array([1], dtype=np.int64), "error": np.array([""])},
            {"timestamp_ns": np.array([2], dtype=np.int64), "error": np.array(["long unicode 错误"])}])
        self.events = (json.dumps({"timestamp_ns": 12, "event": "temperature_reading", "hand_side": "left",
                                  "readings": [{"finger_name": "Index", "sensor_id": 1, "temperature_c": 45.2}]})
                       + "\n" + json.dumps({"timestamp_ns": 9, "event": "other"}) + "\n")
        (self.root / "events.jsonl").write_text(self.events)
        self.save_manifest()

    def add_stream(self, name, arrays):
        fields = {k: {"dtype": str(v.dtype), "shape": list(v.shape[1:])} for k, v in arrays[0].items()}
        chunks = []
        for index, data in enumerate(arrays):
            file = self.root / f"{name}_{index:05d}.npz"
            np.savez_compressed(file, **data)
            chunks.append({"file": file.name, "rows": len(data["timestamp_ns"]),
                           "first_timestamp_ns": int(data["timestamp_ns"][0]),
                           "last_timestamp_ns": int(data["timestamp_ns"][-1]),
                           "sha256": hashlib.sha256(file.read_bytes()).hexdigest()})
        self.manifest["streams"][name] = {"fields": fields, "chunks": chunks,
                                          "rows": sum(c["rows"] for c in chunks)}

    def save_manifest(self):
        (self.root / "manifest.json").write_text(json.dumps(self.manifest))

    def make_zip(self, extra=None):
        output = self.base / "recording.zip"
        with zipfile.ZipFile(output, "w") as z:
            for file in self.root.iterdir():
                z.write(file, "recording/" + file.name)
            if extra:
                z.writestr(extra, b"unsafe")
        return output

    def test_zip_round_trip_all_streams_aliases_and_events(self):
        result = convert_recording(self.make_zip(), self.output)
        self.assertEqual(result["source_npz_count"], 6)
        self.assertEqual(result["tactile_frames"], {"left": 4, "right": 4})
        with h5py.File(self.output) as f:
            for name, spec in self.manifest["streams"].items():
                start = 0
                for chunk in spec["chunks"]:
                    with np.load(self.root / chunk["file"], allow_pickle=False) as arrays:
                        stop = start + chunk["rows"]
                        for key in arrays.files:
                            ds = f[f"streams/{name}/{key}"]
                            actual = ds.asstr()[start:stop] if arrays[key].dtype.kind == "U" else ds[start:stop]
                            np.testing.assert_array_equal(actual, arrays[key])
                    start = stop
            self.assertEqual(f["trials/left/detail_xyz"].dtype, np.dtype("int32"))
            self.assertEqual(f["trials/left/detail_xyz"].id, f["streams/left_tactile/taxel_raw"].id)
            self.assertEqual(f["provenance/events_jsonl"].asstr()[()], self.events)
            self.assertEqual(f["provenance/manifest_json"].asstr()[()], (self.root / "manifest.json").read_text())
            self.assertEqual(f["events/temperature_readings/temperature_c"][0], 45.2)
            self.assertNotIn("temperature", f["trials/left"])
            self.assertNotIn("joint_radians", f["trials/left"])
        trial = load_hdf5(self.output, trial="left")
        self.assertFalse(trial.taxel_valid_mask.any())
        self.assertEqual(trial.hand_side.tolist(), ["left"] * 4)
        with self.assertRaisesRegex(ValueError, "allow_unverified"):
            analyze_trial(trial)
        raw = analyze_trial(trial, AnalysisConfig(allow_unverified=True))
        self.assertEqual(raw.summary["analysis_mode"], "unverified_raw_diagnostic")
        with self.assertRaisesRegex(ValueError, "raw"):
            analyze_trial(trial, AnalysisConfig(allow_unverified=True, force_unit="N"))
        with self.assertRaisesRegex(ValueError, "多个数据组"):
            load_hdf5(self.output)

    def test_single_hand_directory_and_empty_temperature_events(self):
        self.manifest["streams"].pop("right_tactile")
        left = self.manifest["streams"].pop("left_tactile")
        self.manifest["streams"]["tactile"] = left
        for file in self.root.glob("right_tactile_*.npz"):
            file.unlink()
        (self.root / "events.jsonl").write_text("")
        self.save_manifest()
        result = convert_recording(self.root, self.output)
        self.assertEqual(result["temperature_readings"], 0)
        self.assertEqual(load_hdf5(self.output).n_frames, 4)

    def test_checksum_failure_leaves_existing_output_untouched(self):
        self.output.write_bytes(b"existing output")
        (self.root / "left_tactile_00000.npz").write_bytes(b"corrupted")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            convert_recording(self.root, self.output, overwrite=True)
        self.assertEqual(self.output.read_bytes(), b"existing output")
        self.assertFalse(list(self.base.glob(".tactile-convert-*")))

    def test_existing_output_requires_explicit_overwrite(self):
        self.output.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            convert_recording(self.root, self.output)
        convert_recording(self.root, self.output, overwrite=True)
        self.assertEqual(load_hdf5(self.output, trial="right").n_frames, 4)

    def test_overlapping_chunk_times_rejected(self):
        spec = self.manifest["streams"]["left_tactile"]
        file = self.root / spec["chunks"][1]["file"]
        with np.load(file, allow_pickle=False) as data:
            arrays = {k: data[k] for k in data.files}
        arrays["timestamp_ns"] = np.array([20, 40], dtype=np.int64)
        arrays["query_begin_ns"] = np.array([19, 39], dtype=np.int64)
        np.savez_compressed(file, **arrays)
        spec["chunks"][1]["sha256"] = hashlib.sha256(file.read_bytes()).hexdigest()
        spec["chunks"][1]["first_timestamp_ns"] = 20
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "未严格递增"):
            convert_recording(self.root, self.output)
        self.assertFalse(self.output.exists())

    def test_inconsistent_validity_rejected(self):
        file = self.root / "left_tactile_00000.npz"
        with np.load(file, allow_pickle=False) as data:
            arrays = {k: data[k] for k in data.files}
        arrays["sample_valid"][:] = True
        np.savez_compressed(file, **arrays)
        self.manifest["streams"]["left_tactile"]["chunks"][0]["sha256"] = hashlib.sha256(file.read_bytes()).hexdigest()
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "sample_valid"):
            convert_recording(self.root, self.output)

    def test_path_traversal_and_unlisted_npz_rejected(self):
        with self.assertRaisesRegex(ValueError, "源文件路径不安全"):
            convert_recording(self.make_zip("../escape.npz"), self.output)
        np.savez(self.root / "unlisted.npz", x=np.zeros(1))
        with self.assertRaisesRegex(ValueError, "未列入 manifest"):
            convert_recording(self.root, self.output)

    def test_raw_npz_loader_preserves_validity(self):
        trial = load_npz(self.root / "left_tactile_00000.npz")
        self.assertEqual(trial.n_frames, 2)
        np.testing.assert_array_equal(trial.detail_xyz[:, 10], [[-128, 127, 255]] * 2)
        self.assertFalse(trial.sample_valid.any())
        with self.assertRaisesRegex(ValueError, "allow_unverified"):
            analyze_trial(trial)
