# DexH13 MuJoCo 触觉仿真最终技术方案

>  
> 文档目标：明确说明要解决什么问题、输入是什么、输出是什么、怎么实现、做到什么程度算完成。  
> 核心修正：真实上层阵列点读取频率按 **10 Hz** 处理；MuJoCo 内部仿真仍建议 **2 kHz**。

---

## 1. 项目目标

本项目要在 MuJoCo 中构建 DexH13 灵巧手触觉仿真系统，使仿真环境能在抓取、按压、滑动等交互过程中输出与真实 DexH13 SDK 阵列触觉数据同构的数据，用于后续触觉编码器、模仿学习数据训练。

最终输出的核心触觉张量为：

```text
detail_N      float32 [1140, 3]   # SDK 轴下的三维力，单位 N
detail_sdk    float32 [1140, 3]   # SDK-like 数值，是否等于真实 SDK 原始单位需标定
raw_sensor_N  float32 [1140, 3]   # 传感器物理局部轴下的三维力，单位 N
```

其中：

```text
1140 = 11 片触觉传感器的 taxel 总数
3    = 每个 taxel 的三轴力 Fx, Fy, Fz
```

本项目第一版追求的是：

```text
MuJoCo 刚体接触力
  → 官方 3D taxel 坐标
  → Contact-to-Taxel RBF 触觉渲染
  → PX-6AX 等效响应模型
  → 10 Hz HDF5 数据集
```

---

## 2. 问题定义

### 2.1 要解决的问题

真实 DexH13 的触觉传感器不是规则图像网格，而是安装在 11 个指节上的非规则 3D taxel 阵列。MuJoCo 原生接触只给出接触点和接触力，不能直接输出与真实 SDK 对齐的 `[1140, 3]` 阵列触觉数据。

因此，本工程要解决的问题是：

```text
如何把 MuJoCo 中连续接触点的物理接触力，转换为 DexH13 官方 1140 个 taxel 上的三轴触觉输出。
```

### 2.2 第一版必须做到

| 目标 | 要求 |
|---|---|
| 形状一致 | 输出 `[1140, 3]`，与真实 SDK taxel 顺序一致 |
| 轴向一致 | 输出轴通过 `M_sdk_sensor` 对齐 SDK 轴 |
| 单位明确 | `detail_N` 用 N；`detail_sdk` 用 SDK-like 数值 |
| 频率一致 | 阵列触觉输出频率为 **10 Hz** |
| 可标定 | RBF、增益、偏置、噪声、量程都写入 `calibration.yaml` |
| 可验收 | 通过 M0~M7 工程测试，M8 做真机标定对照 |

### 2.3 第一版不做什么

第一版明确不做：

```text
1. 不做霍尔磁场、磁体、电路、硅胶 FEM 全链路仿真。
2. 不为 1140 个 taxel 分别建立 1140 个 collision geom。
3. 不把官方 3D taxel 点投影成 Touch Grid。
4. 不依赖 MuJoCo 原生 touch sensor 作为正式输出。
5. 不强行复刻真实 SDK 内部算法，只做可标定的等效响应模型。
6. 不在第一版精确复刻真实 PIP/DIP 非线性耦合机构。
```

---

## 3. 硬件与数据约束

### 3.1 传感器数量与 taxel 顺序

整手共有 11 片传感器，1140 个 taxel。所有代码、配置和数据集必须使用以下固定顺序。

```python
SENSOR_TABLE = [
    # sensor_id, sdk_name,  name,             template,   n,   start, end
    (0,  "sensor1",  "index_proximal",  "IP_M3025", 120,    0,  120),
    (1,  "sensor2",  "index_middle",    "MP_M2324",  60,  120,  180),
    (2,  "sensor3",  "index_tip",       "DP_M2826", 120,  180,  300),
    (3,  "sensor4",  "middle_proximal", "IP_M3025", 120,  300,  420),
    (4,  "sensor5",  "middle_middle",   "MP_M2324",  60,  420,  480),
    (5,  "sensor6",  "middle_tip",      "DP_M2826", 120,  480,  600),
    (6,  "sensor7",  "ring_proximal",   "IP_M3025", 120,  600,  720),
    (7,  "sensor8",  "ring_middle",     "MP_M2324",  60,  720,  780),
    (8,  "sensor9",  "ring_tip",        "DP_M2826", 120,  780,  900),
    (9,  "sensor10", "thumb_proximal",  "IP_L5325", 120,  900, 1020),
    (10, "sensor11", "thumb_tip",       "DP_L3530", 120, 1020, 1140),
]
```

