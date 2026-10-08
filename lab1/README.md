# Lab 1: Set Up and Run a Robotic Hand

This lab helps you prepare your computer and check that a 3D robotic-hand simulation works.

## Step 1: Open the slides

Read [lab1.pdf](lab1.pdf), the Lab 1 slides.

## Step 2: Set up your environment

If you are using Windows with an Ubuntu virtual machine, follow [install.md](install.md).

If your course Python environment is already ready, activate it and continue below.

## Step 3: Install the Python packages

Open a terminal in the repository root, where you can see `lab1` and `lab2`. Run:

```bash
python -m pip install -r lab1/requirements.txt
```

## Step 4: Run the hand demo

```bash
python lab1/test_hand.py
```

A window should open with a hand and a block. The fingers move with random commands. The window closes after 500 simulation steps.

This checks your setup; the random commands are not a grasping strategy.

If the Ubuntu VM shows a black window, try:

```bash
LIBGL_ALWAYS_SOFTWARE=1 python lab1/test_hand.py
```

You can also follow the short [verification checklist](verification.md).

## Next

Continue to [Lab 2](../lab2/README.md), where you can change the object and a tactile grasping policy.
