from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import yaml

from dexh13sim.calibration_fitting import (
    CalibrationSampleSet,
    apply_fit_to_calibration,
    evaluate_rbf_fit,
    fit_rbf_parameters,
    load_calibration_samples_csv,
    load_calibration_samples,
    write_calibration_samples,
)
from dexh13sim.runtime import load_templates
from dexh13sim.sensor_table import SENSOR_TABLE, SensorSpec, total_taxels
from dexh13sim.tactile_renderer import TactileRenderer


class ToyTemplate:
    xyz_m = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [0.002, 0.0, 0.0],
            [0.004, 0.0, 0.0],
        ],
        dtype=np.float64,
    )
    normals = np.tile(np.asarray([0.0, 0.0, 1.0], dtype=np.float64), (3, 1))


def test_calibration_samples_round_trip_hdf5(tmp_path: Path):
    samples = CalibrationSampleSet(
        sensor_id=np.asarray([0, 1], dtype=np.int32),
        p_sensor=np.asarray([[0.0, 0.0, 0.0], [0.001, 0.0, 0.0]], dtype=np.float32),
        f_sensor=np.asarray([[0.0, 0.0, 1.0], [0.1, 0.0, 2.0]], dtype=np.float32),
        observed_detail_N=np.ones((2, 3, 3), dtype=np.float32),
        metadata={"source": "synthetic_press"},
    )
    out = tmp_path / "calibration_samples.h5"

    write_calibration_samples(out, samples)
    loaded = load_calibration_samples(out)

    assert np.array_equal(loaded.sensor_id, samples.sensor_id)
    assert np.allclose(loaded.p_sensor, samples.p_sensor)
    assert np.allclose(loaded.f_sensor, samples.f_sensor)
    assert np.allclose(loaded.observed_detail_N, samples.observed_detail_N)
    assert loaded.metadata["source"] == "synthetic_press"


def test_fit_rbf_parameters_recovers_synthetic_template_sigma():
    specs = [SensorSpec(0, "sensor1", "toy_sensor", "toy", 3, 0, 3)]
    templates = {"toy": ToyTemplate()}
    true_config = {
        "toy": {
            "sigma_t0": 0.001,
            "sigma_n0": 0.0015,
            "outside_reject_dist": 0.02,
            "max_abs_normal_offset": 0.006,
            "min_raw_weight": 1.0e-8,
        }
    }
    renderer = TactileRenderer(specs, templates, true_config, total_taxels=3)
    contacts = [
        {"sensor_id": 0, "p_sensor": np.asarray([0.0, 0.0, 0.0]), "f_sensor": np.asarray([0.0, 0.0, 1.0])},
        {"sensor_id": 0, "p_sensor": np.asarray([0.003, 0.0, 0.0]), "f_sensor": np.asarray([0.0, 0.0, 2.0])},
    ]
    observed = np.stack([renderer.render([contact]) for contact in contacts]).astype(np.float32)
    samples = CalibrationSampleSet(
        sensor_id=np.asarray([0, 0], dtype=np.int32),
        p_sensor=np.stack([contact["p_sensor"] for contact in contacts]).astype(np.float32),
        f_sensor=np.stack([contact["f_sensor"] for contact in contacts]).astype(np.float32),
        observed_detail_N=observed,
    )
    base_config = {
        "toy": {
            "sigma_t0": 0.004,
            "sigma_n0": 0.003,
            "outside_reject_dist": 0.02,
            "max_abs_normal_offset": 0.006,
            "min_raw_weight": 1.0e-8,
        }
    }

    fits = fit_rbf_parameters(
        samples,
        specs,
        templates,
        base_config,
        candidate_sigma_t=[0.001, 0.004],
        candidate_sigma_n=[0.0015, 0.003],
    )

    assert fits["toy"].sigma_t0 == 0.001
    assert fits["toy"].sigma_n0 == 0.0015
    assert fits["toy"].samples == 2
    updated = apply_fit_to_calibration({"templates": base_config}, fits)
    assert updated["templates"]["toy"]["sigma_t0"] == 0.001
    assert updated["templates"]["toy"]["sigma_n0"] == 0.0015