点数构成：

```text
1140 = 120 × 8 + 60 × 3

120 点传感器：
  IP_M3025 × 3  = sensor1 / sensor4 / sensor7
  DP_M2826 × 3  = sensor3 / sensor6 / sensor9
  IP_L5325 × 1  = sensor10
  DP_L3530 × 1  = sensor11

60 点传感器：
  MP_M2324 × 3  = sensor2 / sensor5 / sensor8
```

规则：

```text
1. 整手张量 tactile[1140, 3] 的 start:end 切片必须严格对应 SENSOR_TABLE。
2. 每片传感器内部 taxel 顺序必须等于官方 CSV 行顺序。
3. 禁止为了实现方便重排 taxel。
```

### 3.2 传感器坐标原点

每个 PX-6AX 传感器的官方 taxel 坐标使用传感器自身坐标系。该坐标系原点定义在传感器硅胶尾部底面中点。

工程要求：

```text
1. 官方 taxel 3D 坐标必须直接导入。
2. 不允许投影成规则 2D 图像网格。
3. MJCF 中每片传感器必须有一个 sensor site。
4. sensor site 的局部坐标系必须与官方 taxel 坐标系一致。
```

### 3.3 采样率

真实上层阵列点读取频率按 10 Hz 处理。

```text
MuJoCo 内部仿真步长：sim_dt = 0.0005 s = 2 kHz
触觉输出频率：tactile_hz = 10 Hz
对齐方式：每 200 个 MuJoCo step 输出 1 帧
```

计算：

```text
1 / (10 × 0.0005) = 200
```

工程规则：

```text
1. ContactReader 和 Renderer 每个 MuJoCo step 都运行。
2. TactileSampler 累加 200 个 sub-step 后输出 1 个 10 Hz 触觉帧。
3. 10 秒 episode 应输出 100 帧。
4. 不再使用 80 Hz 作为正式数据集输出频率。
```

### 3.4 量程初值

```text
法向 Fz：0 ~ 25 N
切向 Fx/Fy：-10 ~ 10 N
lsb_per_N 初值：10.0，仅用于 detail_sdk 初值，必须用真实 SDK 标定确认
```

---

## 4. 系统总体架构

```text
DexH13 MJCF
  → MuJoCo step
  → ContactReader 读取有效接触点和接触力
  → 转换到对应 sensor site 局部坐标系
  → TactileRenderer 用 RBF 分配到官方 taxel 点
  → TactileSampler 做 2 kHz → 10 Hz 累加平均
  → SensorResponse 做 SDK 轴对齐、增益、偏置、噪声、饱和
  → DatasetWriter 写 HDF5
```

模块边界：

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `TaxelTemplate` | 加载 5 类官方 taxel CSV | CSV | `xyz_m`, `normals`, `KDTree` |
| `SensorMount` | 管理 11 片传感器实例和 site 位姿 | `sensors.yaml`, `MjModel` | `T_WS`, `geom_to_sensor` |
| `ContactReader` | 读取 MuJoCo 接触并转到 sensor 系 | `model`, `data` | `contacts` |
| `TactileRenderer` | RBF 分配接触力到 taxel | `contacts` | `raw_sensor_N [1140,3]` |
| `TactileSampler` | 2 kHz 累加平均到 10 Hz | `raw_sensor_N` | `raw_avg_N [1140,3]` |
| `SensorResponse` | 生成 SDK 对齐输出 | `raw_avg_N` | `detail_N`, `detail_sdk` |
| `DatasetWriter` | 写 HDF5 数据集 | 每帧数据 | `.h5` |

---

## 5. 工程目录

