# Lab 2: Make the Hand Grasp an Object

English | [简体中文](README.zh-CN.md)

In this lab, you will watch a simulated hand close around an object. Then you will change a few numbers to make it hold the object or drop it.

You only need to edit two files:

| File | What you can change |
| --- | --- |
| [examples/parameters.py](examples/parameters.py) | Object, target grip force, mass, and friction |
| [student_policy.py](student_policy.py) | How the hand tightens or loosens in response to touch |

## Step 1: Set up

You need Python 3.10 or newer and the complete course repository. Keep `lab2` inside the repository, alongside the other simulation files.

Open the repository folder in your editor, then open a terminal. Its local name may be **Pacini_Course** or **sztu-tactile-robotics**. You should be able to see the `lab2` folder in the terminal's current directory.

If you are using the existing course Conda environment, activate it:

```bash
conda activate dexh13sim
```

Install the dependencies. You only need to do this once:

```bash
python -m pip install -r lab2/requirements.txt
```

## Step 2: Run your first grasp

Open `lab2/examples/parameters.py`. Find these four lines and set them as follows. Leave the rest of the file as it is:

```python
OBJECT_NAME = "box"
TARGET_FORCE_N = 4.0
MASS_KG = 0.03
FRICTION = 1.0
```

Save the file, then run:

```bash
python lab2/examples/parameters.py --controller student
```

**Use this command for every exercise below.** It uses both your parameter file and `student_policy.py`.

When the window opens:

1. The hand starts with all finger joints at zero and moves into position.
2. At 4 seconds, the object is released from its initial support. Watch whether the hand holds it.
3. The right side shows a touch heatmap, a grip-force graph, and an object-height graph.
4. Click the 3D window, then press `N` / `P` to switch sensors. Sensors that do not touch the object may show no color change.
5. The window stays open after the experiment. Close it when you are done.

**After each edit: save the file → close the old window → run again.**

## Step 3: Change the object

In `lab2/examples/parameters.py`, change only `OBJECT_NAME`:

| Object | What to write |
| --- | --- |
| Box | `OBJECT_NAME = "box"` |
| Sphere | `OBJECT_NAME = "sphere"` |
| Cylinder | `OBJECT_NAME = "cylinder"` |

Save the file and run again:

```bash
python lab2/examples/parameters.py --controller student
```

Watch how the hand movement and heatmap change with the object.

## Step 4: Change the grip force and policy

First, change one line in `parameters.py`:

```python
TARGET_FORCE_N = 2.0  # Also try 4.0 and 6.0.
```

A larger number asks the hand to grip harder. Change only this number first, then run the same command.

Next, open `lab2/student_policy.py` and find:

```python
GAIN = 0.1
```

Try `0.3` or `0.6`. This number controls how quickly the hand adjusts: a smaller value responds more slowly; a larger value responds faster and may cause oscillation.

For now, keep the function below as it is:

```python
def policy(obs):
    error = obs.target_force_N - obs.grip_force_N
    return GAIN * error
```

It tells the hand to tighten when the measured force is too low and loosen when it is too high.

Save and run:

```bash
python lab2/examples/parameters.py --controller student
```

Change one number at a time. Watch whether the object stays in the hand and whether the force graph becomes smoother. A larger number does not always give a better grasp.

## Step 5: Make the object slip

In `student_policy.py`, set:

```python
GAIN = 0.3
```

Then set the four lines in `parameters.py` to:

```python
OBJECT_NAME = "sphere"
TARGET_FORCE_N = 2.0
MASS_KG = 0.03
FRICTION = 0.05
```

This makes the surface very slippery. Save both files and run:

```bash
python lab2/examples/parameters.py --controller student
```

Watch after 4 seconds: the sphere slips out, and the height graph drops.

Change `FRICTION` back to `1.0` and run again to compare.

You can also try a different failure: restore the four parameters from Step 2 and set `GAIN = 0.01`. The hand closes too slowly to grip the object before it is released, so the object drops.

## Where are the results?

After you close the window, the terminal shows:

- `PASS`: this run passed.
- `FAIL`: this run failed, for example because the object dropped or the force was too high.
- `Results: ...`: the folder containing this run's results.

Open `curves.png` in that folder to see the force and height graphs. Open `heatmap.png` to see the touch heatmap.

If no window appears, check whether your command includes `--headless` or `--compare`. Both turn off the graphical window. If you see `No ... display is available`, run from a terminal on a computer with a desktop display.

Teachers can use the short [English demo script](TEACHING_SCRIPT.md) or the [Chinese walkthrough script](TEACHING_SCRIPT.zh-CN.md). The [teacher notes](TEACHER_NOTES.md) and [validation record](VALIDATION.md) cover model details, scoring rules, and automatic comparison commands in Chinese.