def test_fit_rbf_parameters_can_fit_template_response_matrix_and_bias():
    specs = [SensorSpec(0, "sensor1", "toy_sensor", "toy", 3, 0, 3)]
    templates = {"toy": ToyTemplate()}
    true_config = {
        "toy": {
            "sigma_t0": 0.001,
            "sigma_n0": 0.0015,
            "outside_reject_dist": 0.02,
            "max_abs_normal_offset": 0.006,
            "min_raw_weight": 1.0e-8,
        }
    }
    renderer = TactileRenderer(specs, templates, true_config, total_taxels=3)
    response_matrix = np.asarray(
        [
            [2.0, 0.2, 0.0],
            [0.0, -1.5, 0.1],
            [0.3, 0.0, 4.0],
        ],
        dtype=np.float64,
    )
    bias_N = np.asarray([0.01, -0.02, 0.03], dtype=np.float64)
    contacts = [
        {"sensor_id": 0, "p_sensor": np.asarray([0.0, 0.0, 0.0]), "f_sensor": np.asarray([1.0, 0.0, 0.0])},
        {"sensor_id": 0, "p_sensor": np.asarray([0.001, 0.0, 0.0]), "f_sensor": np.asarray([0.0, 1.0, 0.0])},
        {"sensor_id": 0, "p_sensor": np.asarray([0.002, 0.0, 0.0]), "f_sensor": np.asarray([0.0, 0.0, 1.0])},
        {"sensor_id": 0, "p_sensor": np.asarray([0.003, 0.0, 0.0]), "f_sensor": np.asarray([1.0, 2.0, 3.0])},
        {"sensor_id": 0, "p_sensor": np.asarray([0.004, 0.0, 0.0]), "f_sensor": np.asarray([-0.5, 0.25, 1.5])},
    ]
    raw_frames = [renderer.render([contact]) for contact in contacts]
    observed = np.stack([_apply_response(raw, specs[0], response_matrix, bias_N) for raw in raw_frames]).astype(np.float32)
    samples = CalibrationSampleSet(
        sensor_id=np.zeros(len(contacts), dtype=np.int32),
        p_sensor=np.stack([contact["p_sensor"] for contact in contacts]).astype(np.float32),
        f_sensor=np.stack([contact["f_sensor"] for contact in contacts]).astype(np.float32),
        observed_detail_N=observed,
    )

    fits = fit_rbf_parameters(
        samples,
        specs,
        templates,
        true_config,
        candidate_sigma_t=[0.001, 0.004],
        candidate_sigma_n=[0.0015, 0.003],
        fit_response=True,
        response_regularization=0.0,
    )

    assert fits["toy"].sigma_t0 == 0.001
    assert fits["toy"].sigma_n0 == 0.0015
    assert np.allclose(fits["toy"].A_matrix, response_matrix, atol=1.0e-5)
    assert np.allclose(fits["toy"].bias_N, bias_N, atol=1.0e-5)
    updated = apply_fit_to_calibration({"templates": true_config}, fits)
    assert np.allclose(updated["templates"]["toy"]["A_matrix"], response_matrix, atol=1.0e-5)
    assert np.allclose(updated["templates"]["toy"]["bias_N"], bias_N, atol=1.0e-5)


def test_fit_rbf_parameters_can_fit_only_z_axis_and_preserve_other_response_rows():
    specs = [SensorSpec(0, "sensor1", "toy_sensor", "toy", 3, 0, 3)]
    templates = {"toy": ToyTemplate()}
    true_config = {
        "toy": {
            "sigma_t0": 0.001,
            "sigma_n0": 0.0015,
            "outside_reject_dist": 0.02,
            "max_abs_normal_offset": 0.006,
            "min_raw_weight": 1.0e-8,
        }
    }
    renderer = TactileRenderer(specs, templates, true_config, total_taxels=3)
    contacts = [
        {"sensor_id": 0, "p_sensor": np.asarray([0.0, 0.0, 0.0]), "f_sensor": np.asarray([0.0, 0.0, 1.0])},
        {"sensor_id": 0, "p_sensor": np.asarray([0.002, 0.0, 0.0]), "f_sensor": np.asarray([0.0, 0.0, 2.0])},
        {"sensor_id": 0, "p_sensor": np.asarray([0.004, 0.0, 0.0]), "f_sensor": np.asarray([0.0, 0.0, 3.0])},
    ]
    observed = np.stack([renderer.render([contact]) for contact in contacts]).astype(np.float32)
    observed[:, :, 0] = 99.0
    observed[:, :, 1] = -77.0
    samples = CalibrationSampleSet(
        sensor_id=np.zeros(len(contacts), dtype=np.int32),
        p_sensor=np.stack([contact["p_sensor"] for contact in contacts]).astype(np.float32),
        f_sensor=np.stack([contact["f_sensor"] for contact in contacts]).astype(np.float32),
        observed_detail_N=observed,
    )
    base_matrix = np.asarray([[1.2, 0.1, 0.2], [0.3, 1.4, 0.5], [0.0, 0.0, 0.25]], dtype=np.float64)
    base_bias = np.asarray([0.4, -0.2, 0.0], dtype=np.float64)
    base_config = {
        "toy": {
            **true_config["toy"],
            "A_matrix": base_matrix.tolist(),
            "bias_N": base_bias.tolist(),
        }
    }

    fits = fit_rbf_parameters(
        samples,
        specs,
        templates,
        base_config,
        candidate_sigma_t=[0.001],
        candidate_sigma_n=[0.0015],
        fit_response=True,
        fit_axes=(2,),
        response_regularization=0.0,
    )

    fitted_matrix = np.asarray(fits["toy"].A_matrix)
    fitted_bias = np.asarray(fits["toy"].bias_N)
    assert np.allclose(fitted_matrix[:2], base_matrix[:2])
    assert np.allclose(fitted_bias[:2], base_bias[:2])
    assert np.allclose(fitted_matrix[2], [0.0, 0.0, 1.0], atol=1.0e-6)
    assert abs(fitted_bias[2]) < 1.0e-6
    assert fits["toy"].fit_axes == ["z"]