```text
dexh13_mujoco_tactile/
├── README.md
├── pyproject.toml
├── assets/
│   ├── dexh13_raw/                  # 官方 URDF / mesh / CAD
│   └── dexh13_mjcf/
│       ├── hand.xml                 # 主 MJCF
│       ├── tactile_geoms.xml        # 11 个 tactile collision geom + 11 个 sensor sites
│       └── test_press_scene.xml     # 单点压入测试场景
├── configs/
│   ├── taxel_templates/
│   │   ├── IP_M3025.csv
│   │   ├── MP_M2324.csv
│   │   ├── DP_M2826.csv
│   │   ├── IP_L5325.csv
│   │   └── DP_L3530.csv
│   ├── sensors.yaml
│   ├── calibration.yaml
│   └── sim.yaml
├── dexh13_tactile/
│   ├── __init__.py
│   ├── sensor_table.py
│   ├── taxel_template.py
│   ├── sensor_mount.py
│   ├── contact_reader.py
│   ├── tactile_renderer.py
│   ├── tactile_sampler.py
│   ├── sensor_response.py
│   └── dataset_writer.py
├── scripts/
│   ├── build_mjcf.py
│   ├── run_press_test.py
│   ├── run_collection.py
│   ├── fit_calibration.py
│   └── visualize_tactile.py
└── tests/
    ├── test_taxel_count.py
    ├── test_site_alignment.py
    ├── test_contact_sign.py
    ├── test_zero_no_contact.py
    ├── test_force_conservation.py
    ├── test_outside_reject.py
    ├── test_sampler_10hz.py
    └── test_hdf5_schema.py
```

---

## 6. 依赖环境

```toml
[project]
name = "dexh13_tactile"
requires-python = ">=3.10"

dependencies = [
    "mujoco>=3.1.0",
    "numpy>=1.24",
    "scipy>=1.10",
    "pyyaml>=6.0",
    "h5py>=3.8",
]

[project.optional-dependencies]
dev = ["pytest>=7", "pytest-cov", "matplotlib", "trimesh"]
```

说明：

```text
1. 推荐 Ubuntu 20.04 / 22.04。
2. 本项目不需要 GPU。
3. MuJoCo 版本固定为 >= 3.1.0，避免 contact API 差异。
```

---

## 7. 输入文件定义

### 7.1 taxel 模板 CSV

每类传感器一个 CSV，单位为 mm，加载后立即转为 m。

```csv
taxel_id,x_mm,y_mm,z_mm,nx,ny,nz
0,-11.29,0.97,1.65,0,0,1
1,-11.23,3.37,1.66,0,0,1
...
```

字段定义：

| 字段 | 含义 |
|---|---|
| `taxel_id` | 模板内 taxel 编号，从 0 开始连续 |
| `x_mm,y_mm,z_mm` | taxel 在传感器局部坐标系下的位置，单位 mm |
| `nx,ny,nz` | taxel 局部法向，单位向量 |

要求：

```text
1. IP_M3025.csv 必须 120 行。
2. MP_M2324.csv 必须 60 行。
3. DP_M2826.csv 必须 120 行。
4. IP_L5325.csv 必须 120 行。
5. DP_L3530.csv 必须 120 行。
6. normals 必须归一化，误差 < 1e-6。
```

如果官方没有法向：

```text
1. 用每个点的 kNN 邻域做 PCA。
2. 最小特征向量作为局部曲面法向。
3. 统一翻转到传感器外侧。
4. 用单点压入测试 M2 验证正负方向。
```

### 7.2 sensors.yaml

```yaml
instances:
  - sensor_id: 0
    sdk_name: sensor1
    name: index_proximal
    template: IP_M3025
    parent_body: index_proximal_link
    parent_geom: index_proximal_tactile_geom
    site_name: site_index_proximal_sensor_frame
    M_sdk_sensor: [[1,0,0],[0,1,0],[0,0,1]]

  - sensor_id: 1
    sdk_name: sensor2
    name: index_middle
    template: MP_M2324
    parent_body: index_middle_link
    parent_geom: index_middle_tactile_geom
    site_name: site_index_middle_sensor_frame
    M_sdk_sensor: [[1,0,0],[0,1,0],[0,0,1]]
```

规则：

```text
1. `sensor_id` 必须与 SENSOR_TABLE 一致。
2. `template` 必须是 5 类模板之一。
3. `parent_geom` 必须对应 MJCF 中的 tactile collision geom。
4. `site_name` 必须对应 MJCF 中的 sensor site。
5. `M_sdk_sensor` 表示 F_sdk = M_sdk_sensor @ F_sensor。
6. 不确定 SDK 轴方向时先用单位阵，后续用真机数据标定。
```

