# SZTU Tactile Robotics

Hands-on labs for the Tactile Robotics course at SZTU.

Start with Lab 1 to set up your computer. Then follow Lab 2 to change an object, adjust a grasping policy, and observe touch feedback.

| Lab | What you will do | Instructions |
| --- | --- | --- |
| Lab 1 | Set up the course environment and run a robotic-hand demo | [Lab 1 README](lab1/README.md) |
| Lab 2 | Grasp objects, change a few parameters, and watch them hold or slip | [English](lab2/README.md) / [简体中文](lab2/README.zh-CN.md) |
| Lab 3 | Inspect tactile recordings, timestamps, validity and calibration | [English](lab3/tactile_analysis/README.en.md) / [简体中文](lab3/tactile_analysis/README.md) |
| Lab 4 | Replay recorded motion, train an MLP, and translate simulation latents into sensor latents | [English](lab4/README.md) / [简体中文](lab4/README.zh-CN.md) |

## First time here?

1. Download or clone this repository.
2. Open its folder in your editor, then open a terminal in that folder.
3. Follow the [Lab 1 setup guide](lab1/README.md).

Run all commands from the repository root: the folder containing `lab1` and `lab2`.

If your Python environment is already ready, install the shared course dependencies:

```bash
python -m pip install -r requirements.txt
```

Check the hand demo:

```bash
python lab1/test_hand.py
```

Then follow the [Lab 2 walkthrough](lab2/README.md) and run:

```bash
python lab2/examples/parameters.py --controller student
```

## Course files

```text
lab1/                              Setup guide, verification script, and slides
lab2/                              Tactile grasping experiment
lab3/tactile_analysis/              Tactile recording analysis
lab4/                              Replay, MLP, autoencoders and latent translation
dexh13-tactile-sim-dex13simv1/       Shared hand model and simulation assets
docs/                              Development conventions and teacher materials
```

Lab 1 slides: [lab1.pdf](lab1/lab1.pdf).

Lab 4 includes five measured episodes, 300 synthetic sequences, compact replay
snapshots and a step-by-step notebook. No new hardware collection is needed.
Its measured and generated signals are labelled separately. Full Lab 4 replay
uses its own virtual environment and MuJoCo version; the root requirements include
its ML dependencies without changing Labs 1/2's version. For CPU-only PyTorch
installation and the quick start, follow the [Lab 4 guide](lab4/README.md).

Keep the complete repository together. Lab 2 uses the shared hand model next to it. Each run saves its results locally; generated results are excluded from Git.

For contributors, see [development conventions](docs/DEVELOPMENT.md). Earlier teaching materials are kept in [teacher references](docs/teacher/README.md).

Recommended GitHub repository name: `sztu-tactile-robotics`.