def test_fit_rbf_parameters_can_lock_existing_rbf_during_staged_axis_fit():
    specs = [SensorSpec(0, "sensor1", "toy_sensor", "toy", 3, 0, 3)]
    templates = {"toy": ToyTemplate()}
    true_config = {
        "toy": {
            "sigma_t0": 0.001,
            "sigma_n0": 0.0015,
            "outside_reject_dist": 0.02,
            "max_abs_normal_offset": 0.006,
            "min_raw_weight": 1.0e-8,
        }
    }
    renderer = TactileRenderer(specs, templates, true_config, total_taxels=3)
    contact = {"sensor_id": 0, "p_sensor": np.asarray([0.0, 0.0, 0.0]), "f_sensor": np.asarray([1.0, 0.0, 1.0])}
    samples = CalibrationSampleSet(
        sensor_id=np.asarray([0], dtype=np.int32),
        p_sensor=contact["p_sensor"].reshape(1, 3).astype(np.float32),
        f_sensor=contact["f_sensor"].reshape(1, 3).astype(np.float32),
        observed_detail_N=renderer.render([contact]).reshape(1, 3, 3).astype(np.float32),
    )
    staged_config = {
        "toy": {
            **true_config["toy"],
            "sigma_t0": 0.004,
            "sigma_n0": 0.003,
        }
    }

    fits = fit_rbf_parameters(
        samples,
        specs,
        templates,
        staged_config,
        candidate_sigma_t=[0.001],
        candidate_sigma_n=[0.0015],
        fit_axes=("x",),
        lock_rbf=True,
    )

    assert fits["toy"].sigma_t0 == 0.004
    assert fits["toy"].sigma_n0 == 0.003
    assert fits["toy"].fit_axes == ["x"]


def test_fit_tactile_calibration_cli_writes_updated_yaml(tmp_path: Path):
    calibration = yaml.safe_load(Path("configs/calibration.yaml").read_text(encoding="utf-8"))
    templates = load_templates("configs/taxel_templates")
    renderer = TactileRenderer(SENSOR_TABLE, templates, calibration["templates"], total_taxels())
    sensor = SENSOR_TABLE[0]
    p_sensor = templates[sensor.template].xyz_m[0]
    f_sensor = np.asarray([0.0, 0.0, 1.0], dtype=np.float64)
    observed = renderer.render([{"sensor_id": sensor.sensor_id, "p_sensor": p_sensor, "f_sensor": f_sensor}])
    samples = CalibrationSampleSet(
        sensor_id=np.asarray([sensor.sensor_id], dtype=np.int32),
        p_sensor=p_sensor.reshape(1, 3).astype(np.float32),
        f_sensor=f_sensor.reshape(1, 3).astype(np.float32),
        observed_detail_N=observed.reshape(1, total_taxels(), 3).astype(np.float32),
        metadata={"source": "synthetic_cli"},
    )
    sample_path = tmp_path / "samples.h5"
    out_yaml = tmp_path / "calibration.fitted.yaml"
    write_calibration_samples(sample_path, samples)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/fit_tactile_calibration.py",
            "--samples",
            str(sample_path),
            "--out",
            str(out_yaml),
            "--sigma-t",
            "0.003",
            "0.006",
            "--sigma-n",
            "0.0015",
            "0.003",
            "--fit-axes",
            "z",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    fitted = yaml.safe_load(out_yaml.read_text(encoding="utf-8"))
    assert "IP_M3025" in result.stdout
    assert "axes=z" in result.stdout
    assert fitted["templates"]["IP_M3025"]["sigma_t0"] == 0.003
    assert fitted["templates"]["IP_M3025"]["sigma_n0"] == 0.0015