### 7.3 calibration.yaml

```yaml
global:
  sim_dt: 0.0005
  tactile_hz: 10
  lsb_per_N: 10.0
  force_on_geom1: true
  random_seed: 0

templates:
  IP_M3025:
    sigma_t0: 0.0030
    sigma_n0: 0.0015
    outside_reject_dist: 0.010
    max_abs_normal_offset: 0.006
    min_raw_weight: 1.0e-4
    A_matrix: [[1,0,0],[0,1,0],[0,0,1]]
    bias_N: [0,0,0]
    noise_std_N: [0.02,0.02,0.03]
    tau_s: 0.0
    clip_N:
      x: [-10, 10]
      y: [-10, 10]
      z: [0, 25]
```

说明：

```text
1. `sigma_t0` 控制切向 RBF 扩散。
2. `sigma_n0` 控制法向 RBF 扩散。
3. `A_matrix` 用于传感器增益和交叉轴耦合。
4. `bias_N` 表示零点偏置。
5. `noise_std_N` 表示加性高斯噪声。
6. `tau_s` 在 10 Hz 输出下默认 0，因为 200 步累加平均已经起到抗混叠作用。
7. 5 类 template 必须分别配置和标定。
```

### 7.4 sim.yaml

```yaml
sim:
  mjcf_path: assets/dexh13_mjcf/hand.xml
  episode_seconds: 10.0
  random_seed: 0

control:
  policy: scripted

object:
  type: cube
  size_m: [0.04, 0.04, 0.04]
  init_pose: [0.10, 0, 0.05, 1, 0, 0, 0]

dataset:
  out_dir: data/episodes/
  filename_pattern: ep_{idx:05d}.h5
```

---

## 8. MJCF 构建要求

### 8.1 每片传感器只建一个 tactile collision geom

示例：

```xml
<body name="index_proximal_link">
  <geom name="index_proximal_tactile_geom"
        type="mesh"
        mesh="index_proximal_tactile_surface"
        contype="1" conaffinity="1"
        friction="1.0 0.02 0.001"
        solref="0.005 1"
        solimp="0.90 0.95 0.001"/>

  <site name="site_index_proximal_sensor_frame"
        pos="0 0.015 0.005"
        quat="1 0 0 0"
        size="0.001"
        group="3"/>
</body>
```

要求：

```text
1. tactile geom 表示真实传感器可接触表面。
2. sensor site 表示官方 taxel 坐标系。
3. 每片传感器只允许一个主要 tactile collision geom。
4. 不允许同一区域有多个 collision geom 重复计力。
5. 视觉 mesh 可以保留，但不得与 tactile geom 同时重复参与接触。
6. 1140 个 taxel 只作为渲染输出点，不作为 MuJoCo collision geom。
```

### 8.2 关节模型

第一版保留 16 个等效串联关节。

```text
0  index_mcp_yaw       1  index_mcp_pitch    2  index_pip      3  index_dip
4  middle_mcp_yaw      5  middle_mcp_pitch   6  middle_pip     7  middle_dip
8  ring_mcp_yaw        9  ring_mcp_pitch    10  ring_pip      11 ring_dip
12 thumb_cmc_yaw      13 thumb_cmc_pitch   14 thumb_mcp     15 thumb_ip
```

控制规则：

```text
1. 仿真内部状态保存 16 维 qpos_serial / qvel_serial。
2. 上层如果输入 13 维电机命令，则由 joint_map.yaml 映射到 16 维。
3. PIP/DIP 耦合第一版可以用线性近似，例如 dip = 2/3 × pip。
4. 不要因为关节耦合不完美阻塞触觉数据管线。
```

---

## 9. 坐标系与单位

### 9.1 坐标系

| 符号 | 名称 | 含义 |
|---|---|---|
| W | world | MuJoCo 世界坐标系 |
| L | link | 指节 body 局部坐标系 |
| S | sensor | 传感器 site 局部坐标系，等于官方 taxel 坐标系 |
| K | SDK | SDK 输出轴坐标系 |
| C | contact | MuJoCo 单个 contact 的局部坐标系 |

### 9.2 强制规则

