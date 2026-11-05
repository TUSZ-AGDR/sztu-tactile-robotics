# Lab 4 slides · 一枚传感器，两个世界

[中文幻灯片](index.html) · [English slides](index.en.html) · [中文讲稿](SPEAKER_NOTES.zh-CN.md) · [English speaker notes](SPEAKER_NOTES.en.md)

英文扩展版共 **25 页**，约 30 分钟，增加 MLP、神经元计算、训练过程以及引入 latent space 的动机和局限。第 9 页可调节神经元输入，第 14 页可调节示意曲线的幅度和宽度，第 20 页可切换训练与推理。原中文版仍为 16 页简短导入。

## 中文

16 页、约 20 分钟的课堂导入，围绕食指指尖 **ID3** 展开。先解释固定手型和已有轨迹如何帮助缩小问题，再介绍配对数据、MLP、encoder/decoder、latent space 和仿真 latent 到传感器 latent 的转换。画面采用深色背景、简洁几何图示与逐步展开，中文讲解配英文技术术语。

直接用 Chrome、Edge 或 Firefox 打开 `index.html`。整个文件包含图形、数据和脚本，无需联网，也不依赖 Python、MuJoCo 或模型权重。GitHub 文件预览不会运行 HTML，需要下载后用浏览器打开。

| 操作 | 快捷键 |
| --- | --- |
| 展开下一步 / 下一页 | →、空格、PageDown |
| 上一步 / 上一页 | ←、PageUp |
| 第一页 / 最后一页 | Home / End |
| 目录 / 当前页讲稿 | O / N |
| 全屏 | F |
| 关闭目录、讲稿或帮助 | Esc |

手机或触摸屏支持左右滑动。讲稿显示在当前画面上；投屏时可在另一设备阅读独立讲稿。

可演示的交互：第 3 页拖动手指，第 4 页移动三轴曲线游标，第 8 页比较 1 帧与 7 帧，第 10 页推进拟合示意，第 13 页切换训练与使用。第 10 页的中间曲线是从基线到最终预测的插值示意，终点是实际留出预测。

浏览器打印样式会展开所有页面与图示。需要静态 PDF 时，选择“保存为 PDF”，打开背景图形，关闭页眉页脚。打印支持取决于浏览器；课堂交互请使用 HTML。

### 内容与维护

- 蓝色：仿真几何和运动；金色：传感器信号；紫色：学习到的表示和映射。
- 第 4 页为真实 ID3 记录。第 10、12、14 页引用本仓库实测参考训练结果，数据已内嵌。
- 5 条实测记录 / 365 个原始触觉包，与 300 条合成变体 / 21,900 个配对时刻分别标记。
- 参考误差仅代表本组相似动作的留出记录，不代表任意材料或整手动作的泛化能力。
- 修改文案与示意图可直接编辑 HTML；讲稿位于脚本的 `notes` 数组，同时维护独立讲稿文件。
- 更新数据或重新训练后，应同步更新内嵌 `lesson-data` 与第 14 页指标。依据见 [参考结果](../REFERENCE_RESULTS.md) 与 [指标 JSON](../reference_metrics.json)。

## English

The expanded [English deck](index.en.html) has **25 slides** and English speaker notes, designed for about 30 minutes with discussion. It focuses on **one sensor, ID3 at the index fingertip**. The original [Chinese deck](index.html) remains a shorter 16-slide introduction.

### Expanded ML explanation

| Slides | Topic |
| --- | --- |
| 1–7 | ID3 scope, replay, paired data and causal history windows |
| 8–12 | Mean and linear baselines, a neuron, MLP layers, loss and training |
| 13–17 | Why use a latent code, compact curve intuition, autoencoders and bottleneck size |
| 18–21 | Separate coordinate systems, pretraining, latent translation and error diagnosis |
| 22–25 | Grouped evaluation, measured results and student experiments |

Slide 9 lets you change one input and see a weighted sum pass through tanh. Slide 14 uses adjustable amplitude and width to illustrate how many curve samples can have a compact description. These are toy examples, not fitted physical latent coordinates. Slide 20 switches between training and inference.

The deck describes MLPs as basic neural networks; mean prediction and linear regression are simpler models. Encoder, decoder and latent mapper are also MLPs in this implementation. Latent space provides an explicit representation to compress, inspect and translate. Better accuracy, denoising and physical interpretability are not guaranteed.

For a shorter introduction, skip slides 3, 9, 14, 18 and 21. The [speaker notes](SPEAKER_NOTES.en.md) explain the examples and their connection to the notebook implementation.

The story progresses from controlled experimental conditions and paired data to a direct MLP, autoencoders, latent representations, and simulation-to-sensor latent translation. Geometric diagrams and incremental reveals keep theory approachable.

Open `index.en.html` in a modern browser. All graphics, data and scripts are embedded; no network, Python environment or simulator is needed. GitHub's source preview does not execute HTML, so download the file first. Use arrow keys or Space to advance, O for the overview, N for notes, and F for fullscreen. Notes appear on the same screen as the slides. Keep both HTML files together to use the language links.

Interactive examples show contact, measured three-axis traces, causal history windows, an illustrative fit progression, and the difference between training and inference. Measured and synthetic data are labelled separately. The fitting animation interpolates between a baseline and the final held-out MLP prediction; it is not an epoch-by-epoch training recording.

Print CSS expands every slide and reveal for browser PDF export. Enable background graphics and disable headers/footers. Use the HTML for interactive teaching. See the [Lab 4 README](../README.md) for setup and the [reference results](../REFERENCE_RESULTS.md) for metric provenance and limitations.

### Editing the English deck

English text, notes and diagrams are authored in [build_en.py](build_en.py). It reuses the Chinese deck's presentation styling, navigation helpers and embedded measured examples, and reads results from `lab4/reference_metrics.json`. Rebuild from the repository root using only Python's standard library:

```bash
python lab4/slides/build_en.py
```

This writes `index.en.html` and `SPEAKER_NOTES.en.md`. The generated HTML is standalone for distribution. Changing the Chinese dataset or helper code requires rebuilding and checking the English deck.

## PAXINI hand model / 整手模型

Both versions show the supplied PAXINI left-hand URDF meshes on slide 2. The gold circle marks **ID3 at the index fingertip**, link `left_index_tactile_link3`. The model uses a neutral, zero-joint display pose; the colors emphasize the selected module. This is a model rendering, not a hardware photograph or a recorded replay posture.

中英文第 2 页展示 PAXINI 左手 URDF 的实际网格，并以金色圆圈标出食指指尖 **ID3**（`left_index_tactile_link3`）。模型采用零关节展示姿态，配色用于突出该传感器；它不是实物照片，也不代表某个回放时刻的姿态。

Source hashes and mesh provenance: [paxini_hand_source.json](assets/paxini_hand_source.json). The hand-only MJCF references the meshes already bundled in `lab4/replay_assets/meshes`. The PNG is embedded into each HTML, so viewing remains fully offline.

To rebuild the model illustration with the lab environment (MuJoCo, NumPy, Pillow), then regenerate English slides:

```bash
MUJOCO_GL=egl python lab4/slides/render_hand.py
python lab4/slides/build_en.py
```

圈注位置由 ID3 网格的渲染分割结果自动计算；重建后仍保持 HTML 单文件离线使用。