def test_load_calibration_samples_csv_builds_hdf5_ready_samples(tmp_path: Path):
    csv_path = tmp_path / "samples.csv"
    csv_path.write_text(
        "\n".join(
            [
                "sample_id,sensor_id,px_m,py_m,pz_m,fx_N,fy_N,fz_N,taxel_id,x_N,y_N,z_N",
                "press_a,0,0,0,0,0,0,1,0,0,0,0.8",
                "press_a,0,0,0,0,0,0,1,1,0,0,0.2",
                "press_a,0,0,0,0,0,0,1,2,0,0,0",
                "press_b,1,0.001,0,0,0.1,0,2,0,0,0,0",
                "press_b,1,0.001,0,0,0.1,0,2,1,0,0,1.5",
                "press_b,1,0.001,0,0,0.1,0,2,2,0,0,0.5",
            ]
        ),
        encoding="utf-8",
    )

    samples = load_calibration_samples_csv(csv_path, total_taxels=3)

    assert samples.sensor_id.tolist() == [0, 1]
    assert np.allclose(samples.p_sensor[1], [0.001, 0.0, 0.0])
    assert np.allclose(samples.f_sensor[1], [0.1, 0.0, 2.0])
    assert np.allclose(samples.observed_detail_N[0, :, 2], [0.8, 0.2, 0.0])
    assert samples.metadata["source_format"] == "flat_csv_v1"


