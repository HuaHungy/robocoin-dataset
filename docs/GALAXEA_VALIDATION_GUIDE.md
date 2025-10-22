# Galaxea R1 Lite 配置验证指南

## 🎯 验证目标

使用新实现的rosbag支持工具验证`converter_config_galaxea_r1_lite.yaml`配置文件

---

## 📋 验证前准备

### 1. 已知问题清单

根据之前的分析，Galaxea R1 Lite配置有以下已知问题需要验证：

| 问题 | 描述 | 状态 |
|------|------|------|
| **Gripper单位** | 值是度数（0-100），需要转换为弧度 | ✅ 已修正（添加degree2rad） |
| **Torso维度** | 实际有4个关节，配置只有3个 | ✅ 已修正（range_to: 3→4） |
| **Chassis位置** | 数据全零，可能不工作 | ⚠️ 需验证 |
| **Torso第4关节** | 数据全零，虽然维度正确 | ⚠️ 需验证 |

---

## 🔧 验证步骤

### Step 1: 运行验证工具

```bash
# 进入项目目录
cd /home/liu/program/robocoin-dataset

# 激活环境（如果使用uv）
source .venv/bin/activate

# 运行验证
python scripts/config_validation/batch_validation.py \
    --database /mnt/db/datasets.db \
    --config-dir ./scripts/format_converters/tolerobot/configs/ \
    --output-dir ./outputs/validation \
    --device-model galaxea_r1_lite \
    --num-datasets 2
```

### Step 2: 查看验证报告

```bash
# 查看文本报告
cat ./outputs/validation/galaxea_r1_lite_default_version_*.txt

# 或查看JSON报告（详细）
cat ./outputs/validation/galaxea_r1_lite_default_version_*.json | python -m json.tool
```

---

## 📊 预期验证结果

### A. Topics检查

**期望看到的topics**：
```
✅ /hdas/feedback_left_arm (N条消息)
✅ /hdas/feedback_right_arm (N条消息)  
✅ /hdas/feedback_torso (N条消息)
✅ /hdas/feedback_gripper_left (N条消息)
✅ /hdas/feedback_gripper_right (N条消息)
⚠️ /hdas/feedback_chassis (N条消息) - 可能全零
✅ /hdas/images/* (图像topics)
```

### B. 维度检查

**需要确认的维度**：
```yaml
✅ Left Arm: 6维 (range_from:0, range_to:6)
✅ Right Arm: 6维 (range_from:0, range_to:6)
✅ Torso: 4维 (range_from:0, range_to:4) ⭐已修正
✅ Left Gripper: 1维 (range_from:0, range_to:1)
✅ Right Gripper: 1维 (range_from:0, range_to:1)
⚠️ Chassis: 3维 (但可能全零)
```

### C. 数据质量检查

**需要确认的数据质量**：
```python
# 1. Gripper值范围
Left Gripper: 
  期望范围: 0-100（度）
  ✅ 如果有convert_func: degree2rad

# 2. Chassis位置
Chassis:
  ⚠️ 如果全零 → 建议删除或注释

# 3. Torso第4关节
Torso Joint 4:
  ⚠️ 如果全零 → 建议注释说明
```

---

## 🔍 详细检查项

### 检查1: Gripper转换函数

**配置应该有**：
```yaml
# 左夹爪
- names: 
  - left_gripper_open_rad
  args:
    topic_name: /hdas/feedback_gripper_left
    range_from: 0
    range_to: 1
  convert_func: degree2rad  # ✅ 必须存在

# 右夹爪
- names:
  - right_gripper_open_rad
  args:
    topic_name: /hdas/feedback_gripper_right
    range_from: 0
    range_to: 1
  convert_func: degree2rad  # ✅ 必须存在
```

**验证方法**：
1. 检查配置文件是否有`convert_func: degree2rad`
2. 查看rosbag中gripper的实际数值范围
3. 如果是0-100范围→确认需要转换

---

### 检查2: Torso维度

**配置应该有**：
```yaml
- names:
  - torso_joint_1_rad
  - torso_joint_2_rad
  - torso_joint_3_rad
  - torso_joint_4_rad  # ✅ 第4个关节
  args:
    topic_name: /hdas/feedback_torso
    range_from: 0
    range_to: 4  # ✅ 必须是4
```

**验证方法**：
1. 检查rosbag中torso topic的实际维度
2. 确认是4维数组
3. 检查第4维的数值（可能全零）

---

### 检查3: Chassis数据质量

**如果chassis全零**：

**选项A**: 删除配置
```yaml
# ❌ 删除这部分（如果确认不工作）
# - names:
#   - chassis_pos_x_m
#   - chassis_pos_y_m
#   - chassis_pos_theta_rad
```

