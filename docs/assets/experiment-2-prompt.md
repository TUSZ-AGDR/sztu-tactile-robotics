# 实验 2 示意图生成提示词

生成方式：内置 image_gen 工具。

Use case: scientific-educational.
Asset type: a single clear Chinese course experiment explainer, landscape 16:9, high resolution, fully opaque white background.
Primary request: Explain experiment 2 in a MuJoCo tactile robotics course: students edit one or two lines of a feedback controller, a fixed DexH13-style articulated robotic hand grasps a cube, tactile feedback adjusts finger closure, and the experiment checks holding for 3 seconds without excessive force, with an optional brief downward pull. This is a planned teaching experiment, not a photo or actual experimental data.

Style: minimal modern textbook illustration, clean flat shapes with a little depth, dark readable Chinese sans-serif text, generous white space, very few words, no dense dashboard, no logos or watermarks. Three numbered columns flow left to right with clear arrows. One main illustration per column. Use neutral light grey robot parts, tactile heatmap colors blue through yellow to red, green for success and orange/red for the force limit.

Exact title at top: "实验 2：用触觉反馈控制抓握"
Exact small subtitle: "改一两行代码，让物体握得稳、用力不过大"

Column 1 title: "① 改策略"
Illustration: a simple Python code card with exactly these two readable code lines:
"error = target - force"
"return gain * error"
Below it: "调整增益或判断条件"
The code returns finger closure RATE: positive tightens and negative loosens; do not show a direct force actuator.

Column 2 title: "② 跑仿真"
Main image: a fixed-base articulated four-finger robotic hand with an opposing thumb gently holding a cube off any surface. The cube is actually between fingers with credible fingertip contacts, no human hand, no robot arm. Small blue/yellow/red taxel dots only on the contact-facing sensor areas. Beside the hand, a simple small 2D taxel heatmap of a selected sensor, labeled "触觉热力图". A shared small color scale labeled "法向力 / N", endpoints "低" and "高".
Clearly depict a simple feedback loop using two clean curved arrows around the hand and a small controller symbol: "读取触觉" then "调整闭合".
Below column 2 show compact experiment stages exactly: "撤支撑 → 保持 3 秒 → 可选轻拉"
A small downward arrow next to the cube suggests the optional pull. No platform touching or supporting the cube during the hold.

Column 3 title: "③ 看结果"
Illustration: one simple schematic time series of grip force versus time, blue measured-force curve approaches a dashed target line, brief disturbance wiggle, never crosses the upper red force-limit line. Clearly label upper line "力上限", middle dashed line "目标力", vertical axis "握力 / N", horizontal axis "时间 / s", and add small "曲线示意".
Under the chart two large simple green checkmarks with exact captions:
"物体不掉落"
"用力不超限"

At the bottom one simple takeaway strip: "比较：固定闭合 vs 触觉反馈"
Scientific constraints: grasp feedback senses touch and changes closure; tactile heatmap shows sensor values, not object temperature. The scene uses gravity and released support. Diagram must not imply tactile feedback always wins. No numeric performance claims. Render all specified Chinese text accurately, no additional paragraphs, no unexplained English aside from the two Python lines and the word vs. Keep everything spacious and immediately comprehensible.

