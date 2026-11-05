"""Inference from simulation features only; never reads sensor labels."""
import argparse
from pathlib import Path

import numpy as np
import torch

from .models import Autoencoder, LatentTranslator, mlp


def predict(model_path, features_path, out):
    out = Path(out)
    if out.exists():
        raise FileExistsError(out)
    torch.set_num_threads(2)
    checkpoint = torch.load(model_path, map_location="cpu", weights_only=True)
    config = checkpoint["config"]
    window = config["window"]
    with np.load(features_path, allow_pickle=False) as source:
        # Only these inputs are read, even if the file also contains labels.
        features, sequences, times = source["x"], source["sequence"], source["time"]
        names = source["feature_names"].tolist()
    if names != checkpoint["feature_names"]:
        raise ValueError("Simulation feature order differs from trained model")
    if not np.isfinite(features).all():
        raise ValueError("Nonfinite simulation input")
    mean, scale = checkpoint["x_mean"].numpy(), checkpoint["x_scale"].numpy()
    normalized = (features - mean) / scale
    rows = []
    for seq in np.unique(sequences):
        indices = np.flatnonzero(sequences == seq)
        if not np.all(np.diff(times[indices]) > 0):
            raise ValueError("Nonmonotonic sequence")
        for end in range(window - 1, len(indices)):
            idx = indices[end - window + 1:end + 1]
            if np.all(np.diff(times[idx]) <= .25):
                rows.append(idx)
    if not rows:
        raise ValueError("No valid windows")
    rows = np.asarray(rows)
    x = torch.tensor(normalized[rows].reshape(len(rows), -1), dtype=torch.float32)
    direct = mlp(x.shape[1], 3)
    direct.load_state_dict(checkpoint["direct_mlp"])
    sim_ae = Autoencoder(x.shape[1], config["sim_latent_dim"])
    sensor_ae = Autoencoder(window * 3, config["sensor_latent_dim"])
    translator = LatentTranslator(sim_ae, sensor_ae, config["sim_latent_dim"], config["sensor_latent_dim"])
    translator.load_state_dict(checkpoint["translator"])
    direct.eval(); translator.eval()
    with torch.no_grad():
        y_mean, y_scale = checkpoint["y_mean"], checkpoint["y_scale"]
        direct_prediction = (direct(x) * y_scale + y_mean).numpy()
        mapped_prediction = (translator(x)[:, -3:] * y_scale + y_mean).numpy()
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, time=times[rows[:, -1]], sequence=sequences[rows[:, -1]],
                        direct_mlp=direct_prediction, latent_translation=mapped_prediction,
                        training_source_kind=np.array(config["source_kind"]),
                        inference_uses_sensor_labels=np.array(False))
    return direct_prediction, mapped_prediction


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--features", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    predict(a.model, a.features, a.out)
    print(a.out)
