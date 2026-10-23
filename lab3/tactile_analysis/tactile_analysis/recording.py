"""Direct NPZ recording loading, without an intermediate HDF5 file."""

from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
from pathlib import Path

import numpy as np

from .convert_recording import _source, _relative_name, _check_cancel
from .io import TactileTrial, load_hdf5


@dataclass
class Recording:
    source: Path
    trials: dict[str, TactileTrial]
    temperatures: list[dict]
    verified_npz_count: int = 0


def load_recording(source, *, progress=None, cancelled=None):
    """Hash every manifest NPZ; decode and validate only the tactile streams."""
    source = Path(source).resolve()
    if source.suffix.lower() in (".h5", ".hdf5") and source.is_file():
        return _load_hdf5_recording(source, progress=progress, cancelled=cancelled)
    with _source(source) as (read, members):
        manifest = json.loads(read("manifest.json"))
        if manifest.get("schema_version") != 1:
            raise ValueError("不支持此采集格式的 schema_version")
        total = sum(len(s["chunks"]) for s in manifest["streams"].values())
        trials, seen = {}, set()
        for name, spec in manifest["streams"].items():
            is_tactile = name == "tactile" or name.endswith("_tactile")
            parts, previous = [], None
            for chunk in spec["chunks"]:
                _check_cancel(cancelled)
                file = _relative_name(chunk["file"])
                if file in seen:
                    raise ValueError(f"NPZ 被重复引用：{file}")
                raw = read(file)
                if hashlib.sha256(raw).hexdigest() != chunk["sha256"]:
                    raise ValueError(f"SHA-256 哈希校验不一致：{file}")
                seen.add(file)
                if is_tactile:
                    with np.load(BytesIO(raw), allow_pickle=False) as data:
                        arrays = {key: data[key] for key in data.files}
                    if set(arrays) != set(spec["fields"]):
                        raise ValueError(f"字段与 manifest 声明不一致：{file}")
                    for key, definition in spec["fields"].items():
                        a, declared = arrays[key], np.dtype(definition["dtype"])
                        if a.shape != (chunk["rows"], *definition["shape"]):
                            raise ValueError(f"数组形状与 manifest 声明不一致：{file}:{key}")
                        if a.dtype != declared and not a.dtype.kind == declared.kind == "U":
                            raise ValueError(f"数组类型与 manifest 声明不一致：{file}:{key}")
                    ts = arrays["timestamp_ns"]
                    if not len(ts) or ts.dtype != np.dtype("int64") or np.any(ts < 0):
                        raise ValueError(f"时间戳无效：{file}")
                    if np.any(np.diff(ts) <= 0) or (previous is not None and ts[0] <= previous):
                        raise ValueError(f"时间戳未严格递增：{file}")
                    if int(ts[0]) != chunk["first_timestamp_ns"] or int(ts[-1]) != chunk["last_timestamp_ns"]:
                        raise ValueError(f"时间戳与 manifest 声明不一致：{file}")
                    previous = ts[-1]
                    parts.append(arrays)
                if progress:
                    progress(len(seen), total, f"已校验 {file}")
            if not is_tactile:
                continue
            if not parts:
                raise ValueError(f"触觉数据流为空：{name}")
            data = {key: np.concatenate([a[key] for a in parts]) for key in parts[0]}
            frames = len(data["timestamp_ns"])
            from .convert_recording import _TACTILE_SCHEMA
            for key, (dtype, shape) in _TACTILE_SCHEMA.items():
                if key not in data or data[key].shape != (frames, *shape) or data[key].dtype != np.dtype(dtype):
                    raise ValueError(f"触觉字段无效：{name}:{key}")
            sides = set(data["hand_side"].tolist())
            if len(sides) != 1 or not sides <= {"left", "right"}:
                raise ValueError(f"hand_side 手别字段无效：{name}")
            side = sides.pop()
            if side in trials or name not in ("tactile", f"{side}_tactile"):
                raise ValueError(f"手别标识重复或不一致：{name}")
            if frames != spec["rows"]:
                raise ValueError(f"行数与 manifest 声明不一致：{name}")
            if np.any(data["taxel_valid_mask"] & ~data["packet_valid"][:, None]):
                raise ValueError("无效数据包中出现了已验证有效的触觉点")
            trials[side] = TactileTrial(
                detail_xyz=data["taxel_raw"], sensor_forces=data["sensor_summary_raw"],
                timestamps_ns=data["timestamp_ns"], taxel_valid_mask=data["taxel_valid_mask"],
                packet_valid=data["packet_valid"], sample_valid=data["sample_valid"],
                query_begin_ns=data["query_begin_ns"], hand_side=data["hand_side"],
                metadata={"hand_side": side, "force_unit": "raw", "source_stream": name,
                          "trajectory_id": manifest["trajectory_id"]})
        extra = {n for n in members if n.endswith(".npz")} - seen
        if extra:
            raise ValueError(f"存在未列入 manifest 的 NPZ 文件：{sorted(extra)}")
        if not trials:
            raise ValueError("未找到触觉数据流")
        events = [json.loads(line) for line in read(manifest["events_file"]).decode("utf-8").splitlines() if line.strip()]
        temperatures = []
        for event in events:
            if event.get("event") != "temperature_reading":
                continue
            for reading in event["readings"]:
                value = float(reading["temperature_c"])
                if not np.isfinite(value):
                    raise ValueError("温度不是有限数值")
                temperatures.append({"timestamp_ns": event["timestamp_ns"], "hand_side": event["hand_side"],
                                     **reading, "temperature_c": value})
    _check_cancel(cancelled)
    return Recording(source, dict(sorted(trials.items())), temperatures, len(seen))


def _load_hdf5_recording(source, *, progress=None, cancelled=None):
    import h5py

    with h5py.File(source, "r") as f:
        names = list(f["trials"]) if "trials" in f else [None]
        temperatures = []
        if "events/temperature_readings" in f:
            table = f["events/temperature_readings"]
            columns = {key: table[key].asstr()[:] if table[key].dtype.kind in ("O", "S", "U") else table[key][:]
                       for key in ("timestamp_ns", "hand_side", "sensor_id", "finger_name", "temperature_c")}
            for row in zip(*columns.values()):
                temperatures.append(dict(zip(columns, row)))
    trials = {}
    for index, name in enumerate(names):
        _check_cancel(cancelled)
        trial = load_hdf5(source, trial=name)
        trials[name or str(trial.metadata.get("hand_side", "trial"))] = trial
        if progress:
            progress(index + 1, len(names), f"已读取 {name or '根级触觉数组'}")
    return Recording(source, trials, temperatures)


def describe_recording(recording):
    rows = []
    for side, trial in recording.trials.items():
        if not trial.n_frames:
            raise ValueError(f"数据组为空：{side}")
        ts = trial.timestamps_ns
        duration = float((ts[-1] - ts[0]) / 1e9) if ts is not None else None
        quality = (trial.taxel_valid_mask, trial.packet_valid, trial.sample_valid)
        rows.append({"trial": side, "frames": trial.n_frames, "taxels": trial.n_taxels,
                     "duration_s": duration, "rate_hz": (trial.n_frames - 1) / duration if duration else None,
                     "packet_valid_fraction": float(trial.packet_valid.mean()) if trial.packet_valid is not None else None,
                     "sample_valid_fraction": float(trial.sample_valid.mean()) if trial.sample_valid is not None else None,
                     "verified_taxels": int(trial.taxel_valid_mask.any(axis=0).sum()) if trial.taxel_valid_mask is not None else None,
                     "unverified": any(v is not None and not np.all(v) for v in quality)})
    return rows