```text
1. taxel CSV 中的 xyz 和 normal 永远在 S 系。
2. Renderer 内部所有几何计算都在 S 系。
3. MuJoCo site 位姿直接读 data.site_xpos / data.site_xmat。
4. 禁止手算 T_world_link @ T_link_sensor。
5. 只在 SensorResponse 中做一次 S 系到 SDK 系的轴变换。
```

### 9.3 单位

```text
CSV 位置输入：mm
内部位置计算：m
内部力计算：N
detail_N：N
detail_sdk：SDK-like 数值
角度：rad
四元数：w, x, y, z
```

---

## 10. 模块实现规格

### 10.1 TaxelTemplate

职责：加载 5 个 taxel CSV，输出坐标、法向和 KDTree。

```python
@dataclass
class TaxelTemplate:
    name: str
    xyz_m: np.ndarray      # [n, 3]
    normals: np.ndarray    # [n, 3]
    kdtree: scipy.spatial.cKDTree
```

验收：

```text
1. 5 个 template 行数正确。
2. taxel_id 从 0 连续递增。
3. xyz 从 mm 转成 m。
4. normals 已归一化。
```

### 10.2 SensorMount

职责：注册 11 片 sensor instance，查询 sensor site 世界位姿。

```python
class SensorMount:
    def __init__(self, model, sensors_yaml, templates_dir): ...
    def get(self, sensor_id: int): ...
    def get_world_sensor_pose(self, sensor_id: int, data) -> np.ndarray: ...
    def geom_to_sensor(self) -> dict[int, int]: ...
```

核心实现：

```python
def get_world_sensor_pose(self, sensor_id, data):
    s = self.by_id[sensor_id]
    t = np.asarray(data.site_xpos[s.site_id], dtype=np.float64)
    R = np.asarray(data.site_xmat[s.site_id], dtype=np.float64).reshape(3, 3)
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = t
    return T
```

验收：

```text
将 1140 个 taxel 从 S 系转换到 W 系后可视化，点云必须覆盖在 11 个 tactile geom 表面。
```

### 10.3 ContactReader

职责：读取 MuJoCo contact，过滤无效接触，输出 sensor 系下的接触点和接触力。

输入：

```text
model, data, mount, geom_to_sensor, force_on_geom1
```

输出：

```python
contacts = [
    {
        "sensor_id": int,
        "p_sensor": np.ndarray,  # [3], m
        "f_sensor": np.ndarray,  # [3], N
        "contact_id": int,
        "geom0": int,
        "geom1": int,
    },
    ...
]
```

过滤规则：

```text
1. 跳过 exclude != 0。
2. 跳过 efc_address < 0。
3. 跳过两边都不是 tactile geom 的接触。
4. 跳过两边都是 tactile geom 的自接触。
```

力方向规则：

```text
1. c.frame.reshape(3,3) 的三行是 contact frame 的 normal/tangent1/tangent2 在 world 系下的方向。
2. f_world = c.frame.reshape(3,3).T @ force6[:3]。
3. f_world 默认假设为作用在 geom[1] 上的力。
4. 是否反号只允许通过 calibration.yaml 的 force_on_geom1 控制。
5. 禁止在 Renderer 或 Response 中再次翻转力符号。
```

### 10.4 TactileRenderer

职责：把连续接触点的力分配到对应传感器的离散 taxel。

输入：

```text
contacts: list[dict]
```

输出：

```text
raw_sensor_N float32 [1140, 3]
```

RBF 公式：

```text
delta_i = p - x_i
n_i     = taxel normal

d_n_i = dot(delta_i, n_i)
d_t_i = norm(delta_i - d_n_i * n_i)

w_i_raw = exp(-0.5 * (d_t_i / sigma_t)^2)
        * exp(-0.5 * (d_n_i / sigma_n)^2)

w_i = w_i_raw / sum(w_i_raw)
F_i += w_i * F_contact
```

拒绝逻辑：

```text
1. 接触点到最近 taxel 距离 > outside_reject_dist → 丢弃该 contact。
2. 某 taxel 的 |d_n| > max_abs_normal_offset → 该 taxel 不参与。
3. 候选 taxel 的 max(w_raw) < min_raw_weight → 丢弃该 contact。
4. 3σ 邻域内没有 taxel → 丢弃该 contact。
```

要求：

