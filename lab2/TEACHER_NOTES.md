# Lab 2：教师与维护者参考

学生操作步骤见 [README.md](README.md)。本文保留模型、评分和复用接口的详细说明。

修改一两行参数或策略，在 MuJoCo 中让 DexH13 固定手位握住物体。比较固定闭合和触觉反馈：物体能否保持 3 秒，轻拉后是否掉落，抓握力是否超过上限。

## 1. 安装与快速运行

需要 Python 3.10 或更新版本，保留本仓库完整目录。`lab2` 复用旁边的 `dexh13-tactile-sim-dex13simv1` 手模型、mesh 和 taxel 模板，不能只拷贝 `lab2` 文件夹。

从仓库根目录运行（建议先激活课程虚拟环境）：

```bash
python -m pip install -r lab2/requirements.txt
python lab2/run.py
```

默认打开一个窗口：三维手及触觉彩色点、选定传感器的二维热力图、握力曲线和物体高度曲线。先点击三维窗口获得键盘焦点，再按 `N` 选择下一个传感器，按 `P` 选择上一个；标题显示当前编号和名称。实验结束后仍可切换传感器和调整窗口大小，关闭窗口即可退出。`--close-on-finish` 可让窗口自动关闭。

`[` / `]` 保留为兼容键，但 MuJoCo 原生也用它们切换相机，建议使用 `N` / `P`。部分传感器没有接触物体，切换后热力图全为冷色是正常情况。

Windows 和 Linux 使用普通 Python；macOS 命令行入口会自动通过当前环境的 `mjpython` 启动 GUI，也可以直接执行 `mjpython lab2/run.py`。若没有图形环境，使用：

```bash
python lab2/run.py --headless
python lab2/run.py --compare
```

`--compare` 自动关闭 GUI，依次运行两个方法并保存对比图；这些命令无需 GPU、OpenGL 窗口或 Jupyter。MuJoCo 的物理仿真仍然正常运行。GUI 不可用时不会自动把失败隐藏成成功。

无显示器的远程会话或受限执行环境会提示 `No ... display is available`，此时使用 `--headless` 或 `--compare`，在桌面终端中另行测试 GUI。

## 2. 实验在做什么

1. **0–2 秒：** 16 个手指关节从实际零位开始，先停留 0.3 秒，再平滑进入捏持准备姿态。物体由初始 weld 支撑，这个阶段不调用学生控制器。
2. **2–4 秒：** 从准备姿态开始，由固定闭合或触觉策略控制捏持。
3. **4 秒：** 解除支撑约束，之后不再修改物体的位姿或速度。
4. **4–7 秒：** 在真实重力下保持物体；默认 **5.5–5.75 秒** 对物体施加 0.1 N 向下拉力，可关闭。
5. **评分：** 同时检查保持与力上限。

手基座固定，采用拇指与食指的捏持预设，其余手指保持张开。学生输出统一闭合速率，库用预计算的关节轨迹执行动作。提供 `box`、`cylinder`、`sphere` 三个预设；尺寸固定，位置与动作已分别配置。

注意：`closure=0` 表示预设捏持轨迹的准备姿态，**不是关节零位**。默认新增的 `approach` 阶段负责从各关节零位运动到准备姿态；移动只通过执行器控制，不直接改写运行中的关节位姿。Python 接口可用 `Experiment(approach_time_s=0, release_time_s=2)` 从准备姿态开始，采用原先的 5 秒时序；固定闭合预设值已按新版重新标定，结果不等同于旧版。

**模型近似：** 保留 DexH13 原始外观和关节，两个主动接触面使用简化平面碰撞垫以获得可重复的课程捏持。采用 `condim=6`，滑动摩擦由 `friction` 控制，扭转/滚动摩擦参数固定为 0.02 / 0.01。模型开启重力与无滑移求解迭代。此处是教学仿真，不是厂家标定的触觉模型，也不用于直接推断真机抓握性能。碰撞垫以半透明蓝色显示，原始白色传感器 mesh 仅用于外观。

## 3. Baseline 和对比方法

| 方法 | 输入触觉？ | 动作 | 可修改内容 |
| --- | --- | --- | --- |
| `fixed` baseline | 否 | 以规定速率闭合到 `fixed_closure`，之后保持 | 固定闭合量 |
| `tactile` | 是 | 依据目标力误差收紧或放松，带死区和速率限制 | 目标力、增益 |
| `student` | 是 | 调用 `student_policy.py` 中的函数 | 一两行反馈逻辑 |

