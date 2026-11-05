"""Train direct MLP, two autoencoders, and a frozen-encoder latent translator."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import numpy as np
import torch

from .data import load_windows
from .models import Autoencoder, LatentTranslator, mlp
from .prepare import sha256


def fit(model, x, y, vx, vy, epochs=600, objective=None):
    """Full-batch Adam; restore best validation checkpoint, never select on test."""
    optimizer = torch.optim.Adam([p for p in model.parameters() if p.requires_grad], lr=.003)
    objective = objective or (lambda a, b: (model(a) - b).square().mean())
    best, best_epoch, state, history = float("inf"), 0, None, []
    for epoch in range(1, epochs + 1):
        model.train()
        optimizer.zero_grad()
        loss = objective(x, y)
        if not torch.isfinite(loss):
            raise RuntimeError("Nonfinite training loss")
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5.)
        optimizer.step()
        if epoch == 1 or epoch % 10 == 0 or epoch == epochs:
            model.eval()
            with torch.no_grad():
                validation = float(objective(vx, vy))
            history.append(dict(epoch=epoch, train=float(loss.detach()), validation=validation))
            if validation < best:
                best, best_epoch, state = validation, epoch, copy.deepcopy(model.state_dict())
    model.load_state_dict(state)
    model.eval()
    return dict(best_epoch=best_epoch, best_validation_loss=best, history=history)


def metrics(prediction, target):
    error = prediction - target
    return dict(mae=float(np.abs(error).mean()), rmse=float(np.sqrt((error**2).mean())),
                per_axis_mae=np.abs(error).mean(axis=0).tolist(),
                per_axis_rmse=np.sqrt((error**2).mean(axis=0)).tolist())


def run(data_path, out, epochs=600, window=7, sim_latent=8, sensor_latent=4, seed=7):
    if epochs < 1 or sim_latent < 1 or sensor_latent < 1:
        raise ValueError("epochs and latent dimensions must be positive")
    torch.set_num_threads(2)
    torch.manual_seed(seed)
    np.random.seed(seed)
    torch.use_deterministic_algorithms(True)
    data = load_windows(data_path, window=window)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    masks = {split: data["split"] == split for split in ("train", "validation", "test")}
    x, y = torch.from_numpy(data["x"]), torch.from_numpy(data["y"])
    xt, xv = x[masks["train"]], x[masks["validation"]]
    yt, yv = y[masks["train"]], y[masks["validation"]]
    direct = mlp(x.shape[1], 3)
    sim_ae = Autoencoder(x.shape[1], sim_latent)
    sensor_ae = Autoencoder(y.shape[1], sensor_latent)
    training = {}
    jobs = [("direct_mlp", direct, xt, yt[:, -3:], xv, yv[:, -3:]),
            ("sim_autoencoder", sim_ae, xt, xt, xv, xv),
            ("sensor_autoencoder", sensor_ae, yt, yt, yv, yv)]
    for name, model, a, b, va, vb in jobs:
        training[name] = fit(model, a, b, va, vb, epochs=epochs)
        print(name, "best validation epoch", training[name]["best_epoch"], flush=True)
    translator = LatentTranslator(sim_ae, sensor_ae, sim_latent, sensor_latent)
    with torch.no_grad():
        translator.sensor_latent_scale.copy_(sensor_ae.encoder(yt).std(dim=0, unbiased=False).clamp_min(.1))
    training["latent_translation"] = fit(translator, xt, yt, xv, yv, epochs=epochs,
                                          objective=translator.objective)
    print("latent_translation best validation epoch", training["latent_translation"]["best_epoch"], flush=True)
    scaler = data["y_scaler"]
    with torch.no_grad():
        predictions = {
            "direct_mlp": scaler.inverse(direct(x).numpy()),
            "latent_translation": scaler.inverse(translator(x).numpy()[:, -3:]),
            # Uses target at inference; reconstruction ceiling, NOT a cross-modal predictor.
            "sensor_ae_self_reconstruction": scaler.inverse(sensor_ae(y).numpy()[:, -3:]),
        }
        z_sensor = sensor_ae.encoder(y).numpy()
        z_mapped = translator.latent(x).numpy()
        z_sim = sim_ae.encoder(x).numpy()
        sim_reconstruction_mse = float((sim_ae(x[masks["test"]]) - x[masks["test"]]).square().mean())
    # Ridge penalty chosen solely on validation data.
    xa = np.column_stack([data["x"], np.ones(len(x))]).astype(np.float64)
    ridge_options = []
    for penalty in (.1, 1., 10., 100.):
        reg = np.eye(xa.shape[1]) * penalty
        reg[-1, -1] = 0
        weights = np.linalg.solve(xa[masks["train"]].T @ xa[masks["train"]] + reg,
                                  xa[masks["train"]].T @ data["y"][masks["train"], -3:])
        prediction = scaler.inverse(xa @ weights)
        score = metrics(prediction[masks["validation"]], data["target"][masks["validation"]])["rmse"]
        ridge_options.append((score, penalty, weights, prediction))
    _, ridge_penalty, ridge_weights, predictions["ridge"] = min(ridge_options, key=lambda item: item[0])
    predictions["train_mean"] = np.broadcast_to(data["target"][masks["train"]].mean(axis=0), data["target"].shape)
    predictions["zero"] = np.zeros_like(data["target"])
    test = masks["test"]
    active = test & (np.linalg.norm(data["target"], axis=1) > .2)
    report = dict(complete=True, seed=seed, epochs=epochs, window=window,
                  input_sha256=sha256(data_path), source_kind=data["source_kind"],
                  units="nominal N; synthetic model units or SDK conversion, not validated physical calibration",
                  sim_latent_dim=sim_latent, sensor_latent_dim=sensor_latent,
                  torch_version=str(torch.__version__), ridge_penalty=ridge_penalty,
                  splits={name: dict(windows=int(mask.sum()), parents=np.unique(data["parent"][mask]).tolist())
                          for name, mask in masks.items()},
                  test={name: metrics(pred[test], data["target"][test]) for name, pred in predictions.items()},
                  test_above_diagnostic_0p2N={name: metrics(pred[active], data["target"][active])
                                             for name, pred in predictions.items()} if active.any() else {},
                  self_reconstruction_uses_target=True, sim_ae_test_standardized_mse=sim_reconstruction_mse,
                  latent_train_std=z_sensor[masks["train"]].std(axis=0).tolist(), training=training,
                  limitations=["Five independent measured parent episodes; variants are not new measurements.",
                               "Synthetic scores assess the teaching generator, not real hardware accuracy.",
                               "Test has one parent; do not infer generalization across objects or sessions."])
    (out / "metrics.json").write_text(json.dumps(report, indent=2) + "\n")
    np.savez_compressed(out / "predictions.npz", target=data["target"], time=data["time"],
                        sequence=data["sequence"], split=data["split"], parent=data["parent"],
                        z_sensor=z_sensor, z_mapped=z_mapped, z_sim=z_sim, **predictions)
    torch.save(dict(direct_mlp=direct.state_dict(), sim_ae=sim_ae.state_dict(),
                    sensor_ae=sensor_ae.state_dict(), translator=translator.state_dict(),
                    config={key: report[key] for key in ("window", "sim_latent_dim", "sensor_latent_dim", "source_kind", "input_sha256")},
                    feature_names=data["feature_names"].tolist(),
                    x_mean=torch.tensor(data["x_scaler"].mean), x_scale=torch.tensor(data["x_scaler"].scale),
                    y_mean=torch.tensor(scaler.mean), y_scale=torch.tensor(scaler.scale),
                    ridge_weights=torch.tensor(ridge_weights)), out / "models.pt")
    plot_results(data, predictions, z_sensor, z_mapped, training, out)
    print(json.dumps({name: value["rmse"] for name, value in report["test"].items()}, indent=2), flush=True)
    return report


def plot_results(data, predictions, z_sensor, z_mapped, training, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    test = data["split"] == "test"
    selected = np.unique(data["sequence"][test])[0]
    mask = data["sequence"] == selected
    fig, axes = plt.subplots(3, 1, figsize=(10, 7), sharex=True, constrained_layout=True)
    for axis, ax in enumerate(axes):
        ax.plot(data["time"][mask], data["target"][mask, axis], color="black", label="Target")
        for name, label in [("direct_mlp", "Direct MLP"), ("latent_translation", "Latent translation"), ("ridge", "Ridge baseline")]:
            ax.plot(data["time"][mask], predictions[name][mask, axis], label=label, alpha=.85)
        ax.set_ylabel(f"{'xyz'[axis]} (nominal N)"); ax.grid(alpha=.2)
    axes[0].legend(ncol=2)
    axes[0].set_title(f"Held-out parent | {data['source_kind']}\n{selected}")
    axes[-1].set_xlabel("Synthetic sequence time (s)" if data["source_kind"] == "synthetic_sensor"
                        else "Trigger-relative time (s)")
    fig.savefig(out / "test_predictions.png", dpi=150); plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(10, 7), constrained_layout=True)
    for ax, (name, entry) in zip(axes.ravel(), training.items()):
        h = entry["history"]
        ax.plot([r["epoch"] for r in h], [r["train"] for r in h], label="Train")
        ax.plot([r["epoch"] for r in h], [r["validation"] for r in h], label="Validation")
        ax.axvline(entry["best_epoch"], color="gray", linestyle="--", label="Selected")
        ax.set_title(name); ax.set_xlabel("Epoch"); ax.set_ylabel("Standardized loss")
        ax.set_yscale("log"); ax.grid(alpha=.2); ax.legend(fontsize=8)
    fig.savefig(out / "learning_curves.png", dpi=140); plt.close(fig)

    train_z = z_sensor[data["split"] == "train"]
    center = train_z.mean(axis=0)
    _, _, vt = np.linalg.svd(train_z - center, full_matrices=False)
    basis = vt[:2].T
    # One common projection, fitted on training target latents only.
    target = (z_sensor[mask] - center) @ basis
    mapped = (z_mapped[mask] - center) @ basis
    if target.shape[1] == 1:
        target = np.column_stack([target, np.zeros(len(target))])
        mapped = np.column_stack([mapped, np.zeros(len(mapped))])
    fig, ax = plt.subplots(figsize=(7, 6), constrained_layout=True)
    color = np.linalg.norm(data["target"][mask], axis=1)
    scatter = ax.scatter(target[:, 0], target[:, 1], c=color, cmap="viridis", label="Sensor encoder (target)")
    ax.scatter(mapped[:, 0], mapped[:, 1], c=color, cmap="viridis", marker="x", label="Mapped simulation latent")
    for a, b in zip(target[::3], mapped[::3]):
        ax.plot([a[0], b[0]], [a[1], b[1]], color="gray", alpha=.3, lw=.8)
    fig.colorbar(scatter, ax=ax, label="Target force norm (nominal N)")
    ax.set(xlabel="Training PCA axis 1", ylabel="Training PCA axis 2",
           title=f"Shared sensor latent coordinates | {data['source_kind']}")
    ax.legend(fontsize=8); ax.grid(alpha=.2)
    fig.savefig(out / "latent_space.png", dpi=150); plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=600)
    parser.add_argument("--window", type=int, default=7)
    parser.add_argument("--sim-latent", type=int, default=8)
    parser.add_argument("--sensor-latent", type=int, default=4)
    parser.add_argument("--seed", type=int, default=7)
    a = parser.parse_args()
    run(a.data, a.out, a.epochs, a.window, a.sim_latent, a.sensor_latent, a.seed)


if __name__ == "__main__":
    main()