```text
1. Renderer 阶段保持合力守恒。
2. 未被 reject 的单个 contact，其 taxel 合力应等于该 contact 力。
3. 饱和、噪声、低通不得放在 Renderer 中。
```

### 10.5 TactileSampler

职责：把 2 kHz 原始触觉流转换为 10 Hz 输出。

```python
class TactileSampler:
    def __init__(self, sim_dt=0.0005, tactile_hz=10, shape=(1140, 3)):
        exact = 1.0 / (tactile_hz * sim_dt)
        self.substeps = int(round(exact))
        if abs(exact - self.substeps) > 1e-9:
            raise ValueError("sim_dt must be integer-aligned with tactile_hz")
        self.reset()

    def reset(self):
        self.acc = np.zeros((1140, 3), dtype=np.float64)
        self.count = 0
        self.frame_idx = 0

    def push(self, raw_sensor_N):
        self.acc += raw_sensor_N
        self.count += 1
        if self.count < self.substeps:
            return None, None
        avg = (self.acc / self.substeps).astype(np.float32)
        t_end = (self.frame_idx + 1) / 10.0
        self.acc[...] = 0.0
        self.count = 0
        self.frame_idx += 1
        return avg, t_end
```

验收：

```text
1. sim_dt = 0.0005, tactile_hz = 10 → substeps = 200。
2. 10 秒 episode → 100 帧。
3. 最后一帧时间戳为 10.0 秒。
4. 每个 episode 开始必须 reset sampler。
```

### 10.6 SensorResponse

职责：把传感器物理轴下的平均力转换成 SDK 对齐输出。

处理顺序：

```text
1. 传感器物理轴 → SDK 轴：F_sdk = M_sdk_sensor @ F_sensor
2. 增益 / 交叉轴 / 偏置：F = A_matrix @ F_sdk + bias
3. 可选低通：state += alpha * (F - state)，tau_s 默认 0
4. 加性高斯噪声：F += N(0, noise_std_N)
5. 饱和：Fx/Fy ∈ [-10,10] N，Fz ∈ [0,25] N
6. SDK-like 数值：detail_sdk = detail_N * lsb_per_N
```

要求：

```text
1. `detail_N` 必须保存，不能只保存 `detail_sdk`。
2. 10 Hz 输出下 `tau_s` 默认 0。
3. 所有随机噪声必须使用可复现 RNG seed。
4. 每个 episode 开始必须 reset response state。
```

### 10.7 DatasetWriter

职责：把每个 episode 写成 HDF5。

推荐 schema：

```text
/episode_{k}/meta/time                         float64 [T]
/episode_{k}/tactile/detail_N                  float32 [T,1140,3]
/episode_{k}/tactile/detail_sdk                float32 [T,1140,3]
/episode_{k}/tactile/raw_sensor_axes_N         float32 [T,1140,3]
/episode_{k}/tactile/sum_N                     float32 [T,11,3]
/episode_{k}/tactile/contact_count             int32   [T]
/episode_{k}/tactile/sensor_pose_world         float32 [T,11,7]
/episode_{k}/state/qpos_serial                 float32 [T,16]
/episode_{k}/state/qvel_serial                 float32 [T,16]
/episode_{k}/object/pose_world                 float32 [T,N_obj,7]
/episode_{k}/static/sensor_table               string/json
/episode_{k}/static/joint_names_serial         string/json
/episode_{k}/static/config_snapshot            string/yaml
```

要求：

```text
1. T = episode_seconds × 10。
2. 10 秒 episode 应有 T = 100。
3. 必须保存 config snapshot，便于复现实验。
4. 必须保存 sensor_pose_world，便于后续训练使用姿态条件。
```

---

## 11. 数据采集主循环

```python
sampler.reset()
response.reset()
writer.start_episode()

while not done:
    apply_control(model, data, action)
    mujoco.mj_step(model, data)

    contacts = read_contacts(
        model,
        data,
        mount,
        geom_to_sensor,
        force_on_geom1=cal["global"]["force_on_geom1"],
    )

    raw_sensor_N = render_contacts(contacts, mount, kdtrees, cal)
    avg_sensor_N, t_end = sampler.push(raw_sensor_N)

    if avg_sensor_N is None:
        continue

    detail_N, detail_sdk = response.step(avg_sensor_N, dt=1.0 / cal["global"]["tactile_hz"])

    writer.write_frame({
        "time": t_end,
        "raw_sensor_axes_N": avg_sensor_N,
        "detail_N": detail_N,
        "detail_sdk": detail_sdk,
        "sum_N": compute_sensor_sum(detail_N, SENSOR_TABLE),
        "contact_count": len(contacts),
        "sensor_pose_world": get_all_sensor_poses(mount, data),
        "qpos_serial": get_qpos_serial(data),
        "qvel_serial": get_qvel_serial(data),
        "object_pose_world": get_object_pose(data),
    })

writer.close_episode()
```

