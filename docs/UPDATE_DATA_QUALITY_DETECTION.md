# 🆕 新功能：数据质量自动检测

## 📅 更新时间
2025-10-22 晚

## 🎯 功能概述

配置验证工具新增**数据质量自动检测**功能，可以发现：
- ⚠️ **全0数据** - 所有值都是0
- ⚠️ **常量数据** - 所有值都相同
- ⚠️ **极小变化** - 数据几乎不变

---

## 🔍 为什么需要这个功能？

### 实际场景

用户反馈发现一个重要问题：

> "有的维度确实是有数据，但是他是0；有的确实是没有数据，但是他就是有那个维度，只是数据一直为0"

这会导致：
1. **配置看起来正确**（字段存在、维度匹配）
2. **但数据实际无效**（传感器未连接、数据采集失败）
3. **浪费存储和训练资源**

---

## ✨ 新增功能

### 1. 自动检测

Schema分析器会自动检测每个字段的数据质量：

```python
# 检测全0
if np.all(data == 0):
    warning = 'ALL_ZERO'

# 检测常量
elif std < 1e-10:
    warning = 'CONSTANT'

# 检测极小变化
elif max - min < 1e-6:
    warning = 'VERY_SMALL_RANGE'
```

### 2. 报告显示

在配置对比报告中会显示警告：

```
[State]
  ⚠️ observations/qpos [80:83]
      Names: left_eef_pos_x_m, left_eef_pos_y_m, left_eef_pos_z_m
      - ⚠️ 数据质量问题: 所有值都为0（可能是传感器未连接或数据采集失败）

  ⚠️ observations/qpos [10:11]
      Names: right_gripper_open
      - ⚠️ 数据质量问题: 所有值都是常量 0.5（可能是传感器故障）
```

---

## 🛠️ 如何使用

### Step 1: 运行验证（同之前）

```bash
bash scripts/config_validation/run_validation.sh
```

### Step 2: 查看数据质量警告

```bash
# 查看所有数据质量问题
grep "数据质量问题" outputs/config_validation/*_comparison.txt
```

### Step 3: 判断和处理

对于每个警告，需要判断是否合理：

#### 情况A: 合理的全0 ✅

**示例**: 夹爪关闭状态
```yaml
- names:
  - right_gripper_open
  args:
    h5_path: observations/qpos
    range_from: 10
    range_to: 11
  # 注释: 部分episodes开始时夹爪为关闭状态(0)，这是正常的
```

**处理**: 保留配置，添加注释说明

#### 情况B: 异常的全0 ❌

**示例**: 末端执行器位置全0（但视频中机械臂在动）
```yaml
# 删除无效配置
# - names:
#   - left_eef_pos_x_m  # 2025-10-22: 数据全0，传感器未连接
#   - left_eef_pos_y_m
#   - left_eef_pos_z_m
#   args:
#     h5_path: observations/qpos
#     range_from: 80
#     range_to: 83
```

**处理**: 从配置中删除

---

## 📊 预期效果

使用这个功能后：

| 指标 | 改进 |
|------|------|
| **发现无效字段** | 30分钟内全部发现 |
| **节省存储空间** | 10-20% |
| **提高数据质量** | 避免训练无效数据 |
| **减少问题排查时间** | 提前发现，避免转换后才发现 |

---

## 📚 详细文档

- **完整说明**: `docs/DATA_QUALITY_DETECTION.md`
- **快速开始**: `scripts/config_validation/START_HERE.md`
- **使用指南**: `scripts/config_validation/README.md`

---

## 🎯 典型场景

### 场景1: 双臂机器人，左臂未使用

**检测结果**:
```
⚠️ 所有left_相关字段数据都为0
```

**处理**:
```yaml
# 删除左臂相关配置
# observation:
#   state:
#     sub_state:
#       - names:
#         - left_arm_joint_1_rad  # 左臂未使用，数据全0
#         - left_arm_joint_2_rad
#         ...
```

### 场景2: 末端姿态传感器故障

**检测结果**:
```
⚠️ eef_rot_euler字段数据都是常量 [0, 0, 1.57]
```

**处理**:
```yaml
# 删除或标记为可选
# - names:
#   - right_eef_rot_euler_x_rad  # 传感器故障，数据为常量
#   - right_eef_rot_euler_y_rad
#   - right_eef_rot_euler_z_rad
```

### 场景3: 夹爪始终关闭

**检测结果**:
```
⚠️ gripper_open字段数据都为0
```

**判断**: 查看任务描述
- 如果是"推动物品"任务（不需要抓取） → 合理 ✅
- 如果是"抓取物品"任务 → 异常 ❌

---

## 🔧 技术细节

### 修改的文件

1. **schema_analyzer.py**
   - 在`_describe_h5_dataset()`中添加数据质量检测
   - 检测全0、常量、极小变化
   - 添加warning和data_quality标记

2. **config_comparator.py**
   - 在对比state和action时检查data_quality
   - 在报告中显示数据质量警告
   - 提供处理建议

3. **文档更新**
   - `DATA_QUALITY_DETECTION.md` - 详细说明
   - `START_HERE.md` - 快速指南

---

## ⚡ 立即使用

```bash
cd /home/liu/program/robocoin-dataset
conda activate robocoin-dataset

# 运行验证（包含数据质量检测）
bash scripts/config_validation/run_validation.sh

# 查看数据质量问题
grep -A 2 "数据质量问题" outputs/config_validation/*_comparison.txt

# 统计有多少个全0字段
grep -c "所有值都为0" outputs/config_validation/*_comparison.txt
```

---

## 💡 最佳实践

1. **首次验证**: 关注所有数据质量警告
2. **视频确认**: 对照视频判断是否合理
3. **配置清理**: 删除无效字段
4. **添加注释**: 记录决策原因
5. **重新验证**: 确认清理后没有新问题

---

**更新**: 2025-10-22  
**状态**: ✅ 已实现并集成  
**影响**: 提高配置质量，避免无效数据

立即运行验证，发现并清理无效数据！ 🚀