两个对比方法共用物体、从零位运动到准备姿态的流程、捏持关节轨迹、初始支撑、释放时刻、扰动、采样频率、评分规则与随机种子。每次运行重新创建物理状态，不把上次运行的姿态带入下一次。不同对象的预设动作经过准备，但不会根据方法或目标力自动重新调姿态。

默认固定闭合量按默认质量/摩擦下、释放前约 4 N 的标称抓握力预先设置：方块 0.5927、圆柱 0.6070、球 0.6115。标定只使用有支撑时 3.8–4.0 秒的平均握力，不根据释放后的成功/失败挑选闭合量。改变测试条件后这些预设保持不变；可通过 `--fixed-closure` 手动设置，实际使用值记录在 `fixed_closure_used`。如果目标力改为其他值并希望比较同等力度，应在独立的标定条件中先选定 baseline 闭合量，再固定下来测试。

```bash
python lab2/run.py --compare --out lab2/outputs/my-comparison
python lab2/run.py --compare --object sphere
python lab2/run.py --compare --object cylinder --no-disturbance
python lab2/run.py --compare --include-student
```

对比指标：

| 指标 | 定义 | 如何解释 |
| --- | --- | --- |
| `success` | 完整跑完，未掉落/逃离/受到外部支撑，且没有持续超力 | 单次是否成功，不叫“成功率” |
| `held_time_s` | 释放后到首次保持失败的时间，上限 3 秒 | 越长越好；超力失败可能仍保持 3 秒 |
| `peak_force_N` | 全实验每个物理步的原始握力最大值 | 握住的同时是否用力过大 |
| `overforce_time_s` | 原始握力超过上限的累计时长 | 显示超力负担 |
| `longest_overforce_s` | 最长连续超限时间 | 达到 0.02 秒即判超力失败 |
| `force_tracking_rmse_N` | 保持阶段采样握力与目标力之间的 RMSE | 力控制表现；必须结合掉落与超力结果看 |

不预设触觉方法一定胜出。固定闭合也可能在某些条件下成功。完整比较应报告多个质量/摩擦设置，而不是挑选一个有利例子。

## 4. 基础练习：改参数

打开 `examples/parameters.py`，优先只改下面一行：

```python
TARGET_FORCE_N = 4.0  # 分别测试 2.0、4.0、6.0
```

运行：

```bash
python lab2/examples/parameters.py
python lab2/examples/parameters.py --headless
```

再试着把 `OBJECT_NAME = "box"` 改为 `"sphere"` 或 `"cylinder"`。也可以用命令行修改参数：

```bash
python lab2/run.py --target-force 6 --mass 0.05 --friction 0.6
python lab2/run.py --compare --friction 0.3
```

默认质量 0.03 kg、滑动摩擦系数 1.0、目标握力 4 N。其他参数组合可能失败，失败本身就是实验观察；任意大质量或低摩擦不保证能握住。

### 看一次明显的滑落

在 `examples/parameters.py` 设置：

```python
OBJECT_NAME = "sphere"
TARGET_FORCE_N = 2.0
MASS_KG = 0.03
FRICTION = 0.05
```

运行 `python lab2/examples/parameters.py` 打开 GUI。4 秒解除初始支撑后，球会滑落；这组参数已在当前版本实测，判定保持失败的时间为释放后约 0.053 秒，物体最终落到地面。若原本已用球、2 N、0.03 kg，只需改摩擦一行。恢复 `FRICTION = 1.0` 后再做其他单因素比较。

另一个失败来源是闭合过慢：将 `student_policy.py` 的 `GAIN` 改为 `0.01`，运行 `python lab2/examples/policy.py`。默认方块、4 N 下已实测：释放时尚未接触夹住物体，随后掉落。这是“尚未夹住”的失败，与“夹住后滑落”不同。

`parameters.py` 默认运行内置 `tactile` 控制器，修改 `student_policy.py` 不会影响它。要同时使用参数文件和学生策略，运行 `python lab2/examples/parameters.py --controller student`；`examples/policy.py` 则使用库的默认参数。

## 5. 进阶练习：改反馈策略

打开 `student_policy.py`：

```python
GAIN = 0.3

def policy(obs):
    error = obs.target_force_N - obs.grip_force_N
    return GAIN * error
```

