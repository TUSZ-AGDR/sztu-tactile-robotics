from dataclasses import dataclass
from dataclasses import asdict
from pathlib import Path
import csv
import json
import numpy as np


@dataclass
class ExperimentResult:
    controller: str
    config: object
    metrics: dict
    trace: dict
    output_dir: Path | None = None

    def save(self, directory):
        directory = Path(directory).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        self.output_dir = directory
        summary = {"controller": self.controller, "config": asdict(self.config),
                   "metrics": self.metrics, "force_definition": "sum of target-object tactile contact normal forces (N)",
                   "collision_model": "planar teaching pads; original hand meshes are visual"}
        (directory / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        np.savez_compressed(directory / "episode.npz", **self.trace)
        scalar_keys = [key for key, value in self.trace.items() if value.ndim == 1]
        with (directory / "trace.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(scalar_keys)
            for row in zip(*(self.trace[key] for key in scalar_keys)):
                writer.writerow(row)
        return directory

    def describe(self):
        metrics = self.metrics
        state = "PASS" if metrics["success"] else "FAIL"
        reasons = ", ".join(metrics["reasons"]) or "none"
        return (f"{self.controller}: {state} | held={metrics['held_time_s']:.3f}s "
                f"peak={metrics['peak_force_N']:.3f}N "
                f"over-limit={metrics['overforce_time_s']:.3f}s | reasons={reasons}")


def save_comparison(results, directory):
    from .viewer import plot_comparison
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    rows = [{"controller": r.controller, **r.metrics} for r in results]
    (directory / "comparison.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    with (directory / "comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    plot_comparison(results, directory / "comparison.png")