**选项B**: 保留并注释
```yaml
# 底盘位置（3维）- ⚠️ 数据全零，可能底盘传感器未工作
- names:
  - chassis_pos_x_m
  - chassis_pos_y_m
  - chassis_pos_theta_rad
  args:
    topic_name: /hdas/feedback_chassis
    range_from: 0
    range_to: 3
```

---

### 检查4: 遗漏字段

**可能发现的遗漏字段**：

根据MMK2的经验，可能缺少：
```yaml
# 🆕 左臂速度（如果存在）
- names:
  - left_arm_joint_1_vel_rad_s
  - left_arm_joint_2_vel_rad_s
  ...

# 🆕 左臂力矩（如果存在）
- names:
  - left_arm_joint_1_eff_nm
  - left_arm_joint_2_eff_nm
  ...
```

**验证方法**：
1. 查看验证报告的"遗漏字段"部分
2. 检查这些字段的非零值比例
3. 如果非零值>50%→建议添加

---

## 📝 验证报告示例

### 成功示例

```
==================================================
✅ Galaxea R1 Lite配置验证通过
==================================================

[Topics检查]
  ✅ 所有配置的topics都存在
  ✅ 所有topics的维度匹配

[维度检查]
  ✅ Left Arm: 6维 - 匹配
  ✅ Right Arm: 6维 - 匹配
  ✅ Torso: 4维 - 匹配（已修正）
  ✅ Grippers: 1维 - 匹配

[数据质量]
  ⚠️  Chassis: 全零数据（已注释说明）
  ⚠️  Torso第4关节: 全零数据（已注释说明）
  ✅ 其他字段: 数据正常

[转换函数]
  ✅ Gripper: degree2rad已配置
```

### 需要修复示例

```
==================================================
❌ Galaxea R1 Lite配置需要修复
==================================================

[错误]
  ❌ Torso维度不匹配
     配置期望: 3维
     实际数据: 4维
     修复: 修改range_to为4，添加torso_joint_4_rad

  ❌ Gripper缺少转换函数
     修复: 添加convert_func: degree2rad

[警告]
  ⚠️  遗漏字段:
     - /hdas/feedback_left_arm/velocity (6维)
     - /hdas/feedback_left_arm/effort (6维)
     建议: 根据实际需求决定是否添加
```

---

## 🔧 修复流程

### 1. 根据报告修改配置

```bash
# 编辑配置文件
vim scripts/format_converters/tolerobot/configs/converter_config_galaxea_r1_lite.yaml

# 根据验证报告修改：
# - 修正维度
# - 添加转换函数
# - 删除或注释无效字段
# - （可选）添加遗漏的有意义字段
```

### 2. 重新验证

```bash
# 再次运行验证
python scripts/config_validation/batch_validation.py \
    --device-model galaxea_r1_lite \
    --num-datasets 1

# 确认全部通过
```

### 3. 提交修改

```bash
# 查看修改
git diff scripts/format_converters/tolerobot/configs/converter_config_galaxea_r1_lite.yaml

# 提交
git add scripts/format_converters/tolerobot/configs/converter_config_galaxea_r1_lite.yaml
git commit -m "fix(galaxea): update config based on rosbag validation

- Fix torso dimension: 3 → 4
- Add degree2rad conversion for grippers
- Mark chassis as all-zero data
- Add comments for torso joint 4 (all-zero)
"
```

---

## 🎯 验证完成标准

配置验证通过的标准：

- ✅ 所有配置的topics在rosbag中存在
- ✅ 所有配置的维度与实际数据匹配
- ✅ Gripper有degree2rad转换
- ✅ 无维度不匹配错误
- ⚠️ 全零数据已标注或删除
- ℹ️ 遗漏字段已评估（添加或忽略）

---

## 📋 验证后行动

### 如果验证通过

1. ✅ 可以进行test模式转换测试
2. ✅ 可以进行正式转换
3. ✅ 更新文档说明已验证

### 如果发现问题

1. ⚠️ 根据报告修改配置
2. ⚠️ 重新验证直到通过
3. ⚠️ 记录修改原因

---

## 🔗 相关文档

- `docs/GALAXEA_R1_LITE_CONFIG_ANALYSIS.md` - 之前的分析
- `docs/GALAXEA_R1_LITE_DATA_ISSUES.md` - 数据问题记录
- `docs/GALAXEA_GRIPPER_COMPARISON.md` - Gripper数据对比
- `docs/ROSBAG_VALIDATION_USAGE.md` - rosbag验证使用指南

---

**指南创建时间**: 2025-10-22  
**下一步**: 运行实际验证，获取验证报告