返回值单位为 **闭合量/秒**，正数收紧，负数放松，零保持。库按控制周期积分并限制闭合量到 `[0, 1]`，速率限幅为 `±0.6 /s`。不要返回关节角或力。可以修改增益，或添加：

```python
if abs(error) < 0.1:
    return 0.0
```

运行并与 baseline 比较：

```bash
python lab2/examples/policy.py
python lab2/run.py --compare --include-student
```

`obs` 提供 `time_s`、`tactile_time_s`、`phase`、`closure`、`grip_force_N`、`target_force_N`、`sensor_forces_N`（11 个传感器）和 `taxel_normal_N`（1140 点）。数组只读。学生策略不读取物体真实位置；位置只用于可视化和独立评分。

## 6. 触觉、色标与评分口径

- **握力单位 N：** 目标物体与触觉垫之间各接触点的正法向力求和。这是抓握力指标，不是把两侧相反方向的力相加得到的物体合力。
- **触觉热力图：** 利用原项目 RBF 空间权重，将每个法向接触力分配到对应传感器的 taxel，保持法向力之和。这里只合成法向分量；没有宣称重现厂家三轴触觉输出。
- **固定色标：** 两种热力图都固定为 0–0.25 N/taxel，切换方法或传感器不自动缩放。超过色标上限会饱和，但评分使用未裁剪的原始接触力。
- **二维位置：** 根据每种模板的几何点进行 PCA 平面投影，保留点的实际布局；不是随意 reshape 张量。投影是观察工具，不是传感器工艺展开图。
- **频率：** 物理 2000 Hz，课程触觉平均采样和控制 100 Hz，图像刷新约 15 Hz。与原项目 10 Hz SDK 风格采样独立，课程不修改原配置。
- **力上限：** 默认 12 N，连续超限至少 0.02 秒判失败；单个尖峰仍进入峰值和累计时间，但不单独判超力失败。
- **保持失败：** 高度下降超过 15 mm，或相对初始位置移动超过 40 mm，或持续至少 0.02 秒受到手掌/地面等非触觉支撑。失败一旦出现就保留，不会因为后来落在手掌上而恢复成功。
- **可选噪声：** `--noise 0.1 --seed 7` 只改变控制器看到的总握力，热力图为原始合成触觉，评分始终使用原始力。对比方法使用同一噪声计划。

曲线中的力是 100 Hz 窗口平均值，评分峰值是 2000 Hz 原始值，因此短暂尖峰可能不会完整显示在曲线里。`tactile_time_s` 表示平均窗口结束时刻，策略只使用已产生的触觉帧。

## 7. 输出与课程记录

默认写入 `lab2/outputs/<物体>-<唯一编号>/`，避免覆盖旧实验。每个方法包含：

```text
fixed/ 或 tactile/ 或 student/
  summary.json   # 参数、评分和力的定义
  trace.csv      # 可直接用 Excel/Notebook 读取的时序数据
  episode.npz    # taxel、关节、物体位姿等数组；不依赖 pickle
  curves.png     # 实际运行的握力与高度曲线
  heatmap.png    # 保持中点时刻的食指指尖二维触觉图，固定色标
comparison.csv / comparison.json / comparison.png
```

建议记录“方法、物体、质量、摩擦、目标力/固定闭合量、是否成功、保持时间、峰值力、超力时长”，再用热力图和曲线解释差异。一个实验只改变一个参数。若需要成功率，按预先固定的条件表重复实验后计算成功次数/总次数；确定性设置重复同一个 seed 不会产生新样本。

Python 复用接口：

```python
from lab2 import Experiment

result = Experiment(object_name="box", target_force_N=4.0).run(
    "tactile", headless=True, output_dir="lab2/outputs/api-example")
print(result.describe())
```

## 8. 自检与维护

```bash
python -m pytest lab2/tests -q
python lab2/tools/build_presets.py   # 维护者重新生成三个闭合轨迹，学生不需要执行
```

测试覆盖默认三物体保持、弱闭合掉落、强闭合超力、支撑解除、法向力守恒、重置与随机可重复性、数据导出、异工作目录加载，以及学生策略观测边界。

本次本地验证环境与具体测试结果见 `VALIDATION.md`。Windows/Linux 的 GUI 需要在对应平台另行验证。Linux 虚拟机如果 3D 窗口黑屏，可先用 `--headless` 验证物理；需要软件渲染时尝试 `LIBGL_ALWAYS_SOFTWARE=1 python lab2/run.py`。
