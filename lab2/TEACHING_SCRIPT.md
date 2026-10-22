# Lab 2: Short Demo Script

English | [中文讲稿](TEACHING_SCRIPT.zh-CN.md)

Keep the [README](README.md) open and follow its steps. **Do** is your action; the quoted text is what you can say.

## Start

**Do:** Open the README.

> Today, we will make a simulated hand hold an object. We will change a few numbers and see what happens.
>
> We only need to edit two files: `parameters.py` and `student_policy.py`.

## Step 1: Set up

**Do:** Follow the setup commands in the README. Skip installation if it is already done.

> First, open a terminal in the course folder and activate the course environment.

## Step 2: Run a grasp

**Do:** Set the four parameters as shown in README Step 2: `box`, `4.0`, `0.03`, and `1.0`. Set `GAIN = 0.1` in `student_policy.py`. Save, then run:

```bash
python lab2/examples/parameters.py --controller student
```

> The hand closes around the box. At four seconds, the initial support is removed. Watch whether the box stays in the hand.

**Do:** Let the experiment finish, then point to the display.

> The colored dots show where the hand feels contact and how much force it feels.
>
> The heatmap shows one touch sensor. Click the 3D window and press N or P to switch sensors.
>
> Below it, the first graph shows grip force. Blue is the measured force, green is the target, and red is the limit.
>
> The bottom graph shows object height. If the object falls, this line goes down.

## Step 3: Change the object

**Do:** Close the window. Change only `OBJECT_NAME` to `"sphere"`, save, and run the same command.

> Now we change the box to a sphere. Watch the contact colors and see whether it stays in the hand.

## Step 4: Change the force and policy

**Do:** Restore the box settings from Step 2. Change only `TARGET_FORCE_N` to `2.0`, save, and run.

> Now we ask for less grip force. Watch how the force graph changes.

**Do:** Restore the target to `4.0`. Change only `GAIN` from `0.1` to `0.3`, save, and run.

> This policy tightens the hand when force is too low and loosens it when force is too high. GAIN controls how quickly it adjusts.

## Step 5: Make it slip

**Do:** Use the settings from README Step 5: `sphere`, `2.0`, `0.03`, friction `0.05`, and `GAIN = 0.3`. Save both files and run.

> This time, the surface is slippery. Watch the sphere and the height graph after four seconds.

**Do:** Change only `FRICTION` back to `1.0` and run again.

> Now we increase friction. Compare this run with the previous one.

## Finish

**Do:** Close the window and show the result folder printed in the terminal.

> You can find the graphs in the result folder. Now try changing one number at a time and record what changes.
>
> Each time: save your file, close the old window, and run again.
