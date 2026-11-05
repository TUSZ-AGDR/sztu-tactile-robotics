"""Parent-grouped, causal windows and train-only standardization."""
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Standardizer:
    mean: np.ndarray
    scale: np.ndarray

    @classmethod
    def fit(cls, values):
        return cls(values.mean(axis=0), np.maximum(values.std(axis=0), 1e-4))

    def transform(self, values):
        return ((values - self.mean) / self.scale).astype(np.float32)

    def inverse(self, values):
        return values * self.scale + self.mean


def load_windows(path, window=7, max_gap_sec=.25):
    if window < 1:
        raise ValueError("window must be positive")
    with np.load(Path(path), allow_pickle=False) as source:
        data = {key: source[key] for key in source.files}
    if not np.isfinite(data["x"]).all() or not np.isfinite(data["y"]).all():
        raise ValueError("Missing observations must be explicitly filtered, not replaced with zero")
    if len(np.unique(data["source_kind"])) != 1:
        raise ValueError("Do not mix synthetic and measured targets in one experiment")
    for parent in np.unique(data["parent"]):
        if len(np.unique(data["split"][data["parent"] == parent])) != 1:
            raise ValueError(f"Parent leakage: {parent} occurs in multiple splits")
    train = data["split"] == "train"
    if not train.any():
        raise ValueError("No training frames")
    x_scaler = Standardizer.fit(data["x"][train])
    y_scaler = Standardizer.fit(data["y"][train])
    x = x_scaler.transform(data["x"])
    y = y_scaler.transform(data["y"])
    indices = []
    for seq in np.unique(data["sequence"]):
        selected = np.flatnonzero(data["sequence"] == seq)
        if len(np.unique(data["parent"][selected])) != 1 or len(np.unique(data["split"][selected])) != 1:
            raise ValueError("Sequence has inconsistent identity")
        t = data["time"][selected]
        if not np.all(np.diff(t) > 0):
            raise ValueError("Sequence times must be strictly increasing")
        for end in range(window - 1, len(selected)):
            rows = selected[end - window + 1:end + 1]
            if np.all(np.diff(data["time"][rows]) <= max_gap_sec):
                indices.append(rows)
    if not indices:
        raise ValueError("No valid windows")
    indices = np.asarray(indices)
    ends = indices[:, -1]
    result = dict(x=x[indices].reshape(len(indices), -1),
                  y=y[indices].reshape(len(indices), -1),
                  target=data["y"][ends], time=data["time"][ends],
                  split=data["split"][ends], sequence=data["sequence"][ends],
                  parent=data["parent"][ends], indices=indices,
                  source_kind=str(data["source_kind"][0]), feature_names=data["feature_names"],
                  x_scaler=x_scaler, y_scaler=y_scaler, window=window)
    for split in ("train", "validation", "test"):
        if not np.any(result["split"] == split):
            raise ValueError(f"No {split} windows")
    return result
