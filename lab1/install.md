# Tutorial: Installing VMware Workstation Pro & ROS 2 Humble & MuJoCo (China Network Edition)

**Course:** SZTU Tactile Robotics

The course files are in this repository. After setup, return to [Lab 1](README.md) and run the included verification script from the repository root.

**Target Environment:** Windows Host $\rightarrow$ VMware Workstation Pro $\rightarrow$ Ubuntu 22.04 LTS $\rightarrow$ ROS 2 Humble $\rightarrow$ MuJoCo

---

## Part 1: Download & Install VMware Workstation Pro

> **Important Licensing & Account Note:** Broadcom has made **VMware Workstation Pro free for personal and educational use**. You do **not** need serial key generators or pirated licenses. However, downloading the software directly from the official portal requires creating a free Broadcom account.

### 1. Download the Installer (Official Portal Path)

1. Visit the official VMware Workstation Pro Portal:
👉 **Official Download Portal:** [VMware Workstation Pro Official Documentation & Download Portal](https://techdocs.broadcom.com/us/en/vmware-cis/desktop-hypervisors/workstation-pro/17-0/using-vmware-workstation-pro.html)
2. Click the **Download** button on the product page.
3. You will be redirected to the **Broadcom Support Portal login page**:
* If you already have an account, enter your credentials.
* If not, click **Register / Create Account**, fill in your email address and basic profile information, and complete registration via the verification email sent to your inbox.


4. Once logged in, select **VMware Workstation Pro 17.x for Windows**, accept the End User Terms, and download the `.exe` installer.

---

### 2. Step-by-Step Installation Instructions

1. Locate your downloaded installer (`.exe`), right-click it, and select **"Run as administrator"**.
2. **Welcome Screen:** Click **Next**.
3. **End-User License Agreement:** Check *"I accept the terms in the License Agreement"* and click **Next**.
4. **Custom Setup (Crucial System Paths):**
* **Installation Directory:** By default, it installs to drive `C:\`. Because virtual machine disks consume significant storage, click **Change** and direct it to drive `D:\` or `E:\` (e.g., `D:\Program Files\VMware\VMware Workstation\`).
* ⚠️ **CRITICAL WARNING:** Ensure that your chosen installation path contains **ONLY English characters and NO spaces/Chinese characters** (e.g., avoid paths like `D:\软件\VMware`). Non-English characters in path names will break physics simulation rendering (e.g., MuJoCo / OpenGL) later in the course!
* **Console Tools:** Check the box **"Add VMware Workstation console tools into system PATH"**. This enables command-line interaction (`vmrun`).
* Check **"Enhanced Keyboard Driver"** if prompted. Click **Next**.


5. **User Experience Settings:**
* Uncheck *"Join the VMware Customer Experience Improvement Program"*.
* Click **Next**.


6. **Shortcuts:** Keep defaults (Desktop & Start Menu shortcuts checked) $\rightarrow$ Click **Next**.
7. **Execute Installation:** Click **Install**.
> **Note on Network Interruption:** During installation, your Windows host network connection may briefly flicker or disconnect. This is completely normal—VMware is installing virtual network adapters (`VMnet1` and `VMnet8`). Do **not** cancel or force-shutdown during this process!


8. **Finish & First-Time Activation:**
* Launch VMware Workstation Pro.
* When prompted for licensing upon first launch, select **"Use VMware Workstation 17 for Personal Use"** (or *Use for Free for Personal Use*).
* Click **Finish**. If prompted to restart your computer, save your work and **Restart immediately**.



---

## Part 2: Create an Ubuntu 22.04 LTS Virtual Machine

### 1. Download the Ubuntu ISO Image

Use a fast domestic mirror to download the desktop image:

* **Tsinghua University Mirror:** [https://mirrors.tuna.tsinghua.edu.cn/ubuntu-releases/22.04/](https://mirrors.tuna.tsinghua.edu.cn/ubuntu-releases/22.04/)
* Download filename: `ubuntu-22.04.5-desktop-amd64.iso` (or the latest 22.04 release).

### 2. Create the VM in VMware

1. Launch VMware Workstation Pro and click **"Create a New Virtual Machine"**.
2. Select **Typical (recommended)** $\rightarrow$ **Next**.
3. Select **Installer disc image file (iso)** $\rightarrow$ Browse and select your downloaded `ubuntu-22.04...iso` file.
4. **Easy Install Information:**
* Full name: `Student`
* User name: `ubuntu` *(or your preferred lowercase username)*
* Password: Set a memorable password (e.g., `123456`).


5. **Virtual Machine Name & Location:**
* Select a folder on Drive `D:\` or `E:\` (e.g., `D:\VirtualMachines\Ubuntu2204`).
* ⚠️ **Reminder:** Ensure the virtual machine storage directory path contains **NO Chinese characters**!


6. **Specify Disk Capacity:**
* Maximum disk size: **60.0 GB** *(Minimum recommended for ROS 2 + MuJoCo)*.
* Select **"Store virtual disk as a single file"** for optimal disk performance.


7. **Customize Hardware (Crucial Step):**
* **Memory:** Allocate **8192 MB (8 GB)** (or at least 4096 MB if host RAM is 8 GB).
* **Processors:** Assign **4 Cores** (or half of your host CPU's total threads).
* **Network Adapter:** Select **NAT** (Recommended for stable VM internet access).


8. Click **Finish** and allow Ubuntu to complete its automated installation.

---

## Part 3: Optimize Ubuntu APT Mirrors (China Network Acceleration)

After booting into Ubuntu, open a terminal (`Ctrl + Alt + T`). Default canonical servers are heavily throttled in China. We will switch APT sources to the **Tsinghua University Mirror**.

```bash
# 1. Backup default APT sources list
sudo cp /etc/apt/sources.list /etc/apt/sources.list.bak

# 2. Replace archive and security domains with Tsinghua mirror
sudo sed -i 's@http://.*archive.ubuntu.com@https://mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list
sudo sed -i 's@http://.*security.ubuntu.com@https://mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list

# 3. Update software package indexes
sudo apt update && sudo apt upgrade -y

```

---

## Part 4: Install ROS 2 and MuJoCo

### Step 1: Configure Locale (UTF-8)

```bash
sudo apt update && sudo apt install locales -y
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8

```

### Step 2: Add ROS 2 GPG Key & Domestic Repository

Standard ROS 2 keys hosted on GitHub (`raw.githubusercontent.com`) are typically unreachable due to DNS poisoning. Use the **Tsinghua ROS 2 Mirror Pipeline** instead:

```bash
# 1
sudo apt update
sudo apt install -y curl gnupg2 lsb-release

# 2
sudo rm -f /etc/apt/sources.list.d/ros2*.list
sudo rm -f /usr/share/keyrings/ros-archive-keyring.gpg
sudo rm -f /etc/apt/trusted.gpg.d/ros-archive-keyring.gpg

# 3(copy and paste the full following command into your terminal)
sudo curl -sSL https://mirrors.tuna.tsinghua.edu.cn/rosdistro/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg

# 4
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] https://mirrors.tuna.tsinghua.edu.cn/ros2/ubuntu $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

