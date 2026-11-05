# Lab 4 reference results / 参考结果

2026-11-05 (Asia/Shanghai). Machine-readable scores, versions, source hashes and parent splits are in [reference_metrics.json](reference_metrics.json).

## English

Both complete training runs used seed 7, at most 600 epochs, 7-frame windows,
11 features per frame, an 8-dimensional simulation latent and a 4-dimensional
sensor latent. Validation chose the saved checkpoints. Test results were not
used to select architectures or the generator's variation ranges.

| Model | Measured RMSE (nominal N) | Synthetic RMSE (model N) |
| --- | ---: | ---: |
| Zero | 1.1610 | 0.9912 |
| Training mean | 0.5409 | 0.6225 |
| Ridge | 0.1330 | 0.0479 |
| Direct MLP | 0.0865 | 0.0246 |
| Latent translation | 0.0993 | 0.0704 |
| Sensor self-reconstruction — reads target | 0.0538 | 0.0524 |

The last row is a compression reference, not cross-modal prediction. A direct
MLP outperforms the latent bridge here; compression and translation can both
introduce error. This is a useful result to explain, not a reason to hide a
simpler baseline. The expanded synthetic dataset has broader variation than
the earlier 60-sequence prototype, so scores are not directly comparable.

The measured test comprises 65 windows from original episode #5. Synthetic
testing comprises 3,900 windows from 60 variants of that same held-out parent.
There are only five independent measured motion sources in total. These scores
do not validate new objects, sessions or hand poses.

The original measured geometry is unmodified saved-state replay. Some episodes
have no simulated ID3 force, but nearest-point and motion features still predict
parts of the measured response. Synthetic pairs use an additional fixed fixture
translation and synthetic timing, with an analytic signal model. They do not
establish accurate MuJoCo force reproduction.

Curated plots are stored in `figures/`. Full run outputs, model checkpoints and
local validation logs are intentionally kept in ignored `outputs/`; the README
commands reproduce them. No developer-specific absolute path is needed.

## 中文

两套完整训练均使用 seed 7、最多 600 epochs、7 帧窗口、每帧 11 维特征，以及
8 维仿真 latent、4 维传感器 latent。Checkpoint 根据验证集选择，架构和生成器
变化范围没有根据测试成绩调整。

上表最后一行的传感器自重建在推理时读取了目标，只能作为压缩参考。当前数据上
直接 MLP 比 latent 转换更准确，因为压缩和映射都可能引入误差；课堂应解释这个
结果，并保留简单基线。本版合成数据的变化范围比早期 60 条原型更大，不能直接
横向比较两个版本的成绩。

实测测试为原始第 5 条记录的 65 个窗口；合成测试为同一留出父记录的 60 个变体、
3,900 个窗口。独立实测运动来源总共仍只有五条，不支持跨物体、session 或手型
泛化结论。

实测实验使用原始保存状态的几何；即使某些记录的 ID3 仿真力为零，最近点与运动
信息仍能预测部分实测响应。合成实验额外加入固定工装平移与合成时间轴，并用
解析信号模型生成输出，不能把其成绩解释为 MuJoCo 三轴力已准确复现。

选定的参考图放在 `figures/`。完整运行输出、权重和本机验证日志放在 Git 忽略的
`outputs/`；按 README 命令可以重新生成，无需教师电脑的绝对路径。