---

## 12. Touch Grid 的定位

Touch Grid 只能作为：

```text
1. baseline；
2. 可视化辅助；
3. 消融对照。
```

正式数据集输出必须使用自写 Contact-to-Taxel Renderer。

原因：

```text
1. DexH13 输出是官方 1140 个非规则 3D taxel 点。
2. Touch Grid 是规则 pixel-like grid。
3. Touch Grid 不能天然对齐曲面 taxel 布局和真实 SDK 顺序。
4. 原生 touch sensor 通常只输出标量法向力，不能满足三轴阵列触觉需求。
```

---

## 13. 标定方案

### 13.1 必须标定的参数

第一版标定：

```text
1. force_on_geom1：确认 MuJoCo contact force 方向。
2. M_sdk_sensor：确认 sensor 轴到 SDK 轴的旋转。
3. sigma_t0 / sigma_n0：确认 RBF 扩散范围。
4. A_matrix 主对角：确认三轴增益。
5. bias_N：确认零点偏置。
6. noise_std_N：确认噪声水平。
7. lsb_per_N：确认 SDK-like 数值换算。
```

第二版再考虑：

```text
1. A_matrix 非对角项。
2. sigma 随接触力变化。
3. 每个 taxel 的局部增益差异。
4. 更精确的 PIP/DIP 真实耦合。
```

### 13.2 标定实验

最低要求：

```text
1. 对 5 类 template 分别做单点压入。
2. 每类至少选择中心点和边缘点。
3. 记录真实 SDK 输出和仿真输出。
4. 拟合 calibration.yaml。
```

损失函数建议：

```text
loss = MSE(detail_sim_N, detail_real_N)
     + λ1 * MSE(sum_sim_N, sum_real_N)
     + λ2 * MSE(center_of_pressure_sim, center_of_pressure_real)
```

---

## 14. 测试与验收

### M0：taxel 数量测试

```text
目标：确认 5 类 template 行数正确，整手总数为 1140。
通过条件：所有 template 行数正确，SENSOR_TABLE 切片无重叠且覆盖 0:1140。
```

### M1：site 对齐测试

```text
目标：确认 1140 个 taxel 投到 world 后覆盖在 11 个 tactile geom 表面。
通过条件：可视化无明显错位，点云不漂浮、不穿入错误 link。
```

### M2：contact 符号测试

```text
目标：确认 force_on_geom1 和 Fz 方向正确。
方法：用球或平面单点压入 5 类传感器。
通过条件：按压时主要法向通道为正，释放后回到近零。
```

### M3：无接触零输出测试

```text
目标：确认无接触时不会产生虚假触觉。
通过条件：raw_sensor_N 近零；detail_N 只包含 bias/noise。
```

### M4：合力守恒测试

```text
目标：确认 RBF 分配不凭空增减力。
通过条件：未 reject 的单 contact，sum(taxel force) 与 contact force 误差 < 1e-5。
```

### M5：outside reject 测试

```text
目标：确认远离传感器表面的 contact 不会被错误分配。
通过条件：超出 outside_reject_dist 的 contact 输出为 0。
```

### M6：10 Hz 采样器测试

```text
目标：确认 2 kHz 到 10 Hz 的帧率转换正确。
通过条件：sim_dt=0.0005 时 substeps=200；10 秒输出 100 帧。
```

### M7：HDF5 schema 测试

```text
目标：确认数据集字段、shape、dtype 正确。
通过条件：所有必需字段存在，shape 与 dtype 与本方案一致。
```

### M8：真机对照测试

```text
目标：确认仿真触觉数值与真机同类实验接近。
通过条件：单点压入下合力误差 < 20%，激活中心位置误差 < 2 mm。
```

---

## 15. 实现顺序