```

### Step 3: Install ROS 2 Packages

```bash
sudo apt update
sudo apt install ros-humble-desktop -y
```

### Step 4: Install MuJoCo & Gymnasium-Robotics

Set up a clean Python virtual environment and install MuJoCo alongside `gymnasium-robotics` (using Tsinghua PyPI mirror for accelerated downloads in China):

```bash
# Install Python virtual environment and build tools
sudo apt install python3-venv python3-pip git -y

# Create workspace and virtual environment
mkdir -p ~/tactile_ws && cd ~/tactile_ws
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install MuJoCo and Gymnasium-Robotics via Tsinghua Mirror
pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install mujoco==3.8.0 gymnasium==1.3.0 gymnasium-robotics==1.4.2 matplotlib numpy -i https://pypi.tuna.tsinghua.edu.cn/simple

```

### Step 5: Configure Environment Auto-Sourcing

Append ROS 2 and Python virtual environment initialization scripts to your `~/.bashrc`:

```bash
echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
echo "source ~/tactile_ws/venv/bin/activate" >> ~/.bashrc
source ~/.bashrc
```

### Step 6: Verify Installation with Shadow Hand Tactile Demo

Create a verification Python script `test_shadow_hand.py` that loads the Shadow Hand manipulation environment with integrated touch sensors:

```python
import gymnasium as gym
import gymnasium_robotics

