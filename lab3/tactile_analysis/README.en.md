# DexH13 tactile data analysis from the command line

[中文 README](README.md)

This project provides command-line tools only. Analyze a recording ZIP, an extracted recording directory, or an HDF5 file directly. Optionally convert the entire recording to HDF5 for storage or other tools. Outputs include JSON, CSV, PNG, and optional MATLAB `.mat` files.

**The current real recording supports raw-signal diagnostics, not validated pressure or physical contact-area measurements.** Its taxel validity masks are all false, and force calibration, surface normals, and taxel areas have not been verified. Converting to HDF5 does not supply that missing information. This guide covers both immediately usable raw diagnostics and the calibrated area/pressure workflow using the same CLI.

## Contents

1. [Capabilities and prerequisites](#1-capabilities-and-prerequisites)
2. [Installation and working directory](#2-installation-and-working-directory)
3. [Import a ZIP and run your first analysis](#3-import-a-zip-and-run-your-first-analysis)
4. [Optional HDF5 conversion](#4-optional-hdf5-conversion)
5. [Analysis recipes](#5-analysis-recipes)
6. [Interpret raw outputs](#6-interpret-raw-outputs)
7. [Contact area and pressure: requirements and equations](#7-contact-area-and-pressure-requirements-and-equations)
8. [Run a complete synthetic area/pressure example](#8-run-a-complete-synthetic-areapressure-example)
9. [Prepare calibration for real hardware](#9-prepare-calibration-for-real-hardware)
10. [Arguments, Python API, and troubleshooting](#10-arguments-python-api-and-troubleshooting)
11. [Project files and validation](#11-project-files-and-validation)

## 1. Capabilities and prerequisites

| Quantity or task | Available for the current real ZIP? | Method or missing prerequisite |
| --- | --- | --- |
| Signed x/y/z values per taxel | Yes, readable | Original SDK counts; no unit conversion |
| Vector magnitude, peaks, above-threshold taxel counts | Raw diagnostics | Explicit `--allow-unverified`; raw units |
| Signal changes and candidate response intervals | Raw diagnostics | No automatic claim of contact or grasp phase |
| Taxel-index heatmaps | Yes | Index order is not a hand-surface geometry map |
| Eleven SDK summaries and temperature | Yes | Raw summary vectors; event temperatures in °C |
| Sampling rate and validity | Yes | Frames, host timestamps, packet flags, masks |
| Estimated contact area in mm² | Not yet | Verified taxels, a contact criterion, and effective taxel areas |
| Normal force in N and pressure in Pa/kPa | Not yet | Additionally measured force calibration and compressive normals |
| True spatial distribution over fingers | Not yet | Verified geometry; this version does not render a 3D hand |
| Slip detection and grasp-stability scores | Not implemented | No such inference is currently provided |

The supplied recording has 407 left-hand frames and 408 right-hand frames over approximately 46.5 seconds, at about 8.75 Hz. All 55 NPZ hashes match the manifest and all packet flags are valid, but there are no verified taxels or `sample_valid=true` frames. A false sample flag does not imply zero signal or absence of contact.

## 2. Installation and working directory

Run **all commands below from `lab3/tactile_analysis`**. Do not mix repository-root and module-relative paths.

### 2.1 macOS / Linux

On the current machine:

```bash
cd /Users/alaia/Developer/Pacini_Course/lab3/tactile_analysis
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[cli]'
```

On another machine, replace the `cd` path. If `.venv` already exists, activate it without recreating it. The `[cli]` extra installs NumPy, h5py, and matplotlib; it does not install Qt.

For MATLAB export:

```bash
python -m pip install -e '.[all]'
```

`[all]` additionally includes SciPy. A NumPy-only installation is insufficient for the plotting and HDF5 examples in this guide.

Check your interpreter and CLI:

```bash
python -c "import sys, numpy, h5py, matplotlib; print(sys.executable)"
python examples/analyze_recording.py --help
```

The interpreter should belong to the active `.venv`. Python 3.10 or newer is required.

### 2.2 Windows

```powershell
cd C:\your\path\Pacini_Course\lab3\tactile_analysis
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[cli]"
```

The subsequent `python examples/...` invocations have the same arguments. Bash `\` line continuations, `for` loops, and `python - <<'PY'` blocks do not work unchanged in PowerShell: put commands on one line and save Python blocks to `.py` files. The tested platform is macOS; Windows has not been tested.

### 2.3 Without installing this package

Install the dependencies and run the checkout entry scripts:

```bash
python -m pip install numpy h5py matplotlib
python examples/analyze_recording.py --help
python examples/convert_recording_to_hdf5.py --help
```

These scripts locate the local package without a manual `PYTHONPATH`. With the package installed, `tactile-analyze` is equivalent to `python examples/analyze_recording.py`; `tactile-convert-recording` is equivalent to the conversion script.

## 3. Import a ZIP and run your first analysis

Importing means passing a local path as the first argument. There is no upload service, extraction requirement, or mandatory HDF5 conversion.

The local working copy uses `teleop_20261021T090120_798e4203.zip`. Raw recording ZIPs and analysis outputs are not distributed through Git; after cloning, provide your own recording. If your copy is on an external disk, you can copy it locally:

```bash
mkdir -p inputs
cp "/Volumes/home/teleop_20261021T090120_798e4203.zip" "inputs/teleop_20261021T090120_798e4203.zip"
```

After copying, replace `./teleop_20261021T090120_798e4203.zip` in later commands with `inputs/teleop_20261021T090120_798e4203.zip`. An absolute external-disk path also works. Quote paths containing spaces.

### Step 1: inspect input and validity without producing an analysis report

```bash
python examples/analyze_recording.py \
  "./teleop_20261021T090120_798e4203.zip" \
  --list-trials --quiet
```

The JSON output contains:

- `verified_npz_count`: number of manifest NPZ hashes checked; 55 for this recording.
- `trial`: selectable names; `left` and `right` here.
- `frames`, `rate_hz`: frame count and average rate `(frames−1)/timestamp_span`.
- `packet_valid_fraction`: valid packet fraction.
- `verified_taxels`: taxels ever verified during the recording, not taxels with nonzero values.
- `sample_valid_fraction`: valid sample fraction. It is zero here, so subsequent commands explicitly enable raw diagnostics.

### Step 2: analyze the left hand directly

```bash
python examples/analyze_recording.py \
  "./teleop_20261021T090120_798e4203.zip" \
  --trial left \
  --allow-unverified \
  --contact-threshold 10 \
  --output-dir analysis_out/real_left_t10
```

Open `analysis_out/real_left_t10/overview.png` or `taxel_heatmap.png`. The flag `--allow-unverified` includes unverified entries in raw amplitude diagnostics; it does not change masks to true.

The threshold is 10 raw vector-magnitude counts, not 10 N or a calibrated contact threshold. It is an illustrative starting value.

**The output directory must not already exist.** For another run, choose a name such as `analysis_out/real_left_t10_run2`. Analysis never silently overwrites an earlier result.

## 4. Optional HDF5 conversion

Convert when you need a common storage format, all original streams in one file, or interoperability. Conversion does not calibrate, normalize, drop invalid taxels, or synchronize the hands.

```bash
mkdir -p analysis_out
python examples/convert_recording_to_hdf5.py \
  "./teleop_20261021T090120_798e4203.zip" \
  analysis_out/real_recording.h5
```

An extracted directory containing `manifest.json` directly is also accepted:

```bash
python examples/convert_recording_to_hdf5.py \
  "../data/teleop_20261021T090120_798e4203" \
  analysis_out/real_recording_from_directory.h5
```

Add `--overwrite` only when you intend to replace an existing HDF5 file. Conversion writes and checks a temporary file before replacing the destination; a failed conversion preserves the old file.

Analyze HDF5 with the same analysis command:

```bash
python examples/analyze_recording.py \
  analysis_out/real_recording.h5 \
  --trial left --allow-unverified --contact-threshold 10 \
  --output-dir analysis_out/from_hdf5_left_t10
```

### 4.1 HDF5 contents

| Path | Contents |
| --- | --- |
| `trials/left`, `trials/right` | Per-hand tactile analysis views, with independent frame counts and timestamps |
| `streams/<original_name>` | All manifest streams: hands, arms, operator, and controls |
| `events/temperature_readings` | Flattened temperature event table; no frame interpolation |
| `provenance/manifest_json` | Original manifest text |
| `provenance/events_jsonl` | Complete original event text, including non-temperature events |
| `provenance/conversion_report_json` | Input hashes, destination row ranges, read-back counts |

Per-hand datasets:

| Dataset | Shape | HDF5 type / meaning |
| --- | --- | --- |
| `taxel_raw` / `detail_xyz` | `[T,1140,3]` | Hard links to the same int32 raw-count dataset |
| `sensor_summary_raw` / `sensor_forces` | `[T,11,3]` | Hard links to the same int32 SDK summary dataset |
| `timestamp_ns` / `tactile_timestamps_ns` | `[T]` | int64 host monotonic completion timestamps, ns |
| `query_begin_ns` | `[T]` | int64 query start timestamps |
| `taxel_valid_mask` | `[T,1140]` | Original bool mask |
| `packet_valid`, `sample_valid` | `[T]` | Original bool flags |
| `hand_side` | `[T]` | UTF-8 strings |

Single-hand recordings produce only their recorded side. Conversion validates every manifest NPZ hash, field, shape, dtype, frame count, chunk time range, and monotonic chunk boundary; every field is read back after writing. Events and manifest text are retained. The events hash is a conversion-time provenance hash, not an independently supplied manifest checksum.

The analysis object uses float64 internally, while the HDF5 raw tactile arrays remain int32. Equal row indices do not imply synchronization between hands, arms, or temperatures.

## 5. Analysis recipes

These commands use the real ZIP in the current directory. Choose a new `--output-dir` for each run.

### 5.1 Right hand or both hands

```bash
python examples/analyze_recording.py ./teleop_20261021T090120_798e4203.zip \
  --trial right --allow-unverified --contact-threshold 10 \
  --output-dir analysis_out/real_right_t10

python examples/analyze_recording.py ./teleop_20261021T090120_798e4203.zip \
  --trial all --allow-unverified --contact-threshold 10 \
  --output-dir analysis_out/real_both_t10
```

Omitting `--trial` selects all trials. Hands are analyzed separately; equal row numbers are not treated as simultaneous samples. Each plotted hand starts at its own first frame.

### 5.2 Compare threshold sensitivity

```bash
for threshold in 5 10 20 50; do
  python examples/analyze_recording.py ./teleop_20261021T090120_798e4203.zip \
    --trial left --allow-unverified --contact-threshold "$threshold" \
    --output-dir "analysis_out/sweep_left_t${threshold}"
done
```

Compare `active_taxel_count_mean`, `active_taxel_count_peak`, and `contact_fraction` in each `trial_01/summary.json`. These quantify threshold exceedance, not physical contact area. Establish offsets/noise from explicitly identified unloaded data before choosing an experimental threshold. Do not assume the beginning of every recording is unloaded.

### 5.3 Smoothing, a selected frame, and a spatial layout

```bash
python examples/analyze_recording.py ./teleop_20261021T090120_798e4203.zip \
  --trial left --allow-unverified --contact-threshold 10 \
  --smooth-window 5 --heatmap-frame 100 \
  --output-dir analysis_out/left_smooth5_frame100
```

Smoothing operates on per-taxel vector magnitudes. Use a positive odd window; 1 disables smoothing. Endpoints are replicated at the boundaries. This example additionally exports frame 100, using zero-based numbering. Smoothing changes peaks and threshold crossing times; it is not sensor calibration.

For a verified layout, add `--taxel-positions calibration_results/left_layout.npy`. Its shape must be `[1140,2]` or `[1140,3]`, in the verified SDK order for that hand. A rectangular 2D layout can arrange max/mean maps; irregular layouts fall back to index maps. Only the first two coordinates of a 3D array are used; this does not render a 3D hand. Layout coordinates are not required for index plots or loading data.

### 5.4 Export one taxel's signed x/y/z values

```bash
python - <<'PY'
import numpy as np
from tactile_analysis.recording import load_recording

r = load_recording("./teleop_20261021T090120_798e4203.zip")
t = r.trials["left"]
point = 100  # Zero-based; valid indices are 0..1139.
time_s = (t.timestamps_ns - t.timestamps_ns[0]) / 1e9
np.savetxt("analysis_out/left_taxel100_xyz.csv",
           np.column_stack([time_s, t.detail_xyz[:, point, :]]), delimiter=",",
           header="time_s,x_raw,y_raw,z_raw", comments="",
           fmt=["%.9f", "%d", "%d", "%d"])
print(t.detail_xyz[0, point], "mask:", t.taxel_valid_mask[0, point])
PY
```

Earlier steps create `analysis_out`. The components are SDK values. Do not assume z is the surface normal or taxel 100 corresponds to a particular finger location without verification.

### 5.5 Temperature, SDK summaries, and sampling quality

After the both-hand command in section 5.1:

- `sensor_summary.png` shows magnitudes of the eleven SDK summary vectors. Summary values are not added to taxel aggregates.
- `temperature.png` plots temperature events by hand and sensor ID.
- `temperature_events.csv` contains selected-hand readings with independent event timestamps, preserving event order.
- `report.json` → `temperature_summary` contains reading count, minimum, maximum, and mean per hand.
- `report.json` → `data_quality` contains frames, duration, average rate, and validity statistics.

Temperature rows may not be globally sorted. Associate events by hand and timestamp when needed. No forward filling or per-frame interpolation is performed.

```bash
python - <<'PY'
import json
p = "analysis_out/real_both_t10/report.json"
r = json.load(open(p, encoding="utf-8"))
print(r["data_quality"])
print(r["temperature_summary"])
PY
```

### 5.6 MATLAB export

```bash
python examples/analyze_recording.py ./teleop_20261021T090120_798e4203.zip \
  --trial left --allow-unverified --contact-threshold 10 --export-mat \
  --output-dir analysis_out/real_left_mat
```

Each trial folder gains `analysis.mat`. In MATLAB:

```matlab
s = load('analysis_out/real_left_mat/trial_01/analysis.mat');
plot(s.time_s, s.active_taxel_count);
xlabel('Time (s)'); ylabel('Taxels above raw threshold');
```

### 5.7 Optional detailed raw audit

For an already extracted recording, the audit script additionally reports zero frames, repeated frames, axis ranges, byte-boundary observations, and threshold sensitivity:

```bash
python examples/audit_recording.py \
  ../data/teleop_20261021T090120_798e4203 \
  --output-dir analysis_out/audit_real
```

This helper accepts directories only. With only a ZIP, use the main CLI instead; this extra audit is optional. Byte-boundary observations are not an automatic saturation diagnosis, and zero/repeated values do not by themselves establish a faulty sensor.

## 6. Interpret raw outputs

```text
analysis_out/real_both_t10/
├── report.json
├── overview.png
├── taxel_heatmap.png
├── sensor_summary.png
├── temperature.png
├── temperature_events.csv
├── trial_01/
│   ├── summary.json
│   ├── frame_metrics.csv
│   ├── heatmap_max.png
│   ├── heatmap_mean.png
│   └── analysis.mat             # Only with --export-mat
└── trial_02/                    # When both hands are selected
```

Read `report.json` → `trial_folders` to map folders to hand names. Do not infer hand identity from a folder number. Each `summary.json` contains outer `summary` and `metadata` objects.

Let `q_i=sqrt(x_i²+y_i²+z_i²)` for taxel i. With smoothing enabled, the following definitions use the smoothed magnitude.

| CSV / summary field | Meaning in raw mode |
| --- | --- |
| `time_s` | Host time relative to that hand's first frame; frame indices for legacy files without timestamps |
| `active_taxel_count` | Number of taxels with `q_i >= threshold` |
| `total_contact_force` | Sum of above-threshold magnitudes; raw units, not resultant force |
| `peak_taxel_force` | Largest magnitude over all taxels, regardless of threshold |
| `mean_contact_force` | Arithmetic mean over above-threshold taxels; zero if none |
| `sensor_total_force` / `sensor_peak_force` | Sum / maximum of SDK summary-vector magnitudes, raw units |
| `contact_fraction` | Fraction of taxel-frame entries above threshold, not fraction of frames with contact |
| `force_impulse` | Trapezoidal integral of the above-threshold magnitude sum; raw·s, not N·s |
| `contact_duration_s` | Approximate threshold-response duration using right-endpoint frame states |
| `contact_area_mm2_*` | Null without usable areas; the current unverified raw recording produces no physical area |
| `mean_pressure*` | No physical pressure result is available for the current raw recording |

For legacy HDF5 files with no validity fields, raw mode retains compatibility: a successful run does not establish verified validity. Physical mode still requires the source quality fields.

Names containing `force` or `contact` are retained for compatibility. For this recording, `analysis_mode=unverified_raw_diagnostic`: interpret them as raw magnitudes and threshold statistics. This mode includes unverified entries and does not establish that contact occurred.

`heatmap_max.png` takes each taxel's own maximum over time; these maxima need not occur together. `heatmap_mean.png` is the per-taxel frame mean. `taxel_heatmap.png` displays time versus index. Statistical means are frame means, not time-weighted means. Durations and integrals use timestamps. If `time_source=frame_index`, historical time-related field names must not be interpreted as measured seconds or physical impulse.

## 7. Contact area and pressure: requirements and equations

### 7.1 Why the current recording is insufficient

Do not multiply 1140 by a guessed area, treat the SDK's claimed 0.1 N/count as verified calibration, or divide a 3D vector magnitude by area and call it normal pressure. With all source masks false, physical mode rejects this recording. `--allow-unverified` cannot bypass physical-mode validity checks.

### 7.2 What calibrated mode computes

Per taxel:

```text
F_i [N] = M_i [N/count] @ (raw_i - bias_i [count])
Fn_i = max(dot(F_i, normal_i), 0)
valid_i = source_taxel_mask_i AND calibration_verified_mask_i
          AND packet_valid AND sample_valid
contact_i = valid_i AND (Fn_i >= normal_threshold_n)
```

`normal_i` is a unit vector in the calibrated force coordinate system, with positive compression. Negative projections are treated as non-compressive. The algorithm does not assume z is normal and does not use the 3D magnitude as normal force.

```text
Estimated contact area A [mm²] = Σ contact_i * A_i
Normal-force scalar sum Fn_sum [N] = Σ contact_i * Fn_i
Per-taxel pressure p_i [Pa] = Fn_i / A_i[mm²] * 1,000,000 (contact taxels)
Mean contact pressure p_mean [Pa] = Fn_sum / A * 1,000,000
p [kPa] = p [Pa] / 1,000
```

This is a **thresholded discrete contact-area estimate over verified taxels**. Each active taxel contributes its full assigned area, with no sub-taxel contact-fraction estimation. Unverified regions are excluded, so this is not necessarily the complete hand contact area. Known areas are sufficient for the sum; spatial coordinates are only needed for geometric display.

With unequal taxel areas, mean pressure is area weighted, not the simple arithmetic mean of individual pressures. Sums of normal forces or tangential magnitudes are scalar summaries, not a resultant in a shared world frame. Tangential magnitude is `sqrt(||F_i||² - dot(F_i,normal_i)²)`, summed only over selected contact taxels.

### 7.3 No contact, invalid frames, and temporal statistics

- Valid frame with no taxel above the normal threshold: area, force, and count are zero; mean/peak contact pressure is NaN, summarized as JSON null. Undefined `0/0` is not reported as pressure zero.
- Frame without any effective valid taxel: its timestamp is retained, physical metrics are NaN, and it is not averaged as a valid zero/no-contact observation.
- No valid taxel anywhere in the recording: fail rather than write an all-zero pressure report.
- Pressure means average frames with defined contact pressure. Area and force means also include valid no-contact frames. These are frame averages.
- Duration uses right-endpoint contact states between adjacent valid frames. Impulse uses trapezoidal integration. Neither bridges invalid frames. Finite-rate threshold intervals are not precise physical onset/offset times.

## 8. Run a complete synthetic area/pressure example

This is a **four-taxel, three-frame arithmetic example**, not a DexH13 measurement. Its calibration is marked `synthetic_demo`; the program refuses to apply it to real recordings.

```bash
python examples/make_physical_demo.py analysis_out/physical_demo_input

python examples/analyze_recording.py \
  analysis_out/physical_demo_input/synthetic_trial.h5 \
  --trial left \
  --calibration analysis_out/physical_demo_input/synthetic_calibration.npz \
  --normal-threshold-n 0.1 \
  --output-dir analysis_out/physical_demo_result
```

Existing demo files and result directories are not overwritten. Choose new directory names for another run.

Only taxels 0, 1, and 3 are valid. Taxel 2 deliberately has large raw values and must be excluded. Each valid taxel is assigned a toy area of 2 mm², a toy matrix `0.1*I`, and positive z compression. These values demonstrate arithmetic only; do not copy them into real-hardware calibration.

| Frame (zero-based) | Contact taxels | Area mm² | Normal-force sum N | Mean pressure kPa | Peak taxel pressure kPa |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 | 0 | 0 | 0 | NaN | NaN |
| 1 | 2 | 4 | 3 | 750 | 1000 |
| 2 | 3 | 6 | 6 | 1000 | 1500 |

For frame 1: `3 N / 4 mm² = 750000 Pa = 750 kPa`.

```bash
python - <<'PY'
import csv, json
root = "analysis_out/physical_demo_result"
summary = json.load(open(root + "/summary.json", encoding="utf-8"))["summary"]
print("Peak area mm²:", summary["contact_area_mm2_peak"])   # 6
print("Peak local pressure Pa:", summary["peak_pressure_pa"])  # 1500000
with open(root + "/frame_metrics.csv", newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        print(row["time_s"], row["contact_area_mm2"], row["mean_pressure_kpa"])
PY
```

Physical-mode output:

```text
physical_demo_result/
├── summary.json
├── frame_metrics.csv
├── physical_arrays.npz
├── physical_overview.png
├── pressure_heatmap.png
└── analysis.mat                 # Only with --export-mat
```

Key physical CSV columns, all scoped to effective valid taxels:

| Column | Meaning |
| --- | --- |
| `time_s` | Seconds relative to this hand's first frame |
| `sample_valid` | At least one valid point after intersecting source quality and calibration masks |
| `verified_taxel_count` | Effective valid point count in this frame; check changing coverage when comparing frames |
| `active_taxel_count` | Valid points meeting the compressive normal threshold |
| `contact_area_mm2` | Sum of active-point areas, a discrete estimate |
| `normal_force_sum_n` | Scalar sum of compressive normal forces on contact taxels |
| `peak_taxel_normal_force_n` | Largest individual normal force among contact taxels |
| `tangential_magnitude_sum_n` | Sum of tangential magnitudes, not a world-frame resultant |
| `mean_pressure_pa` / `mean_pressure_kpa` | Area-weighted mean contact pressure in this frame |
| `peak_pressure_pa` / `peak_pressure_kpa` | Highest local contact pressure in this frame |

The summary field `normal_force_impulse_n_s` uses N·s. `mean_pressure_pa_mean` averages valid frames with defined contact pressure. CSV preserves NaN as `nan`; undefined pressure summaries use JSON null.

`physical_arrays.npz` contains `force_vector_n[T,N,3]`, `normal_force_n[T,N]`, `pressure_pa[T,N]`, `contact_mask`, `effective_valid_mask`, and `time_s`. Invalid taxels are NaN. Valid taxels not selected as contact contribute zero to the contact-pressure map.

## 9. Prepare calibration for real hardware

### 9.1 Work that must actually be completed

1. Verify enabled, healthy taxels. Configure the acquisition mask and collect new recordings with correct per-frame validity. Analysis does not promote historical false masks to true.
2. Measure unloaded three-axis offsets to obtain `bias_counts`.
3. Apply reference loads with known directions and magnitudes, fit raw-to-N matrices, and validate the range, linear approximation, and repeatability. This version supports an affine model, not nonlinear/hysteretic fitting.
4. Verify each taxel's force frame and positive compression direction to obtain unit `normal_vectors`.
5. Determine effective `taxel_area_mm2` from sensing-region geometry or measurements, not from the point count alone.
6. Match every calibration array to that hand's SDK taxel order. Correct array dimensions do not prove a correct physical mapping.

### 9.2 Complete calibration NPZ schema

Files are loaded with `allow_pickle=False`. Prepare separate calibration files for left and right hands; one physical analysis uses one hand's calibration.

| Field | Shape / type | Meaning |
| --- | --- | --- |
| `schema_version` | Integer scalar, 1 | Calibration format version |
| `hand_side` | String scalar | `left` or `right`, matching the selected input |
| `source_kind` | String scalar | `measured` for actual calibration; `synthetic_demo` for the example |
| `calibration_id` | Nonempty string scalar | Traceable calibration identifier |
| `force_matrix_n_per_count` | `[3,3]` or `[N,3,3]` | Shared or per-taxel matrix, N/count |
| `bias_counts` | `[3]` or `[N,3]` | Shared or per-taxel raw offset |
| `normal_vectors` | `[3]` or `[N,3]` | Unit compressive normal in calibrated force coordinates |
| `taxel_area_mm2` | Positive scalar or `[N]` | Effective taxel areas, mm² |
| `verified_taxel_mask` | bool `[N]` | Calibration-approved taxels; intersected with source masks |

All numbers must be finite, areas positive, and normals unit length. A `measured` label is not a substitute for an experiment: the program checks structure and numerical conditions, not the truth of calibration provenance. Retain the underlying calibration report.

The following packages **already measured result files**. It does not generate unknown coefficients. First place your own `.npy` arrays in `calibration_results/`:

```bash
python - <<'PY'
from pathlib import Path
import numpy as np
p = Path("calibration_results")
np.savez_compressed(
    p / "left_measured.npz",
    schema_version=np.array(1), hand_side=np.array("left"),
    source_kind=np.array("measured"), calibration_id=np.array("replace-with-your-measured-calibration-id"),
    force_matrix_n_per_count=np.load(p / "left_force_matrix_n_per_count.npy", allow_pickle=False),
    bias_counts=np.load(p / "left_bias_counts.npy", allow_pickle=False),
    normal_vectors=np.load(p / "left_normal_vectors.npy", allow_pickle=False),
    taxel_area_mm2=np.load(p / "left_taxel_area_mm2.npy", allow_pickle=False),
    verified_taxel_mask=np.load(p / "left_verified_taxel_mask.npy", allow_pickle=False),
)
PY
```

This section cannot run without the measured files. Use the synthetic example in section 8 to learn the workflow first.

### 9.3 Analyze a newly verified recording

Here `verified_trial.h5` and `left_measured.npz` are future files you actually prepare, not aliases for the current all-false-mask recording:

```bash
python examples/analyze_recording.py verified_trial.h5 \
  --trial left \
  --calibration calibration_results/left_measured.npz \
  --normal-threshold-n 0.1 \
  --output-dir analysis_out/verified_left_pressure
```

The 0.1 N normal threshold is still an example. Choose it using measured noise, resolution, and your experiment's contact criterion. Do not add `--allow-unverified`, a raw threshold, raw smoothing, or `--taxel-area-mm2`; physical mode uses calibrated areas. For the right hand, change the trial, calibration file, and destination directory.

Physical mode permits partially valid taxels/frames, intersects masks, and preserves missing values. This differs from raw mode's default requirement that all provided validity entries be true. Calibration never overrides source validity, and nonzero values never automatically establish a verified taxel.

## 10. Arguments, Python API, and troubleshooting

### 10.1 Main analysis arguments

| Argument | Default / usage |
| --- | --- |
| `input` | First positional argument: ZIP, recording directory, or HDF5 |
| `--trial` | Default `all`; `left`, `right`, or an actual HDF5 trial name |
| `--list-trials` | Inspect input without analysis |
| `--output-dir` | Default `analysis_out`; must not exist; explicitly set it for each run |
| `--allow-unverified` | Off by default; raw diagnostics only |
| `--contact-threshold` | Raw default 10; vector magnitude greater than or equal to threshold |
| `--smooth-window` | Raw default 1; positive odd integer |
| `--heatmap-frame` | `max`, `mean`, or nonnegative frame index; max/mean always exported, numeric selection adds a snapshot |
| `--taxel-positions` | Optional `.npy` layout for raw max/mean/snapshot maps |
| `--taxel-area-mm2` | Legacy equal-area proxy, requiring complete raw validity; not the real-pressure workflow |
| `--force-unit` | CLI accepts `raw` only; N requires calibrated mode, not relabeling |
| `--calibration` | Single-hand calibration NPZ; enables physical mode |
| `--normal-threshold-n` | Physical default 0.1 N; finite and positive |
| `--export-mat` | Supported in both modes; requires SciPy |
| `--quiet` | Suppress stderr progress; stdout still contains result JSON |

The legacy `--taxel-area-mm2` option multiplies above-threshold taxels by a common area. Its `mean_pressure` is a vector-magnitude-sum/area proxy, potentially in raw/mm²; it is not normal pressure. The current unverified real recording rejects this option. Prefer the verified-normal, measured-force workflow in sections 7–9.

### 10.2 Python API

```python
from tactile_analysis import AnalysisConfig, analyze_trial
from tactile_analysis.recording import load_recording
from tactile_analysis.physical import analyze_physical, export_physical

recording = load_recording("./teleop_20261021T090120_798e4203.zip")
raw = analyze_trial(recording.trials["left"], AnalysisConfig(
    contact_threshold=10, allow_unverified=True, smooth_window=1))
print(raw.summary)
# Only run the following after preparing real calibration and verified source data:
# physical = analyze_physical(verified_trial, "calibration_results/left_measured.npz", normal_threshold_n=.1)
# export_physical(physical, "analysis_out/verified_pressure_api")
```

The existing `load_hdf5(path, trial="left")` and `analyze_hdf5(...)` APIs remain available. The main CLI writes the multi-trial report tree in section 6. The legacy `analyze_hdf5(output_dir=...)` API writes single-trial files directly into its destination rather than creating that multi-trial tree.

### 10.3 Troubleshooting

| Symptom | Action |
| --- | --- |
| `No module named ...` | Activate the intended `.venv`; install `[cli]`, or `[all]` for MATLAB |
| ZIP / manifest not found | Check `pwd`, quoting, and full path; directory input must contain manifest directly |
| `SHA-256 mismatch` | Recopy and investigate the recording; do not edit the checksum to bypass the problem |
| `contains invalid/unverified...` | Add `--allow-unverified` for raw diagnostics only |
| `No verified taxels remain` | Verify acquisition and calibration masks; the current all-false recording is ineligible for physical analysis |
| `already exists` | Choose a new analysis directory; conversion supports explicit `--overwrite` |
| `Unknown trial` | Run `--list-trials` and use a listed name |
| `hand_side does not match` | Supply the correct hand's calibration |
| `Synthetic demo calibration cannot...` | Use measured calibration for real data |
| Smoothing error | Use positive odd values such as 1, 3, 5 |
| Frame index out of range | Use 0..T−1; the left recording's final index is 406 |
| Pressure is `nan` / null | Distinguish invalid frames from no-contact frames; do not replace all missing values with zero |
| Heatmap is one long row | No rectangular spatial layout was supplied; it is an index plot |
| Unwritable matplotlib cache | Set `MPLCONFIGDIR="$PWD/.mpl-cache"`; this does not change data values |

Means are not time weighted. Raw integration does not automatically remove large timestamp gaps or infer device-side dropped frames. Query-completion timestamps are not hardware sample times. Do not align hands or arms by row number.

## 11. Project files and validation

```text
examples/analyze_recording.py            Main analysis entry
examples/convert_recording_to_hdf5.py    Entire-recording converter
examples/make_physical_demo.py           Runnable synthetic area/pressure example
examples/audit_recording.py              Detailed extracted-directory audit
examples/convert_npz_to_hdf5.py          Legacy single-NPZ helper; not an entire-recording converter
examples/make_demo_hdf5.py               Legacy raw demo; not actual hardware calibration

tactile_analysis/recording.py            ZIP / directory / HDF5 loader
tactile_analysis/report.py               Raw reports and plots
tactile_analysis/physical.py             Normal force, area, pressure and physical reports
tactile_analysis/convert_recording.py    Lossless conversion and integrity checks
```

Run tests:

```bash
python -m unittest discover -s tests -v
```

Coverage includes lossless chunk/string conversion, corruption rejection, ZIP/directory/HDF5 equivalence, raw validity and CLI outputs, known area/pressure arithmetic, non-z normals, per-taxel calibration, unequal-area weighted pressure, invalid frames, no validity promotion, and rejection of synthetic calibration on real input.

The real-recording audit is in [REPORT.zh-CN.md](reports/teleop_20261021T090120_798e4203/REPORT.zh-CN.md). It describes the historical inspection; use this README for current commands and entry points. Pressure units follow the [NIST SI unit table](https://www.nist.gov/pml/special-publication-330/sp-330-appendix-1): Pa = N/m², so converting N/mm² to Pa multiplies by 10⁶.

Local command-validation outputs are archived in `analysis_out/readme_validation/`, leaving the main tutorial destinations available for your first run. Archived provenance paths describe the original generation locations; see `relocations.json` for relocations.
