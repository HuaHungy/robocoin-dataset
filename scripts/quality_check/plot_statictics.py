import json
import pathlib

import matplotlib.pyplot as plt
import numpy as np

# 假设你的数据已经加载为字典 data
with open("datas/jump_frame_results.json") as f:
    data = json.load(f)

# 提取关键信息并计算统计量
labels = []
means = []
mean_plus_vars = []
maxs = []

for path, files in data.items():
    values = list(files.values())
    mean_val = np.mean(values)
    var_val = np.var(values)
    var_sqrt_val = np.sqrt(var_val)
    max_val = np.max(values)

    # labels.append(path.split("/")[-5] + "/.../" + path.split("/")[-1])  # 简化长路径名
    labels.append(pathlib.Path(path).parent.parent.parent.name)
    means.append(mean_val)
    mean_plus_vars.append(mean_val + var_sqrt_val)
    maxs.append(max_val)

# 绘图
x = np.arange(len(labels))  # x 轴位置
width = 0.25  # 柱宽

fig, ax = plt.subplots(figsize=(12, 6))

bar1 = ax.bar(x - width, means, width, label="Mean", color="skyblue")
bar2 = ax.bar(x, mean_plus_vars, width, label="Mean + QqrtVariance", color="lightgreen")
bar3 = ax.bar(x + width, maxs, width, label="Max", color="salmon")

# 添加标签和标题
ax.set_xlabel("Dataset Name")
ax.set_ylabel("Value")
ax.set_title("Statistics per Directory: Mean, Mean+Variance, Max")
ax.set_xticks(x)
ax.set_xticklabels(
    [f"{lbl[:15]}..." if len(lbl) > 15 else lbl for lbl in labels], rotation=15, ha="right"
)


# 显示数值在柱子上方
def add_labels(bars):
    for bar in bars:
        height = bar.get_height()
        ax.annotate(
            f"{height:.2f}",
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 3),  # 3 points vertical offset
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
        )


add_labels(bar1)
add_labels(bar2)
add_labels(bar3)

ax.legend()
plt.tight_layout()
plt.grid(axis="y", linestyle="--", alpha=0.7)
plt.show()
