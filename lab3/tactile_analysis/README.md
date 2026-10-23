# DexH13 触觉数据命令行分析

[English README](README.en.md)

本项目只保留命令行工具。可以直接分析采集 ZIP、解压后的轨迹目录和 HDF5，也可以把整条轨迹转换为 HDF5 存档。分析结果保存为 JSON、CSV、PNG，可选导出 MATLAB `.mat`。

**对目前这批真实数据，可以做原始信号诊断，不能直接报告真实压力或接触面积。** 原因是有效点 mask 全为 false，力标定、法向和点面积尚未核验。HDF5 转换不会补齐这些信息。本说明同时提供现在可运行的 raw 分析，以及标定完成后可运行的面积/压力分析；两者使用同一个 CLI。

## 目录

1. [能力与前提](#1-能力与前提)
2. [安装和工作目录](#2-安装和工作目录)
3. [导入 ZIP：先跑通一次](#3-导入-zip先跑通一次)
4. [可选：转换为 HDF5](#4-可选转换为-hdf5)
5. [具体分析操作](#5-具体分析操作)
6. [raw 输出如何解读](#6-raw-输出如何解读)
7. [接触面积和压力的计算条件与公式](#7-接触面积和压力的计算条件与公式)
8. [完整跑通一个面积与压力模拟示例](#8-完整跑通一个面积与压力模拟示例)
9. [为真实硬件准备标定文件](#9-为真实硬件准备标定文件)
10. [参数、Python API 和常见错误](#10-参数python-api-和常见错误)
11. [项目文件与验证](#11-项目文件与验证)

## 1. 能力与前提

| 想分析的内容 | 当前真实 ZIP 能否分析 | 方法或缺少的条件 |
| --- | --- | --- |
| 每点 x/y/z 原值 | 可以读取 | 有符号 SDK counts，未换算单位 |
| 三轴模长、峰值、超阈值点数 | 可以诊断 | 使用 `--allow-unverified`，单位为 raw |
| 信号变化、候选响应时段 | 可以诊断 | 不自动判定“真实接触”或抓取阶段 |
| taxel 编号热力图 | 可以 | 编号不是手指表面坐标 |
| 11 组 SDK 汇总、温度 | 可以 | 汇总使用 raw；温度使用事件中的 °C |
| 采样率和有效性 | 可以 | 检查帧数、时间戳、包状态和 mask |
| 接触面积估计 mm² | 当前不可以 | 已验证点、接触判据及每点有效面积 |
| 法向力 N、压力 Pa/kPa | 当前不可以 | 再加实际力标定和压缩法向；使用标定模式 |
| 真实手指表面空间分布 | 当前不可以 | 编号到几何位置的验证；本版不是 3D 手部渲染器 |
| 滑移检测、抓取稳定性评分 | 未实现 | 当前不提供这类判定 |

这批记录的已知情况：左手 407 帧、右手 408 帧，约 46.5 s，平均约 8.75 Hz。55 个 NPZ 的哈希与 manifest 一致，数据包有效率 100%，但已验证 taxel 数和 `sample_valid=true` 的帧数均为 0。`sample_valid=false` 不代表原值全零，也不代表没有接触。

## 2. 安装和工作目录

以下所有命令均从 **`lab3/tactile_analysis` 目录**运行；不要一会儿在仓库根目录、一会儿在模块目录运行同一组相对路径。

### 2.1 macOS / Linux

本机路径：

```bash
cd /Users/alaia/Developer/Pacini_Course/lab3/tactile_analysis
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[cli]'
```

其他机器把 `cd` 后面的路径替换为自己的项目路径。已有 `.venv` 时不必重建，只需激活。`[cli]` 安装 NumPy、h5py、matplotlib，不安装 Qt。

需要 MATLAB 导出时：

```bash
python -m pip install -e '.[all]'
```

`[all]` 额外包含 SciPy。最小 NumPy 安装不足以完成本说明中的绘图和 HDF5 操作。

确认环境：

```bash
python -c "import sys, numpy, h5py, matplotlib; print(sys.executable)"
python examples/analyze_recording.py --help
```

应看到当前 `.venv` 的 Python 路径。Python 要求 3.10 或以上。

### 2.2 Windows

```powershell
cd C:\your\path\Pacini_Course\lab3\tactile_analysis
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[cli]"
```

后面的 `python examples/...` 命令用法相同；Bash 的 `\` 换行、`for` 循环和 `python - <<'PY'` 代码块不适用于 PowerShell。可把长命令写成一行，把 Python 代码块存成 `.py` 再执行。当前实测平台是 macOS，未实测 Windows。

终端帮助、进度、错误和默认结果摘要均使用中文；图表文字和文件中的 JSON/CSV 字段保持原有格式。若其他程序需要读取旧版终端 JSON，请在主分析、整轨迹转换或诊断命令后添加 `--json`。`--quiet` 只关闭进度提示，不关闭结果摘要，也不改变摘要语言。

### 2.3 不想安装本模块

也可以只安装依赖，然后运行 `examples/` 下的入口脚本：

```bash
python -m pip install numpy h5py matplotlib
python examples/analyze_recording.py --help
python examples/convert_recording_to_hdf5.py --help
```

入口脚本会定位本地包，不需要手动设置 `PYTHONPATH`。安装了本模块时，`tactile-analyze` 与 `python examples/analyze_recording.py` 等价，`tactile-convert-recording` 与转换脚本等价。

## 3. 导入 ZIP：先跑通一次

“导入”就是把文件路径作为命令的第一个参数，不需要上传服务、不需要先解压、不要求先转换 HDF5。

本机目录中的 `teleop_20261021T090120_798e4203.zip` 可直接使用。原始采集 ZIP 和分析输出不随 Git 仓库分发；新克隆仓库后，请先准备自己的采集文件。若文件只在外部磁盘，可复制到本地：

```bash
mkdir -p inputs
cp "/Volumes/home/teleop_20261021T090120_798e4203.zip" "inputs/teleop_20261021T090120_798e4203.zip"
```

复制后，把后面命令中的 `./teleop_20261021T090120_798e4203.zip` 换成 `inputs/teleop_20261021T090120_798e4203.zip`。也可以直接使用外部磁盘的完整路径。路径有空格时必须加引号。

### 第一步：只查看内容和质量，不生成分析文件

```bash
python examples/analyze_recording.py \
  "./teleop_20261021T090120_798e4203.zip" \
  --list-trials --quiet
```

上面的命令默认显示中文质量摘要。需要机器可读 JSON 时，请添加 `--json`；其中重点看：

- `verified_npz_count`：本次核对的 NPZ 哈希数量，当前记录为 55。
- `trial`：可选对象，当前是 `left`、`right`。
- `frames`、`rate_hz`：帧数和 `(帧数−1)/时间跨度` 得到的平均频率。
- `packet_valid_fraction`：包有效率。
- `verified_taxels`：整段中曾经被验证的点数，不是非零点数。
- `sample_valid_fraction`：有效帧比例。当前为 0，因此下面明确使用 raw 诊断选项。

### 第二步：直接分析左手

```bash
python examples/analyze_recording.py \
  "./teleop_20261021T090120_798e4203.zip" \
  --trial left \
  --allow-unverified \
  --contact-threshold 10 \
  --output-dir analysis_out/real_left_t10
```

成功后打开 `analysis_out/real_left_t10/overview.png` 或 `taxel_heatmap.png`。`--allow-unverified` 表示允许把未验证条目纳入原始幅值诊断；不会把 mask 改成 true。

阈值 10 的单位是 raw 模长，不是 10 N，也不是已确定的接触阈值。它只是用来演示和初步筛查的起始值。

**输出目录必须是新目录。** 再跑一次请改为 `analysis_out/real_left_t10_run2` 等新名字；分析不会静默覆盖旧结果。

## 4. 可选：转换为 HDF5

需要统一存档、交给其他程序或保留全部流时再转换。转换本身不会标定、归一化、筛掉无效点或同步双手。

```bash
mkdir -p analysis_out
python examples/convert_recording_to_hdf5.py \
  "./teleop_20261021T090120_798e4203.zip" \
  analysis_out/real_recording.h5
```

输入也可以是直接含有 `manifest.json` 的轨迹目录：

```bash
python examples/convert_recording_to_hdf5.py \
  "../data/teleop_20261021T090120_798e4203" \
  analysis_out/real_recording_from_directory.h5
```

明确需要替换现有 HDF5 时添加 `--overwrite`。脚本先完成临时文件及校验，成功后才替换；失败时保留旧文件。

随后分析 HDF5 的命令与 ZIP 相同：

```bash
python examples/analyze_recording.py \
  analysis_out/real_recording.h5 \
  --trial left --allow-unverified --contact-threshold 10 \
  --output-dir analysis_out/from_hdf5_left_t10
```

### 4.1 HDF5 中的内容

| 路径 | 含义 |
| --- | --- |
| `trials/left`、`trials/right` | 按手提供的触觉分析入口，各有自己的帧数与时间轴 |
| `streams/<原流名>` | 全部 manifest 数据流，含手、机械臂、操作员、控制记录 |
| `events/temperature_readings` | 展开的温度事件表，没有插值到触觉帧 |
| `provenance/manifest_json` | manifest 原文 |
| `provenance/events_jsonl` | 完整事件原文，含非温度事件 |
| `provenance/conversion_report_json` | 输入哈希、每块目标行范围、字段核对计数 |

每个手别包含：

| 字段 | 形状 | HDF5 类型 / 单位 |
| --- | --- | --- |
| `taxel_raw` / `detail_xyz` | `[T,1140,3]` | 同一数据集的硬链接，int32，raw counts |
| `sensor_summary_raw` / `sensor_forces` | `[T,11,3]` | 同一数据集的硬链接，int32，SDK 汇总原值 |
| `timestamp_ns` / `tactile_timestamps_ns` | `[T]` | int64，主机单调时钟纳秒 |
| `query_begin_ns` | `[T]` | int64，查询起点 |
| `taxel_valid_mask` | `[T,1140]` | bool，原样保留 |
| `packet_valid`、`sample_valid` | `[T]` | bool，原样保留 |
| `hand_side` | `[T]` | UTF-8 字符串 |

单手采集只生成相应手别。转换器逐个验证所有 manifest NPZ 的哈希、字段、形状、类型、帧数、分块时间和跨块递增；每个字段写入后读回比较。温度、manifest 原文也保留。events 的哈希是转换时计算的追溯值，源 manifest 没有独立 events 哈希。

分析器在内存中使用 float64 计算，但 HDF5 中的原始触觉仍为 int32。相同行号不代表双手、手与机械臂或温度已经同步。

## 5. 具体分析操作

以下示例都使用当前目录下的真实 ZIP。`--output-dir` 每次换成新的目录。

### 5.1 右手或双手

```bash
python examples/analyze_recording.py ./teleop_20261021T090120_798e4203.zip \
  --trial right --allow-unverified --contact-threshold 10 \
  --output-dir analysis_out/real_right_t10

python examples/analyze_recording.py ./teleop_20261021T090120_798e4203.zip \
  --trial all --allow-unverified --contact-threshold 10 \
  --output-dir analysis_out/real_both_t10
```

不传 `--trial` 默认分析全部手别。双手分别计算，不把同一行当同步样本。图中每只手以自己的第一帧为时间 0。

### 5.2 比较阈值敏感性

```bash
for threshold in 5 10 20 50; do
  python examples/analyze_recording.py ./teleop_20261021T090120_798e4203.zip \
    --trial left --allow-unverified --contact-threshold "$threshold" \
    --output-dir "analysis_out/sweep_left_t${threshold}"
done
```

比较各目录的 `trial_01/summary.json` 中 `active_taxel_count_mean`、`active_taxel_count_peak` 和 `contact_fraction`。这些是超阈值统计，不是实际接触面积。应使用明确标记的空载段检查偏置/噪声，再确定实验阈值；不能未经确认就把录制开始的几秒当作空载。

### 5.3 平滑、指定帧和空间布局

```bash
python examples/analyze_recording.py ./teleop_20261021T090120_798e4203.zip \
  --trial left --allow-unverified --contact-threshold 10 \
  --smooth-window 5 --heatmap-frame 100 \
  --output-dir analysis_out/left_smooth5_frame100
```

平滑作用于各点的三轴模长；窗口必须为正奇数，1 表示不平滑，边缘采用端点填充。此例额外生成第 100 帧快照，帧号从 0 开始。平滑会改变峰值和阈值穿越时刻，不是传感器标定。

已有经过验证的布局时，可以加 `--taxel-positions calibration_results/left_layout.npy`。数组形状为 `[1140,2]` 或 `[1140,3]`，必须匹配同一只手的 SDK 顺序。规则二维网格可用于 max/mean 图；不规则布局回退到编号图，三维数组只取前两列，不会生成 3D 手指图。没有布局不影响读取或编号热力图。

### 5.4 读取某个点的有符号三轴原值

```bash
python - <<'PY'
import numpy as np
from tactile_analysis.recording import load_recording

r = load_recording("./teleop_20261021T090120_798e4203.zip")
t = r.trials["left"]
point = 100  # 从 0 开始，范围 0..1139
time_s = (t.timestamps_ns - t.timestamps_ns[0]) / 1e9
np.savetxt("analysis_out/left_taxel100_xyz.csv",
           np.column_stack([time_s, t.detail_xyz[:, point, :]]), delimiter=",",
           header="time_s,x_raw,y_raw,z_raw", comments="",
           fmt=["%.9f", "%d", "%d", "%d"])
print(t.detail_xyz[0, point], "mask:", t.taxel_valid_mask[0, point])
PY
```

前面的分析步骤已创建 `analysis_out`。x/y/z 是 SDK 分量，不能未经验证就把 z 当成法向，也不能把点 100 当作某根手指上的已知位置。

### 5.5 查看温度、传感器汇总和采样质量

运行 5.1 的双手命令后：

- `sensor_summary.png`：11 组 SDK 汇总向量的模长随时间变化；不把汇总再加到逐点统计上。
- `temperature.png`：按手别、sensor_id 显示事件温度。
- `temperature_events.csv`：选中手别的独立温度事件读数，保留事件次序和时间戳。
- `report.json` 的 `temperature_summary`：每手读数数量、最低、最高和均值。
- `report.json` 的 `data_quality`：帧数、时长、平均采样率及有效性。

温度表可能全局乱序；需要关联时按手别与时间戳处理。没有擅自前向填充或逐帧插值。读取温度汇总：

```bash
python - <<'PY'
import json
p = "analysis_out/real_both_t10/report.json"
r = json.load(open(p, encoding="utf-8"))
print(r["data_quality"])
print(r["temperature_summary"])
PY
```

### 5.6 导出 MATLAB

```bash
python examples/analyze_recording.py ./teleop_20261021T090120_798e4203.zip \
  --trial left --allow-unverified --contact-threshold 10 --export-mat \
  --output-dir analysis_out/real_left_mat
```

每个 trial 子目录增加 `analysis.mat`。MATLAB 示例：

```matlab
s = load('analysis_out/real_left_mat/trial_01/analysis.mat');
plot(s.time_s, s.active_taxel_count);
xlabel('Time (s)'); ylabel('Taxels above raw threshold');
```

### 5.7 更细的原始信号审计（可选）

已有解压目录时，保留的审计脚本还可统计全零帧、重复帧、三轴范围、字节边界值和阈值敏感性：

```bash
python examples/audit_recording.py \
  ../data/teleop_20261021T090120_798e4203 \
  --output-dir analysis_out/audit_real
```

此脚本只接受轨迹目录；只有 ZIP 时可以直接用前面主 CLI，无需运行本节。字节边界值不是自动的饱和诊断；全零或重复值也不能直接判定坏点。

## 6. raw 输出如何解读

```text
analysis_out/real_both_t10/
├── report.json
├── overview.png
├── taxel_heatmap.png
├── sensor_summary.png
├── temperature.png
├── temperature_events.csv
├── trial_01/
│   ├── summary.json
│   ├── frame_metrics.csv
│   ├── heatmap_max.png
│   ├── heatmap_mean.png
│   └── analysis.mat             # 仅 --export-mat
└── trial_02/                    # 双手时
```

先读 `report.json` 的 `trial_folders`，确认哪个子目录对应 left/right；不要仅凭文件夹序号猜手别。每个 `summary.json` 外层是 `summary` 与 `metadata`。

设每点原值为 `(x_i,y_i,z_i)`，模长 `q_i=sqrt(x_i²+y_i²+z_i²)`；平滑开启时，下面使用平滑后的 `q_i`。

| CSV / summary 名称 | raw 模式的实际含义 |
| --- | --- |
| `time_s` | 相对该手第一帧的主机时间；无时间戳旧文件则为帧索引 |
| `active_taxel_count` | `q_i >= threshold` 的点数 |
| `total_contact_force` | 超阈值点的 `q_i` 之和；单位 raw，不是合力 |
| `peak_taxel_force` | 全部点的最大 `q_i`，不受阈值过滤 |
| `mean_contact_force` | 超阈值点模长的算术均值；无超阈值点时为 0 |
| `sensor_total_force` / `sensor_peak_force` | SDK 汇总向量模长的和 / 最大值，单位 raw |
| `contact_fraction` | 全部点帧中超阈值的比例，不是有接触帧的比例 |
| `force_impulse` | 超阈值模长和对时间的梯形积分，raw·s，不是 N·s |
| `contact_duration_s` | 有超阈值点的区间时长近似，采用右端点帧状态 |
| `contact_area_mm2_*` | 未提供可用面积时为 null；当前真实 raw 诊断不输出物理面积 |
| `mean_pressure*` | 当前真实 raw 诊断中无此物理压力结果 |

旧 HDF5 若完全缺少有效性字段，raw 沿用兼容行为：能运行不等于验证通过。物理模式仍要求源数据具备完整的质量字段。

`force`、`contact` 是保留的历史键名。当前数据的 `analysis_mode` 为 `unverified_raw_diagnostic`，必须按原始幅值 / 超阈值统计理解。raw 模式包括未验证项，适合检查采集信号，不用于宣布接触为真。

`heatmap_max.png` 是每个点在整段内各自的最大值，未必同时发生；`heatmap_mean.png` 是逐点帧平均；`taxel_heatmap.png` 是时间×编号图。raw 模式的统计均值按帧计算，不按时间间隔加权；只有时长和积分使用时间戳。旧 HDF5 若缺少时间戳，摘要的 `time_source=frame_index`，时间相关旧键不能解释为真实秒或物理冲量。

## 7. 接触面积和压力的计算条件与公式

### 7.1 为什么当前数据不能直接算

不能把 1140 乘一个猜测面积当真实接触面积，不能把 raw 乘 SDK 声称的 0.1 就当完成力标定，也不能用三轴模长除以面积替代法向压力。当前 mask 全 false，物理模式会拒绝运行；`--allow-unverified` 只能用于 raw 诊断，不能绕过物理模式校验。

### 7.2 标定模式实际计算什么

对每个点，线性/仿射标定为：

```text
F_i [N] = M_i [N/count] @ (raw_i - bias_i [count])
Fn_i = max(dot(F_i, normal_i), 0)
valid_i = source_taxel_mask_i AND calibration_verified_mask_i
          AND packet_valid AND sample_valid
contact_i = valid_i AND (Fn_i >= normal_threshold_n)
```

`normal_i` 必须是标定后的力坐标系中的单位法向，并约定受压为正。负法向分量按不受压处理。不是默认取 z，也不是先取三轴模长。

```text
接触面积估计 A [mm²] = Σ contact_i * A_i
法向力标量和 Fn_sum [N] = Σ contact_i * Fn_i
逐点压力 p_i [Pa] = Fn_i / A_i[mm²] * 1,000,000（接触点）
平均接触压力 p_mean [Pa] = Fn_sum / A * 1,000,000
p [kPa] = p [Pa] / 1,000
```

这是基于已验证点和阈值的**离散接触面积估计**。每个激活点按完整 `A_i` 计入，不估计点内部的部分接触。未验证区域不在统计范围内，因此不能宣称得到整只手的完整接触面积。已知点面积即可求和，不强制要求点坐标；空间展示才需要布局。

面积不相等时，平均压力是面积加权平均，不是各点压力的简单平均。法向力标量和、切向力模长和均不是公共世界坐标系下的合力。切向模长由 `sqrt(||F_i||² - dot(F_i,normal_i)²)` 计算，并只在选定接触点上求和。

### 7.3 无接触、无效帧和时间统计

- 有效帧但没有点超过法向阈值：面积、力和计数为 0，平均/峰值接触压力为 NaN（JSON 摘要为 null），避免把 `0/0` 当压力 0。
- 没有任何有效点的帧：保持原时间戳，物理指标为 NaN；不会作为“无接触”或有效 0 参与均值。
- 整段没有有效点：报错，不生成一份全零压力报告。
- 压力均值只对存在接触压力的帧求均值；面积和力均值包括有效的无接触帧，均为帧平均。
- 接触时长按相邻有效帧的右端点状态近似；冲量采用梯形法。无效帧两侧不跨越积分。采样频率有限，阈值时段不等于精确接触起止。

## 8. 完整跑通一个面积与压力模拟示例

下面是 **4 个点、3 帧的数学示例**，不是 DexH13 实验结果。示例标定标记为 `synthetic_demo`，程序拒绝将其用于真实记录。

```bash
python examples/make_physical_demo.py analysis_out/physical_demo_input

python examples/analyze_recording.py \
  analysis_out/physical_demo_input/synthetic_trial.h5 \
  --trial left \
  --calibration analysis_out/physical_demo_input/synthetic_calibration.npz \
  --normal-threshold-n 0.1 \
  --output-dir analysis_out/physical_demo_result
```

生成的两个输入文件以及结果目录默认不覆盖已有文件；重复运行请改目录名。

示例只有点 0、1、3 有效；点 2 即便原值很大也必须被排除。每个有效点面积人为设为 2 mm²，标定矩阵人为设为 `0.1*I`，正 z 为受压方向。这些值仅用于算术验证，不能复制到真实硬件标定。

| 帧号（从 0 开始） | 有效接触点数 | 面积 mm² | 法向力标量和 N | 平均压力 kPa | 单点峰值压力 kPa |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 | 0 | 0 | 0 | NaN | NaN |
| 1 | 2 | 4 | 3 | 750 | 1000 |
| 2 | 3 | 6 | 6 | 1000 | 1500 |

例如第 1 帧 `3 N / 4 mm² = 750000 Pa = 750 kPa`。

```bash
python - <<'PY'
import csv, json
root = "analysis_out/physical_demo_result"
summary = json.load(open(root + "/summary.json", encoding="utf-8"))["summary"]
print("峰值面积 mm²:", summary["contact_area_mm2_peak"])  # 6
print("峰值局部压力 Pa:", summary["peak_pressure_pa"])    # 1500000
with open(root + "/frame_metrics.csv", newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        print(row["time_s"], row["contact_area_mm2"], row["mean_pressure_kpa"])
PY
```

物理模式输出：

```text
physical_demo_result/
├── summary.json
├── frame_metrics.csv
├── physical_arrays.npz
├── physical_overview.png
├── pressure_heatmap.png
└── analysis.mat                 # 仅 --export-mat
```

物理 CSV 的关键列如下；所有面积、力和压力都是有效范围内的统计：

| 列名 | 含义 |
| --- | --- |
| `time_s` | 相对该手第一帧的秒数 |
| `sample_valid` | 源质量字段与标定 mask 取交集后，该帧是否仍有有效点 |
| `verified_taxel_count` | 该帧实际参与分析的有效点数；比较不同帧时应检查覆盖范围是否变化 |
| `active_taxel_count` | 达到法向阈值的有效点数 |
| `contact_area_mm2` | 接触点面积之和，离散估计 |
| `normal_force_sum_n` | 接触点压缩法向力的标量和 |
| `peak_taxel_normal_force_n` | 接触点中最大的单点法向力 |
| `tangential_magnitude_sum_n` | 接触点切向力模长之和，不是世界坐标合力 |
| `mean_pressure_pa` / `mean_pressure_kpa` | 该帧面积加权的平均接触压力 |
| `peak_pressure_pa` / `peak_pressure_kpa` | 该帧接触点中的最高局部压力 |

摘要中的 `normal_force_impulse_n_s` 单位为 N·s；`mean_pressure_pa_mean` 是存在接触压力的有效帧平均。NaN 在 CSV 中保留为 `nan`，摘要中没有可定义压力时为 JSON null。

`physical_arrays.npz` 包含 `force_vector_n[T,N,3]`、`normal_force_n[T,N]`、`pressure_pa[T,N]`、`contact_mask`、`effective_valid_mask`、`time_s`。无效点为 NaN；有效但未被选为接触的点，接触压力图中为 0。

## 9. 为真实硬件准备标定文件

### 9.1 需要实际完成的工作

1. 核验采集 mask，确认哪些点启用且可靠；将核验结果配置到采集端，并采集带正确逐帧状态的新记录。分析工具不会把历史 false 改成 true。
2. 使用明确的无接触状态测量三轴零偏，得到 `bias_counts`。
3. 施加已知方向与大小的参考载荷，拟合 raw 到 N 的矩阵，验证适用量程、线性近似及重复性。本版只支持仿射模型，不拟合非线性或滞回。
4. 核验各点力坐标系和压缩正方向，得到单位 `normal_vectors`。
5. 通过敏感区域几何或实际测量得到 `taxel_area_mm2`；不要仅由点总数猜面积。
6. 确保所有标定数组与该手当前 SDK 点顺序一致。维度匹配只说明结构正确，不证明空间映射正确。

### 9.2 标定 NPZ 的完整字段

读取使用 `allow_pickle=False`。左右手各自准备文件，一次物理分析使用一个手别的标定。

| 字段 | 形状 / 类型 | 含义 |
| --- | --- | --- |
| `schema_version` | 整数标量，1 | 标定文件版本 |
| `hand_side` | 字符串标量 | `left` 或 `right`，必须匹配输入 |
| `source_kind` | 字符串标量 | 真实实验填 `measured`；模拟示例填 `synthetic_demo` |
| `calibration_id` | 非空字符串标量 | 可追溯的标定编号 |
| `force_matrix_n_per_count` | `[3,3]` 或 `[N,3,3]` | 共用或逐点标定矩阵，N/count |
| `bias_counts` | `[3]` 或 `[N,3]` | 共用或逐点 raw 零偏 |
| `normal_vectors` | `[3]` 或 `[N,3]` | 标定力坐标系中的单位压缩法向 |
| `taxel_area_mm2` | 正标量或 `[N]` | 各点有效面积，mm² |
| `verified_taxel_mask` | bool `[N]` | 标定时确认可用的点，与源 mask 取交集 |

数值必须有限，面积必须大于 0，法向长度必须为 1。不能靠标记 `measured` 完成物理验证；程序只验证结构和这些数值条件。保存文件和矩阵对应的实际标定报告。

下面只打包**已经测得的结果文件**，不会生成未知标定值。先在 `calibration_results/` 放好自己的 `.npy` 文件：

```bash
python - <<'PY'
from pathlib import Path
import numpy as np
p = Path("calibration_results")
np.savez_compressed(
    p / "left_measured.npz",
    schema_version=np.array(1), hand_side=np.array("left"),
    source_kind=np.array("measured"), calibration_id=np.array("replace-with-your-measured-calibration-id"),
    force_matrix_n_per_count=np.load(p / "left_force_matrix_n_per_count.npy", allow_pickle=False),
    bias_counts=np.load(p / "left_bias_counts.npy", allow_pickle=False),
    normal_vectors=np.load(p / "left_normal_vectors.npy", allow_pickle=False),
    taxel_area_mm2=np.load(p / "left_taxel_area_mm2.npy", allow_pickle=False),
    verified_taxel_mask=np.load(p / "left_verified_taxel_mask.npy", allow_pickle=False),
)
PY
```

没有这些实测文件时，本段不能运行；请先运行第 8 节的模拟例子熟悉流程。

### 9.3 对完成核验的新记录分析

下面的 `verified_trial.h5`、`left_measured.npz` 是你将来实际准备的文件，不是当前全 false mask 记录的别名：

```bash
python examples/analyze_recording.py verified_trial.h5 \
  --trial left \
  --calibration calibration_results/left_measured.npz \
  --normal-threshold-n 0.1 \
  --output-dir analysis_out/verified_left_pressure
```

法向阈值 0.1 N 仍是用法示例，应按标定噪声、分辨率和实验判据确定。不要附带 `--allow-unverified`、raw 阈值、raw 平滑或 `--taxel-area-mm2`；物理模式使用标定文件里的面积。右手换成 `--trial right`、右手标定文件和新输出目录。

物理模式允许部分有效 taxel / 帧，按 mask 取交集并保留缺失标记；这与 raw 默认的“所有已提供质量字段完全有效才允许统计”策略不同。加载标定文件不会覆盖源 mask，不会因原值非零而自动认定点有效。

## 10. 参数、Python API 和常见错误

### 10.1 主分析参数

| 参数 | 默认 / 用法 |
| --- | --- |
| `input` | 第一个位置参数：ZIP、轨迹目录、HDF5 |
| `--trial` | 默认 `all`；支持 `left`、`right` 或实际 HDF5 trial 名 |
| `--list-trials` | 只检查 / 列出数据，不运行分析 |
| `--output-dir` | 默认 `analysis_out`，要求不存在，建议总是显式指定 |
| `--allow-unverified` | 默认关闭；只允许 raw 诊断纳入未验证项 |
| `--contact-threshold` | raw 默认 10，判断模长是否大于等于阈值 |
| `--smooth-window` | raw 默认 1，正奇数 |
| `--heatmap-frame` | `max` / `mean` / 非负帧号；max 和 mean 图始终输出，数值时加一张快照 |
| `--taxel-positions` | 可选 `.npy` 布局，raw max/mean/快照图使用 |
| `--taxel-area-mm2` | 旧的常面积代理选项，要求 raw 质量完全有效；不用于真实压力流程 |
| `--force-unit` | CLI 只接受 `raw`；写 `N` 不会自动换算，物理量请用标定模式 |
| `--calibration` | 单手标定 NPZ，启用物理模式 |
| `--normal-threshold-n` | 物理模式默认 0.1 N，必须为有限正数 |
| `--export-mat` | 两种模式均可，需 SciPy |
| `--quiet` | 关闭 stderr 进度，stdout 保留中文结果摘要（与 `--json` 同用时保留结果 JSON） |
| `--json` | 显式使用旧版机器可读 JSON 结果，字段名和结构不变；默认中文摘要 |

旧的 `--taxel-area-mm2` 将超阈值点按相同面积求和，`mean_pressure` 是模长和/面积的代理，可能只有 raw/mm² 单位。即使提供面积，也不能把它当法向压力。当前未验证真实数据会拒绝这一选项。推荐使用第 7–9 节有明确法向、力标定和有效点范围的流程。

### 10.2 Python API

```python
from tactile_analysis import AnalysisConfig, analyze_trial
from tactile_analysis.recording import load_recording
from tactile_analysis.physical import analyze_physical, export_physical

recording = load_recording("./teleop_20261021T090120_798e4203.zip")
raw = analyze_trial(recording.trials["left"], AnalysisConfig(
    contact_threshold=10, allow_unverified=True, smooth_window=1))
print(raw.summary)
# 以下只在你已经有真实标定与有效源数据时运行：
# physical = analyze_physical(verified_trial, "calibration_results/left_measured.npz", normal_threshold_n=.1)
# export_physical(physical, "analysis_out/verified_pressure_api")
```

既有 HDF5 API `load_hdf5(path, trial="left")`、`analyze_hdf5(...)` 仍保留。主 CLI 的多手报告输出结构见第 6 节；旧 `analyze_hdf5(output_dir=...)` API 在指定目录直接写单 trial 文件，不会生成主 CLI 的多手报告树。

### 10.3 常见错误

| 现象 | 处理 |
| --- | --- |
| `No module named ...` | 激活正确 `.venv`，执行 `pip install -e '.[cli]'`；MAT 再装 `[all]` |
| 找不到 ZIP / manifest | 检查 `pwd`、完整路径和引号；目录必须直接含 manifest，不是其上一级 |
| `SHA-256 哈希校验不一致` | 文件与 manifest 不一致，重新复制并检查采集记录；不要仅改哈希来跳过问题 |
| `数据组包含无效或未验证的样本、触觉点` | 当前 raw 诊断加 `--allow-unverified`；物理模式不能用此选项绕过 |
| `没有可用的已验证触觉点` | 核验采集 mask 和标定 mask；当前这份全 false 记录不具备物理分析条件 |
| `输出已存在` | 为分析选一个新输出目录；HDF5 转换可明确用 `--overwrite` |
| `未知数据组` | 先运行 `--list-trials`，使用输出中的名字 |
| `hand_side 与所选数据组的手别不一致` | 使用该手正确的标定文件 |
| `合成示例标定不能用于真实采集记录` | 模拟标定不能套在真实数据上；需要实测文件 |
| 平滑窗口报错 | 使用 1、3、5 等正奇数 |
| 帧号越界 | 0..T−1 是有效范围；407 帧左手的最后一帧为 406 |
| 压力是 `nan` / null | 区分无效帧、无接触帧；不能全部替换成 0 |
| 热力图是一条长条 | 未提供规则空间布局，这是编号图，不是读取失败 |
| Matplotlib 缓存目录不可写 | 可设 `MPLCONFIGDIR="$PWD/.mpl-cache"`；与数据数值无关 |

均值默认不是按时间加权。相邻 raw 帧用于积分，不会自动删除大时间间隔或判断设备丢帧。主机查询完成时间不等于硬件采样时间，不要按相同行号同步左右手或机械臂。

## 11. 项目文件与验证

```text
examples/analyze_recording.py            主分析入口
examples/convert_recording_to_hdf5.py    整条轨迹转换
examples/make_physical_demo.py           可运行的模拟面积 / 压力示例
examples/audit_recording.py              已解压目录的详细审计
examples/convert_npz_to_hdf5.py          早期单 NPZ 的辅助转换，不代替整条轨迹转换
examples/make_demo_hdf5.py               早期 raw 信号示例，不包含真实硬件标定

tactile_analysis/recording.py            ZIP / 目录 / HDF5 读取
tactile_analysis/report.py              raw 报告与图表
tactile_analysis/physical.py            法向力、面积、压力及物理报告
tactile_analysis/convert_recording.py   无损转换与完整性检查
tactile_analysis/terminal.py            中文帮助、错误与终端结果摘要
```

运行测试：

```bash
python -m unittest discover -s tests -v
```

测试包括分块与字符串无损转换、哈希损坏拒绝、ZIP/目录/HDF5 数值等价、raw 有效性与 CLI 输出、已知面积/压力算术、非 z 法向、逐点标定、不同点面积的加权平均、无效帧和 mask 不提升、模拟标定不能用于真实数据等。另有中文帮助、参数报错、质量/分析/转换摘要和 `--json` 兼容性检查；当前共 39 项。

实际记录的原始诊断见 [REPORT.zh-CN.md](reports/teleop_20261021T090120_798e4203/REPORT.zh-CN.md)，它记录当时的检查结果，当前入口和命令以本 README 为准。压力单位定义参考 [NIST 的 SI 单位表](https://www.nist.gov/pml/special-publication-330/sp-330-appendix-1)：Pa = N/m²，因此 N/mm² 转成 Pa 乘以 10⁶。

本地实跑验证产物归档在 `analysis_out/readme_validation/`，教程中的主要输出路径已留给你首次执行时创建。验证归档中的来源路径是生成时的历史路径，移动记录见 `relocations.json`。
