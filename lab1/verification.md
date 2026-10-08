# Lab 1: Quick Setup Check

No submission is required. This is a short check that your hand simulation opens and runs.

## 1. Install

Activate your course Python environment. From the repository root, run:

```bash
python -m pip install -r lab1/requirements.txt
```

## 2. Run

The script is already included; you do not need to copy or create it.

```bash
python lab1/test_hand.py
```

You should see a 3D hand and a block, with the fingers moving. The demo closes after 500 simulation steps and prints a completion message.

## 3. If the Ubuntu VM shows a black window

```bash
LIBGL_ALWAYS_SOFTWARE=1 python lab1/test_hand.py
```

For other installation problems, see [install.md](install.md). For the course slides, see [lab1.pdf](lab1.pdf).