def test_convert_calibration_csv_cli_writes_hdf5(tmp_path: Path):
    csv_path = tmp_path / "samples.csv"
    h5_path = tmp_path / "samples.h5"
    csv_path.write_text(
        "\n".join(
            [
                "sample_id,sensor_id,px_m,py_m,pz_m,fx_N,fy_N,fz_N,taxel_id,x_N,y_N,z_N",
                "press_a,0,0,0,0,0,0,1,0,0,0,1.0",
                "press_a,0,0,0,0,0,0,1,1,0,0,0.0",
                "press_a,0,0,0,0,0,0,1,2,0,0,0.0",
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/convert_calibration_csv.py",
            "--input",
            str(csv_path),
            "--out",
            str(h5_path),
            "--total-taxels",
            "3",
            "--metadata",
            "source=test_fixture",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    loaded = load_calibration_samples(h5_path)
    assert "samples=1" in result.stdout
    assert loaded.observed_detail_N.shape == (1, 3, 3)
    assert loaded.metadata["source"] == "test_fixture"


def test_evaluate_rbf_fit_reports_zero_error_for_matching_synthetic_samples():
    specs = [SensorSpec(0, "sensor1", "toy_sensor", "toy", 3, 0, 3)]
    templates = {"toy": ToyTemplate()}
    config = {
        "toy": {
            "sigma_t0": 0.001,
            "sigma_n0": 0.0015,
            "outside_reject_dist": 0.02,
            "max_abs_normal_offset": 0.006,
            "min_raw_weight": 1.0e-8,
        }
    }
    renderer = TactileRenderer(specs, templates, config, total_taxels=3)
    observed = renderer.render(
        [{"sensor_id": 0, "p_sensor": np.asarray([0.0, 0.0, 0.0]), "f_sensor": np.asarray([0.0, 0.0, 1.0])}]
    )
    samples = CalibrationSampleSet(
        sensor_id=np.asarray([0], dtype=np.int32),
        p_sensor=np.asarray([[0.0, 0.0, 0.0]], dtype=np.float32),
        f_sensor=np.asarray([[0.0, 0.0, 1.0]], dtype=np.float32),
        observed_detail_N=observed.reshape(1, 3, 3),
    )

    report = evaluate_rbf_fit(samples, specs, templates, config)

    assert report.samples == 1
    assert report.rmse_N == 0.0
    assert report.peak_taxel_accuracy == 1.0


def test_evaluate_rbf_fit_uses_template_response_matrix_and_bias():
    specs = [SensorSpec(0, "sensor1", "toy_sensor", "toy", 3, 0, 3)]
    templates = {"toy": ToyTemplate()}
    config = {
        "toy": {
            "sigma_t0": 0.001,
            "sigma_n0": 0.0015,
            "outside_reject_dist": 0.02,
            "max_abs_normal_offset": 0.006,
            "min_raw_weight": 1.0e-8,
            "A_matrix": [[1.5, 0.0, 0.0], [0.0, -2.0, 0.25], [0.0, 0.0, 3.0]],
            "bias_N": [0.02, -0.01, 0.04],
        }
    }
    renderer = TactileRenderer(specs, templates, config, total_taxels=3)
    raw = renderer.render(
        [{"sensor_id": 0, "p_sensor": np.asarray([0.001, 0.0, 0.0]), "f_sensor": np.asarray([1.0, 2.0, 3.0])}]
    )
    observed = _apply_response(raw, specs[0], np.asarray(config["toy"]["A_matrix"]), np.asarray(config["toy"]["bias_N"]))
    samples = CalibrationSampleSet(
        sensor_id=np.asarray([0], dtype=np.int32),
        p_sensor=np.asarray([[0.001, 0.0, 0.0]], dtype=np.float32),
        f_sensor=np.asarray([[1.0, 2.0, 3.0]], dtype=np.float32),
        observed_detail_N=observed.reshape(1, 3, 3),
    )

    report = evaluate_rbf_fit(samples, specs, templates, config)

    assert report.rmse_N == 0.0
    assert report.mae_N == 0.0


def test_evaluate_rbf_fit_can_score_only_selected_axes():
    specs = [SensorSpec(0, "sensor1", "toy_sensor", "toy", 3, 0, 3)]
    templates = {"toy": ToyTemplate()}
    config = {
        "toy": {
            "sigma_t0": 0.001,
            "sigma_n0": 0.0015,
            "outside_reject_dist": 0.02,
            "max_abs_normal_offset": 0.006,
            "min_raw_weight": 1.0e-8,
        }
    }
    renderer = TactileRenderer(specs, templates, config, total_taxels=3)
    observed = renderer.render(
        [{"sensor_id": 0, "p_sensor": np.asarray([0.0, 0.0, 0.0]), "f_sensor": np.asarray([0.0, 0.0, 1.0])}]
    )
    observed[:, 0] = 10.0
    observed[:, 1] = -10.0
    samples = CalibrationSampleSet(
        sensor_id=np.asarray([0], dtype=np.int32),
        p_sensor=np.asarray([[0.0, 0.0, 0.0]], dtype=np.float32),
        f_sensor=np.asarray([[0.0, 0.0, 1.0]], dtype=np.float32),
        observed_detail_N=observed.reshape(1, 3, 3),
    )

    z_report = evaluate_rbf_fit(samples, specs, templates, config, axes=(2,))
    full_report = evaluate_rbf_fit(samples, specs, templates, config)

    assert z_report.rmse_N == 0.0
    assert full_report.rmse_N > 0.0


def test_evaluate_tactile_calibration_cli_reports_metrics(tmp_path: Path):
    calibration = yaml.safe_load(Path("configs/calibration.yaml").read_text(encoding="utf-8"))
    templates = load_templates("configs/taxel_templates")
    renderer = TactileRenderer(SENSOR_TABLE, templates, calibration["templates"], total_taxels())
    sensor = SENSOR_TABLE[0]
    p_sensor = templates[sensor.template].xyz_m[0]
    f_sensor = np.asarray([0.0, 0.0, 1.0], dtype=np.float64)
    observed = renderer.render([{"sensor_id": sensor.sensor_id, "p_sensor": p_sensor, "f_sensor": f_sensor}])
    sample_path = tmp_path / "samples.h5"
    write_calibration_samples(
        sample_path,
        CalibrationSampleSet(
            sensor_id=np.asarray([sensor.sensor_id], dtype=np.int32),
            p_sensor=p_sensor.reshape(1, 3).astype(np.float32),
            f_sensor=f_sensor.reshape(1, 3).astype(np.float32),
            observed_detail_N=observed.reshape(1, total_taxels(), 3).astype(np.float32),
        ),
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_tactile_calibration.py",
            "--samples",
            str(sample_path),
            "--axes",
            "z",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "samples=1" in result.stdout
    assert "rmse_N=0.000000e+00" in result.stdout


def _apply_response(raw: np.ndarray, spec: SensorSpec, A_matrix: np.ndarray, bias_N: np.ndarray) -> np.ndarray:
    responded = raw.copy()
    values = responded[spec.start : spec.end].astype(np.float64)
    responded[spec.start : spec.end] = (values @ A_matrix.T + bias_N).astype(np.float32)
    return responded