# Create the Shadow Hand Block Manipulation environment with tactile sensors enabled
gym.register_envs(gymnasium_robotics)
env = gym.make('HandManipulateBlock_ContinuousTouchSensors-v1', render_mode='human')
obs, info = env.reset()

print("MuJoCo & Gymnasium-Robotics initialized successfully!")
print("Simulating Shadow Hand block manipulation with 92 touch sensor signals...\n")

# Run interactive simulation loop
for step in range(500):
    # Sample random action to control the 24-DOF Shadow Hand
    action = env.action_space.sample()
    obs, reward, terminated, truncated, info = env.step(action)

    # Access raw touch sensor array readings
    touch_data = obs['observation'][-92:]
    if touch_data is not None and step % 50 == 0:
        print(f"Step {step:03d} | Active Touch Sensors Count: {(touch_data > 0).sum()}/92")

    env.render()
    if terminated or truncated:
        obs, info = env.reset()

env.close()
print("Verification complete! Shadow Hand tactile environment is fully functional.")

```

Run the script to launch the 3D physics window:

```bash
python test_shadow_hand.py
```

---



## Frequently Asked Questions (Q&A) & Troubleshooting

### Q1: I installed Ubuntu inside VMware, but there is no internet connection! How do I fix this?

**A:** This is usually caused by Windows anti-virus tools or optimizer software disabling VMware background network services on your host computer.

1. On your Windows host, press `Win + R`, type `services.msc`, and press **Enter**.
2. Scroll down and locate **VMware NAT Service** and **VMware DHCP Service**.
3. Right-click both services, set their **Startup type** to **Automatic**, and click **Start**.
4. In VMware Workstation, go to `Edit` $\rightarrow$ `Virtual Network Editor`, click `Restore Defaults` at the bottom right corner, and click **Apply**.

---

### Q2: Why does the installer prompt "A restart is required before setup can continue"?

**A:** This occurs when leftover files from a previous or failed VMware installation exist in system temporary folders. Restart your computer as instructed; the installer will automatically resume after rebooting.

---

### Q3: What should I do if GPG key retrieval or APT download fails during Part 4 (ROS 2 Setup)?

**A:** If you encounter persistent network timeouts or repository authentication errors during manual setup, you can use **`FishROS`**—a popular automated installation script widely used in China—as a backup method to complete the environment setup quickly.

Because the script's interactive terminal interface is in **Chinese**, follow this step-by-step mapping guide:

1. Open your terminal in Ubuntu (`Ctrl + Alt + T`) and execute:
```bash
wget http://fishros.com/install -O fishros && bash fishros

```


2. **Step 1: Choose Installation Mode**
* Type `1` and press **Enter**.
* *Chinese Prompt:* `[1]: 一键安装:ROS/ROS2` (One-click ROS/ROS2 Installation)


3. **Step 2: Choose ROS Distribution**
* Type `2` and press **Enter**.
* *Chinese Prompt:* `[2]: ros2-humble(ROS2最新LTS版本)` (ROS2 Humble LTS)


4. **Step 3: Choose Desktop vs. Base Version**
* Type `1` and press **Enter**.
* *Chinese Prompt:* `[1]: humble-desktop(桌面版，包含Rviz2/Demo)` (Desktop Edition)


5. **Step 4: Select APT Mirror Source**
* Type `1` and press **Enter**.
* *Chinese Prompt:* `[1]: 清华源(推荐)` (Tsinghua Mirror - Recommended)


6. **Step 5: ROSDEP Dependency Tool Initialization (Optional)**
* When asked whether to clean up existing configurations or install `rosdepc` (a localized version of rosdep for China), select `1` to accept.


7. **Complete Installation:**
* Wait 3–5 minutes for the script to automatically update system dependencies and install packages.
* Once finished, restart your terminal or run `source ~/.bashrc`.

Environment IDs and touch-observation layout follow the [official Gymnasium-Robotics registry](https://github.com/Farama-Foundation/Gymnasium-Robotics/blob/main/gymnasium_robotics/__init__.py) and [touch-sensor implementation](https://github.com/Farama-Foundation/Gymnasium-Robotics/blob/main/gymnasium_robotics/envs/shadow_dexterous_hand/manipulate_touch_sensors.py).
