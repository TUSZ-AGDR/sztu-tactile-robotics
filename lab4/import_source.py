"""Teacher utility: compact five replay packages and deduplicate model meshes."""
import argparse
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

import numpy as np

from .prepare import SavedReplay, sha256


def compact_source(source, out):
    source, out = Path(source), Path(out)
    folders = sorted(source.glob("Joint_*/paired.h5"))
    if len(folders) != 5:
        raise ValueError("Expected five Joint replay packages")
    out.mkdir(parents=True, exist_ok=False)
    (out / "models").mkdir()
    (out / "meshes").mkdir()
    inventory = dict(schema_version=1, format="packet-sampled saved simulation states", sources=[], meshes={})
    for paired in folders:
        folder = paired.parent
        replay = SavedReplay(folder)
        target = out / "episodes" / folder.name
        target.mkdir(parents=True)
        np.savez_compressed(target / "recording.npz", time=replay.time, q_actual=replay.q,
                            measured_sdk_N=replay.measured, native_module_force_N=replay.native_force,
                            raw_event_index=replay.raw_indices, sim_frame_index=replay.indices,
                            joint_names=np.array(replay.joint_names))
        tree = ET.parse(folder / "model/model.xml")
        root = tree.getroot()
        compiler = root.find("compiler")
        meshdir, texturedir = compiler.get("meshdir", "."), compiler.get("texturedir", ".")
        for asset in root.findall("asset/*"):
            file = asset.get("file")
            if not file:
                continue
            original = folder / "model" / (meshdir if asset.tag == "mesh" else texturedir) / file
            digest = sha256(original)
            name = digest + original.suffix.lower()
            destination = out / "meshes" / name
            if not destination.exists():
                shutil.copy2(original, destination)
            inventory["meshes"][name] = {"sha256": digest, "original_asset_name": file}
            asset.set("file", f"../meshes/{name}")
        compiler.set("meshdir", ".")
        compiler.set("texturedir", ".")
        tree.write(out / "models" / f"{folder.name}.xml", encoding="utf-8", xml_declaration=True)
        original_manifest = json.loads((folder / "model/model_manifest.json").read_text())
        compact_manifest = {key: original_manifest[key] for key in ("modules", "object_alignment")}
        (target / "model_manifest.json").write_text(json.dumps(compact_manifest, indent=2) + "\n")
        metadata = dict(parent=folder.name, model_path=f"../../models/{folder.name}.xml",
                        measured_module_id=3, coordinate_change="none; only asset paths rewritten",
                        source_sha256={name: sha256(folder / name) for name in
                                       ("paired.h5", "simulation/simulation.h5", "model/model.xml", "model/model_manifest.json")})
        (target / "recording.json").write_text(json.dumps(metadata, indent=2) + "\n")
        # Independently load rewritten XML and compare geometry and measured labels.
        compact = SavedReplay(target)
        np.testing.assert_array_equal(compact.measured, replay.measured)
        np.testing.assert_array_equal(compact.q, replay.q)
        np.testing.assert_allclose(compact.geometry()[0], replay.geometry()[0], atol=1e-9, rtol=0)
        inventory["sources"].append(dict(parent=folder.name, packets=len(replay.time),
                                          source_sha256=metadata["source_sha256"]))
        print("Verified compact replay:", folder.name, flush=True)
    (out / "provenance.json").write_text(json.dumps(inventory, indent=2) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("lab4/replay_assets"))
    a = p.parse_args()
    compact_source(a.source, a.out)
