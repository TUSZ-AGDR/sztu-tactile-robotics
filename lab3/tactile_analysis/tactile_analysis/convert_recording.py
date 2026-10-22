"""Lossless, validated conversion of a DexH13 recording ZIP/directory to HDF5."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
import zipfile
from typing import Callable

import numpy as np


class OperationCancelled(Exception):
    """Cooperative cancellation; temporary conversion output is removed."""


def _check_cancel(cancelled):
    if cancelled is not None and cancelled():
        raise OperationCancelled("Operation cancelled")


def _relative_name(name: str) -> str:
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError(f"Unsafe source path: {name!r}")
    return str(path)


@contextmanager
def _source(path: Path):
    """Read archive members directly; never extract untrusted archive paths."""
    if path.is_dir():
        root = path.resolve()

        def read(name):
            file = (root / _relative_name(name)).resolve()
            if not file.is_relative_to(root):
                raise ValueError("Source symlink escapes recording directory")
            return file.read_bytes()

        yield read, {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
    else:
        with zipfile.ZipFile(path) as archive:
            members = {}
            for info in archive.infolist():
                name = _relative_name(info.filename)
                if name in members:
                    raise ValueError(f"Duplicate ZIP member: {name}")
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError(f"ZIP symlink is not supported: {name}")
                if not info.is_dir():
                    members[name] = info
            manifests = [n for n in members if PurePosixPath(n).name == "manifest.json"]
            if len(manifests) != 1:
                raise ValueError("ZIP must contain exactly one manifest.json")
            prefix = str(PurePosixPath(manifests[0]).parent)
            prefix = "" if prefix == "." else prefix + "/"

            def read(name):
                return archive.read(members[prefix + _relative_name(name)])

            yield read, {n[len(prefix):] for n in members if n.startswith(prefix)}


def _h5py():
    try:
        import h5py
    except ImportError as exc:
        raise ImportError("Install numpy and h5py: python -m pip install numpy h5py") from exc
    return h5py


def _append(group, name, values, start, h5py):
    if values.dtype.kind == "O":
        raise ValueError(f"Object arrays are not supported: {name}")
    if name not in group:
        dtype = h5py.string_dtype("utf-8") if values.dtype.kind == "U" else values.dtype
        group.create_dataset(name, shape=(0, *values.shape[1:]),
                             maxshape=(None, *values.shape[1:]), dtype=dtype,
                             compression="gzip", compression_opts=4,
                             shuffle=values.dtype.kind != "U")
    dataset = group[name]
    stop = start + len(values)
    dataset.resize(stop, axis=0)
    dataset[start:stop] = values.astype(object) if values.dtype.kind == "U" else values
    # Read back every field/chunk, including signed integers, validity and strings.
    back = dataset.asstr()[start:stop] if values.dtype.kind == "U" else dataset[start:stop]
    equal = np.array_equal(back, values, equal_nan=True) if values.dtype.kind in "fc" else np.array_equal(back, values)
    if not equal or (values.dtype.kind != "U" and dataset.dtype != values.dtype):
        raise ValueError(f"HDF5 read-back mismatch: {group.name}/{name}")


_TACTILE_SCHEMA = {
    "timestamp_ns": ("int64", ()), "query_begin_ns": ("int64", ()),
    "taxel_raw": ("int32", (1140, 3)), "sensor_summary_raw": ("int32", (11, 3)),
    "taxel_valid_mask": ("bool", (1140,)), "packet_valid": ("bool", ()),
    "sample_valid": ("bool", ()),
}


def _validate_tactile(group):
    frames = len(group["timestamp_ns"])
    for key, (dtype, shape) in _TACTILE_SCHEMA.items():
        if key not in group or group[key].shape != (frames, *shape) or group[key].dtype != np.dtype(dtype):
            raise ValueError(f"Invalid tactile dataset: {group.name}/{key}")
    if "hand_side" not in group or group["hand_side"].shape != (frames,):
        raise ValueError("Missing per-frame hand_side")
    sides = set(group["hand_side"].asstr()[:].tolist())
    if len(sides) != 1 or not sides <= {"left", "right"}:
        raise ValueError(f"Tactile stream must contain exactly one hand: {sides}")
    side = sides.pop()
    if group.name.rsplit("/", 1)[-1] not in ("tactile", f"{side}_tactile"):
        raise ValueError("Stream name disagrees with hand_side")
    for start in range(0, frames, 256):
        sl = slice(start, start + 256)
        ts, begin = group["timestamp_ns"][sl], group["query_begin_ns"][sl]
        if np.any(begin < 0) or np.any(begin > ts):
            raise ValueError("Invalid tactile query interval")
        mask, packet = group["taxel_valid_mask"][sl], group["packet_valid"][sl]
        if np.any(mask & ~packet[:, None]):
            raise ValueError("Verified taxel in invalid packet")
        if not np.array_equal(group["sample_valid"][sl], packet & mask.any(axis=1)):
            raise ValueError("sample_valid disagrees with packet_valid and taxel_valid_mask")
    return side, frames


def _write_temperatures(handle, text, h5py):
    columns = {k: [] for k in ("timestamp_ns", "hand_side", "finger_name", "sensor_id",
                               "temperature_c", "event_line_1based", "reading_index")}
    event_count = 0
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("event") != "temperature_reading":
            continue
        event_count += 1
        side, timestamp = event["hand_side"], event["timestamp_ns"]
        if side not in ("left", "right") or type(timestamp) is not int or timestamp < 0:
            raise ValueError(f"Invalid temperature event on line {line_number}")
        for i, reading in enumerate(event["readings"]):
            if type(reading["sensor_id"]) is not int or not isinstance(reading["finger_name"], str):
                raise ValueError(f"Invalid temperature identity on line {line_number}")
            temperature = float(reading["temperature_c"])
            if not np.isfinite(temperature):
                raise ValueError(f"Nonfinite temperature on line {line_number}")
            values = (timestamp, side, reading["finger_name"], reading["sensor_id"],
                      temperature, line_number, i)
            for key, value in zip(columns, values):
                columns[key].append(value)
    group = handle.require_group("events/temperature_readings")
    group.attrs["time_contract"] = "Original event timestamps and file order; not resampled to tactile frames"
    for key, values in columns.items():
        dtype = "U" if key in ("hand_side", "finger_name") else "float64" if key == "temperature_c" else "int64"
        _append(group, key, np.asarray(values, dtype=dtype), 0, h5py)
    return event_count, len(columns["timestamp_ns"])


def convert_recording(source: str | Path, output: str | Path, *, overwrite: bool = False,
                      progress: Callable[[int, int, str], None] | None = None,
                      cancelled: Callable[[], bool] | None = None) -> dict:
    """Convert all manifest-listed streams, preserving independent time axes.

    Each hand is an analysis trial with hard links to its raw tactile stream.
    Missing verification is preserved, never inferred from nonzero readings.
    Writes to a temporary file and publishes only after successful validation.
    """
    h5py = _h5py()
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output:
        raise ValueError("Output must differ from source")
    if output.exists() and not overwrite:
        raise FileExistsError(f"Output exists; use --overwrite to replace it: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".tactile-convert-", suffix=".h5", dir=output.parent)
    os.close(descriptor)
    report = {"source": str(source), "output": str(output), "chunks": [],
              "verified_field_arrays": 0, "tactile_frames": {}, "source_archive_sha256": None}
    try:
        if source.is_file():
            digest = hashlib.sha256()
            with source.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    _check_cancel(cancelled)
                    digest.update(block)
            report["source_archive_sha256"] = digest.hexdigest()
        with _source(source) as (read, members), h5py.File(temporary, "w") as handle:
            manifest_bytes = read("manifest.json")
            manifest = json.loads(manifest_bytes)
            if manifest.get("schema_version") != 1:
                raise ValueError("Unsupported recording schema_version (expected 1)")
            total_chunks = sum(len(s["chunks"]) for s in manifest["streams"].values())
            if progress:
                progress(0, total_chunks, "读取 manifest，准备逐块校验")
            handle.attrs["conversion_schema"] = "dexh13-recording-hdf5-v1"
            handle.attrs["trajectory_id"] = manifest["trajectory_id"]
            handle.attrs["force_unit"] = "raw"
            handle.attrs["synchronization"] = "Independent host monotonic time axes; no resampling"
            provenance = handle.create_group("provenance")
            provenance.create_dataset("manifest_json", data=manifest_bytes.decode("utf-8"), dtype=h5py.string_dtype())
            provenance.attrs["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
            events_bytes = read(manifest["events_file"])
            events_text = events_bytes.decode("utf-8")
            provenance.create_dataset("events_jsonl", data=events_text, dtype=h5py.string_dtype())
            provenance.attrs["events_sha256"] = hashlib.sha256(events_bytes).hexdigest()
            provenance.attrs["events_hash_verification"] = "Computed on input; manifest provides no independent events hash"
            seen = set()
            for name, spec in manifest["streams"].items():
                if _relative_name(name) != name or "/" in name or name == ".":
                    raise ValueError(f"Invalid stream name: {name}")
                group = handle.require_group(f"streams/{name}")
                offset, previous = 0, None
                for chunk in spec["chunks"]:
                    _check_cancel(cancelled)
                    file = _relative_name(chunk["file"])
                    if file in seen:
                        raise ValueError(f"NPZ referenced more than once: {file}")
                    seen.add(file)
                    raw = read(file)
                    digest = hashlib.sha256(raw).hexdigest()
                    if digest != chunk["sha256"]:
                        raise ValueError(f"SHA-256 mismatch: {file}")
                    with np.load(BytesIO(raw), allow_pickle=False) as data:
                        if set(data.files) != set(spec["fields"]):
                            raise ValueError(f"Manifest field mismatch: {file}")
                        rows = chunk["rows"]
                        if type(rows) is not int or rows <= 0:
                            raise ValueError(f"Invalid chunk rows: {file}")
                        ts = data["timestamp_ns"]
                        if ts.dtype != np.dtype("int64") or ts.shape != (rows,) or np.any(ts < 0):
                            raise ValueError(f"Invalid timestamp array: {file}")
                        if np.any(np.diff(ts) <= 0) or (previous is not None and ts[0] <= previous):
                            raise ValueError(f"Non-increasing timestamps (including chunk boundary): {file}")
                        if int(ts[0]) != chunk["first_timestamp_ns"] or int(ts[-1]) != chunk["last_timestamp_ns"]:
                            raise ValueError(f"Manifest timestamp mismatch: {file}")
                        previous = int(ts[-1])
                        for key, definition in spec["fields"].items():
                            if "/" in key or key in ("", ".", ".."):
                                raise ValueError(f"Invalid field name: {key}")
                            values = data[key]
                            declared = np.dtype(definition["dtype"])
                            if values.shape != (rows, *definition["shape"]):
                                raise ValueError(f"Manifest shape mismatch: {file}:{key}")
                            if values.dtype != declared and not values.dtype.kind == declared.kind == "U":
                                raise ValueError(f"Manifest dtype mismatch: {file}:{key}")
                            _append(group, key, values, offset, h5py)
                            report["verified_field_arrays"] += 1
                        report["chunks"].append({"file": file, "stream": name, "sha256": digest,
                                                 "row_start": offset, "row_stop": offset + rows})
                        offset += rows
                    if progress:
                        progress(len(report["chunks"]), total_chunks, f"已校验并写入 {file}")
                if offset != spec["rows"]:
                    raise ValueError(f"Manifest total row mismatch: {name}")
                group.attrs["rows"] = offset
                if name == "tactile" or name.endswith("_tactile"):
                    side, frames = _validate_tactile(group)
                    trials = handle.require_group("trials")
                    if side in trials:
                        raise ValueError(f"Multiple tactile streams for {side}")
                    trial = trials.create_group(side)
                    for key in group:
                        trial[key] = group[key]
                    for alias, key in (("detail_xyz", "taxel_raw"), ("sensor_forces", "sensor_summary_raw"),
                                       ("tactile_timestamps_ns", "timestamp_ns")):
                        trial[alias] = group[key]
                    trial.attrs["hand_side"] = side
                    trial.attrs["force_unit"] = "raw"
                    trial.attrs["calibration_status"] = "Not applied; see source manifest"
                    trial.attrs["taxel_order"] = manifest.get("metadata", {}).get("taxel_order", "SDK order; unverified")
                    trial.attrs["source_stream"] = group.name
                    trial.attrs["temperature_events"] = "/events/temperature_readings"
                    trial.attrs["alignment"] = "No per-frame temperature or joint alignment performed"
                    report["tactile_frames"][side] = frames
            if not report["tactile_frames"]:
                raise ValueError("No tactile stream found")
            extra = {n for n in members if n.endswith(".npz")} - seen
            if extra:
                raise ValueError(f"Unlisted NPZ files would be omitted: {sorted(extra)}")
            report["source_npz_count"] = len(seen)
            _check_cancel(cancelled)
            report["temperature_events"], report["temperature_readings"] = _write_temperatures(handle, events_text, h5py)
            provenance.create_dataset("conversion_report_json", data=json.dumps(report, ensure_ascii=False, indent=2),
                                      dtype=h5py.string_dtype())
            handle.flush()
        _check_cancel(cancelled)
        if overwrite:
            os.replace(temporary, output)
        else:
            # Atomic publication that cannot silently replace a concurrently created output.
            os.link(temporary, output)
            os.unlink(temporary)
        return report
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Recording ZIP or directory containing manifest.json")
    parser.add_argument("output", type=Path, help="Output HDF5 file")
    parser.add_argument("--overwrite", action="store_true", help="Replace output only after successful conversion")
    args = parser.parse_args(argv)
    try:
        result = convert_recording(args.source, args.output, overwrite=args.overwrite)
    except (ValueError, KeyError, OSError, ImportError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Conversion failed: {exc}\n")
    print(json.dumps({key: value for key, value in result.items() if key != "chunks"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
