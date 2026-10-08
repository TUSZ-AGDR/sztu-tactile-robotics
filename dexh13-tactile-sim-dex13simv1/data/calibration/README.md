# Calibration Data

This folder is the default place for real DexH13 tactile calibration inputs and outputs.

Recommended layout:

```text
data/calibration/
├── raw/                         # Optional raw logs from your real SDK collector
├── real_press_samples.csv        # Input CSV consumed by convert_calibration_csv.py
├── real_press_samples.h5         # Generated locally; ignored by Git
├── calibration.fitted.yaml       # Optional fitted output if you choose to store it here
└── evaluation.txt                # Optional evaluation log
```

The project expects `real_press_samples.csv` to contain one full 1140-taxel frame for each `sample_id`.
See the root `README.md` section "实机触觉标定" for the exact schema and workflow.
