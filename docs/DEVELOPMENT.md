# Course Repository Conventions

Course: **SZTU Tactile Robotics**. GitHub repository name: **sztu-tactile-robotics**.

Keep all course labs in this repository. Students download the course once and run commands from the repository root.

## Layout

```text
README.md                          Course overview and links to each lab
requirements.txt                   Dependencies for all labs
lab1/
  README.md                        Beginner walkthrough
  install.md                       VM and course environment setup
  verification.md                  Short setup check
  test_hand.py                     Hand demo
  requirements.txt
  lab1.pdf                         Official Lab 1 slides
lab2/
  README.md
  README.zh-CN.md
  requirements.txt
  examples/
  student_policy.py
  ...
dexh13-tactile-sim-dex13simv1/       Shared hand model and simulation code
docs/
  DEVELOPMENT.md
  teacher/                         Earlier teaching materials and design notes
```

## Rules for each lab

1. Use `lab1`, `lab2`, and so on. Keep each lab's teaching files together.
2. Write a short English README with copyable commands: install, run, edit, and observe. A Chinese version can use `README.zh-CN.md`.
3. Run commands from the repository root. Use one main command throughout a beginner tutorial, so edits to both parameters and policies take effect.
4. Tell students exactly which files and numbers to edit. Keep simulator internals out of their first exercise.
5. Keep Python comments and docstrings in English. Use descriptive English filenames without spaces.
6. List each lab's Python dependencies in `requirements.txt`. Include its requirements file from the root `requirements.txt`.
7. Keep only one copy of shared simulation code and model assets. Lab 2 references the existing shared model folder by its name and location.
8. Keep experiment outputs, virtual environments, caches, and temporary files out of Git. Keep detailed model and scoring notes separate from the student README.

## Adding a lab

Create a `labN` folder with a short README, a requirements file, and a runnable example. Add the lab to the course table in the root README and include its requirements in the root requirements file.

Before publishing a change, check the README links and run the documented example. Use a desktop display to check the graphical window. Use headless runs to check physics and exported data.

Current Lab 2 checks:

```bash
python -m pytest lab2/tests -q
```

The local folder remains `Pacini_Course`; the GitHub repository can be named `sztu-tactile-robotics`. Do not embed a developer's absolute folder path in course scripts.

The current course materials and model assets are prepared locally. Creating a GitHub remote and uploading the repository are separate steps.
