# Dexh13 Hand with Tactile Sensors Simulation

**[English](#english) | [中文](#中文)**

---

## English

### Introduction

This repository provides the simulation model for the Dexh13 robotic hand, with a special focus on integrating tactile sensor data. It includes URDF models for use with ROS/Gazebo and MJCF models for use with MuJoCo, allowing for detailed physics simulation and sensor visualization.

### Repository Structure

-   **/config**: Contains configuration files, such as joint names.
-   **/example**: Includes example scenes, like `touch_grid.xml` for MuJoCo.
-   **/launch**: ROS2 launch files to start simulations in RViz (`display.launch.py`) and Gazebo (`gazebo.launch.py`).
-   **/meshes**: Stores the `.STL` mesh files that define the geometry of the hand parts.
-   **/mjcf**: Contains the MuJoCo models (`.mjcf.xml`), including versions with detailed tactile sensor sites.
  >- dexh13_hand_right_description.mjcf.xml: The base model without specific sensor plugins.
  >- `touch_dexh13_hand_right_description.mjcf.xml`: Model with the native MuJoCo `touch` sensor plugin.
  >- `touch_grid_dexh13_hand_right_description.mjcf.xml`: Model with the custom `touch_grid` sensor plugin.
-   **/rviz**: RViz configuration file for optimal visualization.
-   **/urdf**: Contains the URDF model of the hand, which is widely used in the ROS ecosystem.
-   `CMakeLists.txt` & `package.xml`: ROS2 package definition files.

### How to Use

#### 1. ROS2 & RViz (for URDF visualization)

This assumes you have a ROS2 environment set up.

1.  **Build the package:**
    Navigate to your ROS2 workspace and build:
    ```bash
    colcon build --packages-select dexh13_hand_right_description
    ```

2.  **Source the workspace:**
    ```bash
    source install/setup.bash
    ```

3.  **Launch the display:**
    To visualize the hand model in RViz, run the following launch file:
    ```bash
    ros2 launch dexh13_hand_right_description display.launch.py
    ```

#### 2. MuJoCo (for MJCF simulation)

This assumes you have `mujoco` installed in your Python environment.

1.  **Install MuJoCo:**
    ```bash
    pip install mujoco
    ```

2.  **Run the simulation:**
    You can directly run the simulation using MuJoCo's built-in viewer. From the root of this repository, run:

Windows:
```bash
python -m mujoco.viewer --mjcf=.\mjcf\dexh13_hand_right_description.mjcf.xml
```
Linux / macOS:
```bash
python3 -m mujoco.viewer --mjcf=./mjcf/dexh13_hand_right_description.mjcf.xml
```
Or view one of the examples (the command is the same for all OS):
```bash
python -m mujoco.viewer ./example/touch_grid.xml
```

---

## 中文

### 项目简介

本仓库提供了 Dexh13 机械手的仿真模型，并特别集成了触觉传感器。仓库中包含了适用于 ROS/Gazebo 的 URDF 模型和适用于 MuJoCo 的 MJCF 模型，可以用于精细的物理仿真和传感器数据可视化。

### 仓库结构

-   **/config**: 包含配置文件，例如关节名称定义。
-   **/example**: 包含示例场景，如用于 MuJoCo 的 `touch_grid.xml`。
-   **/launch**: ROS2 启动文件，用于在 RViz (`display.launch.py`) 和 Gazebo (`gazebo.launch.py`) 中启动仿真。
-   **/meshes**: 存放定义手部几何形状的 `.STL` 网格文件。
-   **/mjcf**: 包含 MuJoCo 模型 (`.mjcf.xml`)，其中包括带有详细触觉传感器位点的版本。

>dexh13_hand_right_description.mjcf.xml：无专用传感器插件的基础模型
touch_dexh13_hand_right_description.mjcf.xml：搭载 MuJoCo 原生 touch 触觉传感器的模型
touch_grid_dexh13_hand_right_description.mjcf.xml：搭载自定义 touch_grid 网格化触觉传感器的模型


-   **/rviz**: 用于优化的 RViz 配置文件。
-   **/urdf**: 包含手的 URDF 模型，该模型广泛用于 ROS 生态系统。
-   `CMakeLists.txt` & `package.xml`: ROS2 功能包定义文件。

### 如何使用

#### 1. ROS2 & RViz (用于 URDF 可视化)

此操作需要您已经配置好 ROS2 环境。

1.  **编译功能包:**
    进入您的 ROS2 工作空间并执行编译：
    ```bash
    colcon build --packages-select dexh13_hand_right_description
    ```

2.  **激活工作空间:**
    ```bash
    source install/setup.bash
    ```

3.  **启动显示:**
    要在 RViz 中可视化机械手模型，请运行以下启动文件：
    ```bash
    ros2 launch dexh13_hand_right_description display.launch.py
    ```

#### 2. MuJoCo (用于 MJCF 仿真)

此操作需要您的 Python 环境中已经安装了 `mujoco`。

1.  **安装 MuJoCo:**
    ```bash
    pip install mujoco
    ```

2.  **运行仿真:**
    您可以使用 MuJoCo 的内置查看器直接运行仿真。在仓库根目录下，运行：
    
    -   **Windows:**
        ```bash
        python -m mujoco.viewer --mjcf=.\mjcf\dexh13_hand_right_description.mjcf.xml
        ```
    -   **Linux / macOS:**
        ```bash
        python3 -m mujoco.viewer --mjcf=./mjcf/dexh13_hand_right_description.mjcf.xml
        ```

    或者查看一个示例场景（此命令在所有系统上通用）：
    ```bash
    python -m mujoco.viewer ./example/touch_grid.xml
    ```
