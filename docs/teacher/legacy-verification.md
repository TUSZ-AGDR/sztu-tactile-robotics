# 📢 3-Minute After-Class Verification: Test Your MuJoCo Robotic Hand Setup

> **Note:** No submission is required for this exercise. This is a quick self-check to verify that 3D hardware acceleration and the MuJoCo physics engine are functioning properly inside your virtual machine.

---

### Step 1: Install Core Dependencies

Open your Ubuntu terminal (`Ctrl + Alt + T`) and execute this command (using the Tsinghua mirror for accelerated downloads in China):

```bash
pip install mujoco gymnasium-robotics -i https://pypi.tuna.tsinghua.edu.cn/simple
```

*(Note: If you configured a virtual environment, activate it first; otherwise, running it directly in your terminal/system Python is also fine.)*

---

### Step 2: Create Test Script & Run

Open a text editor in your terminal by running `gedit test_hand.py`, paste the following 12 lines of code, and save:

```python
import gymnasium as gym
import gymnasium_robotics

# 1. Load OpenAI's classic in-hand block manipulation environment (with 3D GUI window)
env = gym.make("HandManipulateBlock-v1", render_mode="human")
env.reset()

print(">>> Initializing 3D physics engine. Press Ctrl+C in terminal to exit...")

# 2. Animate the robotic hand (run for 500 simulation steps)
for _ in range(500):
    action = env.action_space.sample()  # Random joint actuation commands
    env.step(action)
    env.render()

env.close()
print(">>> 🎉 Congratulations! Your MuJoCo simulation environment is fully ready!")
```

Run the script:

```bash
python3 test_hand.py
```

---

### ✅ Success Checklist

A **3D simulation window** will pop up showing an anthropomorphic 5-fingered robotic hand holding and manipulating a cube with subtle finger motions.
* **Camera Controls:** Drag with the `Left Mouse Button` to rotate the view, scroll the `Mouse Wheel` to zoom, and drag with the `Right Mouse Button` to pan.

---

### ❓ Troubleshooting (Black Screen or Crash)

If the 3D window is completely black or crashes immediately, this is an occasional OpenGL hardware acceleration issue in VMware Workstation. Run the script with software rendering fallback instead:

```bash
export LIBGL_ALWAYS_SOFTWARE=1 && python3 test_hand.py
```