| Step | 任务 | 完成判据 |
|---|---|---|
| 1 | 整理 5 个 taxel CSV | M0 通过 |
| 2 | 从官方 URDF/mesh 生成 DexH13 MJCF | viewer 可加载，关节可动 |
| 3 | 添加 11 个 tactile geom 和 11 个 sensor site | M1 可视化通过 |
| 4 | 实现 `SensorMount` | 能读取 11 个 site 位姿 |
| 5 | 实现 `ContactReader` | 单 contact 测试通过 |
| 6 | 实现 `TactileRenderer` | M4/M5 通过 |
| 7 | 实现 `TactileSampler` | M6 通过 |
| 8 | 实现 `SensorResponse` | 轴变换、饱和、噪声测试通过 |
| 9 | 实现 `DatasetWriter` | M7 通过 |
| 10 | 实现 `run_press_test.py` | M2 通过 |
| 11 | 实现 `run_collection.py` | 可生成 10 Hz HDF5 |
| 12 | 真机标定 | M8 通过 |
| 13 | 大规模采集 | 输出稳定数据集 |

---

## 16. Agent 禁止事项

```text
1. 禁止把 1140 个 taxel 建成 1140 个 collision geom。
2. 禁止把 Touch Grid 作为正式输出。
3. 禁止在多个模块同时翻转力符号。
4. 禁止丢弃 detail_N，只保存 detail_sdk。
5. 禁止不保存 raw_sensor_N。
6. 禁止不保存 sensor_pose_world。
7. 禁止 episode 间不 reset sampler/response。
8. 禁止忽略 contact.exclude 和 contact.efc_address。
9. 禁止将 80 Hz 写入正式方案。
10. 禁止在没有真实标定前声称仿真触觉与真实完全一致。
```

---

## 17. 缺失信息时的处理规则

### 17.1 缺官方 taxel 坐标

```text
停止实现 Renderer。
必须先补齐 5 个 taxel template CSV。
没有官方 3D taxel 坐标，就不能生成 DexH13 对齐的 1140 点触觉数据。
```

### 17.2 缺 sensor site 安装位姿

```text
可以先从 CAD/mesh 粗配准。
但必须通过 M1 可视化检查。
M1 未通过前，禁止采集训练数据。
```

### 17.3 不确定 SDK 轴方向

```text
先设置 M_sdk_sensor = I。
后续用真实按压数据标定。
不要凭经验猜轴方向。
```

### 17.4 不确定 contact force 符号

```text
只允许通过 force_on_geom1 一个开关修正。
通过 M2 后固定。
不要在 Renderer 或 Response 中额外翻转。
```

---

## 18. 最小可运行版本定义

实现到以下程度，才算 MVP 完成：

```text
1. 能加载 DexH13 MJCF。
2. 能在 11 个 tactile geom 上产生接触。
3. 能输出 raw_sensor_N [1140,3]。
4. 能输出 detail_N/detail_sdk [1140,3]。
5. 能以 10 Hz 写入 HDF5。
6. 10 秒 episode 输出 100 帧。
7. M0~M7 全部通过。
```

MVP 完成后，才能进入真实标定和大规模数据采集。

---

## 19. 最终交付物

最终必须提交：

```text
1. dexh13_mujoco_tactile/ 完整代码仓库。
2. assets/dexh13_mjcf/hand.xml。
3. assets/dexh13_mjcf/tactile_geoms.xml。
4. configs/taxel_templates/*.csv。
5. configs/sensors.yaml。
6. configs/calibration.yaml。
7. configs/sim.yaml。
8. tests/ 全部通过的日志。
9. 至少一个 test_press_scene 的 HDF5 示例文件。
10. 至少一个 grasp/press 数据采集 HDF5 示例文件。
11. README.md，说明如何运行：
    - 安装环境
    - pytest
    - 单点压入测试
    - 采集一个 episode
    - 可视化 1140 点触觉
```

---

## 20. 一句话总结

本工程不是让 MuJoCo 原生 sensor 直接输出 DexH13 触觉，而是：

```text
用 MuJoCo 计算接触力，
用官方 3D taxel 坐标定义 1140 个输出点，
用可标定的 RBF + PX-6AX 响应模型生成与真实 SDK 同构的 10 Hz 阵列触觉数据。
```
