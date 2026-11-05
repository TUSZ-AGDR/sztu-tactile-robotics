"""Check distributed data hashes, parent splits, timestamps and model meshes."""
import argparse
import json
from pathlib import Path

import numpy as np

from .data import load_windows
from .prepare import sha256


def verify(data_dir, assets):
    data_dir, assets = Path(data_dir), Path(assets)
    checksums = json.loads((data_dir / "checksums.json").read_text())
    for name, digest in checksums.items():
        if sha256(data_dir / name) != digest:
            raise ValueError(f"Dataset hash mismatch: {name}")
    manifest = json.loads((data_dir / "manifest.json").read_text())
    if not manifest["complete"]:
        raise ValueError("Dataset generation did not finish")
    inventory = json.loads((assets / "provenance.json").read_text())
    for name, record in inventory["meshes"].items():
        if sha256(assets / "meshes" / name) != record["sha256"]:
            raise ValueError(f"Mesh hash mismatch: {name}")
    for entry in manifest["sources"]:
        folder = assets / "episodes" / entry["parent"]
        files = {"recording.npz": folder / "recording.npz", "recording.json": folder / "recording.json",
                 "model_manifest.json": folder / "model_manifest.json",
                 "model.xml": folder / json.loads((folder / "recording.json").read_text())["model_path"]}
        for name, digest in entry["sha256"].items():
            if sha256(files[name]) != digest:
                raise ValueError(f"Source hash mismatch: {entry['parent']}/{name}")
    report = {"passed": True, "mesh_count": len(inventory["meshes"]), "datasets": {}}
    for domain in ("measured", "synthetic"):
        path = data_dir / f"{domain}.npz"
        data = load_windows(path)
        with np.load(path, allow_pickle=False) as raw:
            expected = manifest[f"{domain}_packets"]
            if len(raw["time"]) != expected:
                raise ValueError("Packet count differs from manifest")
            for seq in np.unique(raw["sequence"]):
                mask = raw["sequence"] == seq
                parent = str(raw["parent"][mask][0])
                with np.load(assets / "episodes" / parent / "recording.npz", allow_pickle=False) as original:
                    np.testing.assert_array_equal(raw["source_time"][mask], original["time"])
                    if domain == "measured":
                        np.testing.assert_array_equal(raw["time"][mask], original["time"])
                        np.testing.assert_allclose(raw["y"][mask], original["measured_sdk_N"], atol=1e-7, rtol=1e-6)
                    else:
                        meta = next(v for v in manifest["synthetic_sequences"] if v["sequence"] == seq)
                        wanted = original["time"][0] + (original["time"] - original["time"][0]) / meta["replay_speed_factor"]
                        np.testing.assert_allclose(raw["time"][mask], wanted, atol=1e-12, rtol=0)
                dt = np.r_[0., np.diff(raw["time"][mask])]
                np.testing.assert_allclose(raw["x"][mask, -1], dt, atol=1e-7, rtol=0)
            report["datasets"][domain] = dict(frames=len(raw["time"]), sequences=len(np.unique(raw["sequence"])),
                windows={split: int((data["split"] == split).sum()) for split in ("train", "validation", "test")})
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, default=Path("lab4/datasets"))
    p.add_argument("--assets", type=Path, default=Path("lab4/replay_assets"))
    a = p.parse_args()
    verify(a.data, a.assets)
