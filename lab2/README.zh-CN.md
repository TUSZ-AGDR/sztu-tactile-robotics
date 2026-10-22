# Lab 2：让手抓住物体

[English](README.md) | 简体中文

这个实验里，你会看到一只手闭合、抓住物体，再尝试让它抓稳或掉落。

你只需要改两个文件：

| 文件 | 用来改什么 |
| --- | --- |
| [examples/parameters.py](examples/parameters.py) | 物体、抓握力度、重量、摩擦 |
| [student_policy.py](student_policy.py) | 手如何根据触觉收紧或放松 |

## 第 1 步：准备好运行环境

需要 Python 3.10 或更新版本，以及完整的课程仓库。不要只复制 `lab2` 文件夹。

在编辑器里打开课程仓库文件夹，再打开终端。文件夹可能叫 **Pacini_Course** 或 **sztu-tactile-robotics**。终端所在目录应能看到 `lab2` 文件夹。

如果使用已有的课程 Conda 环境，先运行：

```bash
conda activate dexh13sim
```

然后安装依赖，只需安装一次：

```bash
python -m pip install -r lab2/requirements.txt
```

## 第 2 步：先跑一次抓握

打开 `lab2/examples/parameters.py`，找到下面四行。第一次先设成这样，其他代码不用改：

```python
OBJECT_NAME = "box"
TARGET_FORCE_N = 4.0
MASS_KG = 0.03
FRICTION = 1.0
```

保存文件，在终端运行：

```bash
python lab2/examples/parameters.py --controller student
```

**后面的练习都用这条命令。** 它会同时使用参数文件和 `student_policy.py`。

窗口打开后：

1. 手从关节零位开始，慢慢进入抓握姿态。
2. 第 4 秒，物体不再被初始支撑托住，观察手能不能握住它。
3. 右侧有触觉热力图、抓握力度曲线和物体高度曲线。
4. 点击三维窗口，再按 `N` / `P` 切换传感器。没碰到物体的传感器没有明显颜色变化，这是正常的。
5. 实验结束后窗口会停留。看完后关闭窗口。

**每次改代码：保存 → 关闭旧窗口 → 重新运行。**

## 第 3 步：换一个物体

还是打开 `lab2/examples/parameters.py`，只改 `OBJECT_NAME`：

| 想抓什么 | 这一行怎么写 |
| --- | --- |
| 方块 | `OBJECT_NAME = "box"` |
| 球 | `OBJECT_NAME = "sphere"` |
| 圆柱 | `OBJECT_NAME = "cylinder"` |

保存后，再运行：

```bash
python lab2/examples/parameters.py --controller student
```

观察：换了物体后，手的动作和触觉颜色有什么变化？

## 第 4 步：改抓握力度和策略

先试着在 `parameters.py` 改一行：

```python
TARGET_FORCE_N = 2.0  # 也可以试 4.0、6.0
```

数字越大，策略希望抓得越用力。先只改这一项，再运行同一条命令。

接着打开 `lab2/student_policy.py`，找到：

```python
GAIN = 0.1
```

把数字改成 `0.3` 或 `0.6`。这个数字控制调整的快慢：数值较小，调整较慢；数值较大，调整更快，也可能出现晃动。

先保留下面的函数，暂时不用改：

```python
def policy(obs):
    error = obs.target_force_N - obs.grip_force_N
    return GAIN * error
```

它的意思是：触觉告诉手“力度不够就收紧，力度太大就放松”。

保存后运行：

```bash
python lab2/examples/parameters.py --controller student
```

每次只改一个数字，观察手是否握住物体、力度曲线是否更平稳。数值变大不一定抓得更好。

## 第 5 步：看一次明显的滑落

先在 `student_policy.py` 设置：

```python
GAIN = 0.3
```

再把 `parameters.py` 的四行改成：

```python
OBJECT_NAME = "sphere"
TARGET_FORCE_N = 2.0
MASS_KG = 0.03
FRICTION = 0.05
```

这里把物体表面变得很滑。保存两个文件，然后运行：

```bash
python lab2/examples/parameters.py --controller student
```

观察第 4 秒之后：球会滑落，物体高度曲线也会下降。

看完把 `FRICTION` 改回 `1.0`，再运行一次，比较差别。

还可以试另一种失败：恢复第 2 步的四行参数，把 `GAIN` 改成 `0.01`。这次手闭合太慢，物体释放时还没夹住，就会掉落。

## 结果在哪里？

关闭窗口后，终端会显示：

- `PASS`：这一次通过。
- `FAIL`：这一次失败，可能掉落，也可能用力过大。
- `Results: ...`：这次结果保存的位置。

在这个位置打开 `curves.png` 看力度和高度曲线，打开 `heatmap.png` 看触觉图。

如果没有打开窗口，检查命令中是否加了 `--headless` 或 `--compare`；这两个选项会关闭图形窗口。若提示 `No ... display is available`，请在有桌面的电脑终端运行。

教师现场演示可使用 [简短英文讲稿](TEACHING_SCRIPT.md) 或 [中文课堂讲稿](TEACHING_SCRIPT.zh-CN.md)。模型原理、评分规则或自动对比命令可查看 [教师参考](TEACHER_NOTES.md) 和 [验证记录](VALIDATION.md)。
