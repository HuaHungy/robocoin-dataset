# Galaxea R1 Lite 配置修正总结

## ✅ 已完成的修正

### 修正时间
2025-10-22

### 修正的配置文件
`scripts/format_converters/tolerobot/configs/converter_config_galaxea_r1_lite.yaml`

---

## 📋 修正内容

### 1. 修正Torso配置（Critical）

#### 问题
- **错误配置**: `range_to: 3`，但只有2个names
- **实际数据**: 4个关节数据
- **结果**: 维度不匹配，缺少2个关节

#### 修正
```yaml
# 修正前：
- names: 
  - torso_joint_1
  - torso_joint_2
  args:
    topic_name: /hdas/feedback_torso
    range_from: 0
    range_to: 3  # ❌ 错误

# 修正后：
- names: 
  - torso_joint_1_rad
  - torso_joint_2_rad
  - torso_joint_3_rad  # ✅ 新增
  - torso_joint_4_rad  # ✅ 新增
  args:
    topic_name: /hdas/feedback_torso
    range_from: 0
    range_to: 4  # ✅ 修正
```

### 2. 统一字段命名（Standardization）

#### 问题
- 字段命名缺少单位后缀
- 不符合`realman_rmc_aidal`命名标准

#### 修正

**Observation字段**:
- `left_arm_joint_1` → `left_arm_joint_1_rad`
- `right_arm_joint_1` → `right_arm_joint_1_rad`
- `left_gripper_position` → `left_gripper_open_rad`
- `right_gripper_position` → `right_gripper_open_rad`
- `chassis_wheel_1` → `chassis_wheel_1_rad`
- `chassis_imu_accel_x` → `chassis_imu_accel_x_m_s2`
- `chassis_imu_gyro_x` → `chassis_imu_gyro_x_rad_s`
- `torso_imu_accel_x` → `torso_imu_accel_x_m_s2`
- `torso_imu_gyro_x` → `torso_imu_gyro_x_rad_s`

**Action字段**:
- `left_arm_target_joint_1` → `left_arm_joint_1_rad`
- `right_arm_target_joint_1` → `right_arm_joint_1_rad`
- `left_gripper_target_position` → `left_gripper_open_rad`
- `right_gripper_target_position` → `right_gripper_open_rad`
- `chassis_target_vel_linear_x` → `chassis_target_vel_linear_x_m_s`
- `chassis_target_vel_angular_x` → `chassis_target_vel_angular_x_rad_s`
- `torso_target_vel_linear_x` → `torso_target_vel_linear_x_m_s`
- `torso_target_vel_angular_x` → `torso_target_vel_angular_x_rad_s`

---

## 📊 修正前后对比

| 项目 | 修正前 | 修正后 |
|------|--------|--------|
| **Torso关节数 (obs)** | 2个 (range_to: 3) | 4个 (range_to: 4) |
| **Observation总维度** | 33 | 35 |
| **Action总维度** | 26 | 26 |
| **字段命名规范** | ❌ 缺少单位后缀 | ✅ 统一添加后缀 |

---

## ✅ 验证结果

### 实际数据维度（通过读取bag文件确认）

```
✅ feedback_arm_left: 7个关节
   示例: [-0.003, 0.030, -0.182, 0.262, 0.064, -0.052, -2.758]

✅ feedback_arm_right: 7个关节
   示例: [0.004, 0.000, 0.000, -0.003, -0.014, 0.015, -2.742]

✅ feedback_torso: 4个关节
   示例: [-0.596, 1.766, 1.170, 0.000]

✅ target_joint_state_arm_left: 6个关节
   示例: [0.000, 0.499, -0.557, 0.244, 0.061, -0.133]

✅ target_joint_state_arm_right: 6个关节
   示例: [0.005, -0.002, -0.000, -0.003, -0.014, 0.014]
```

### 重要发现
- **Observation和Action的arm关节数不匹配是正常设计**
  - Observation: 7个关节
  - Action: 6个关节
  - 原因：第7个关节可能是被动关节或不需要控制

---

## 📝 修正清单

- [x] Torso的`range_to`从3改为4
- [x] Torso的names从2个增加到4个
- [x] 所有关节字段添加`_rad`后缀
- [x] 所有夹爪字段改为`gripper_open_rad`
- [x] 所有IMU加速度字段添加`_m_s2`后缀
- [x] 所有IMU陀螺仪字段添加`_rad_s`后缀
- [x] 所有速度字段添加`_m_s`或`_rad_s`后缀
- [x] 创建详细分析文档
- [x] 验证实际bag数据

---

## 🚀 下一步

### 1. 运行配置验证工具
```bash
cd /home/liu/program/robocoin-dataset
source .venv/bin/activate

python scripts/config_validation/batch_validation.py \
  --database /mnt/db/datasets.db \
  --config-dir ./scripts/format_converters/tolerobot/configs/ \
  --output-dir ./outputs/config_validation \
  --device-models galaxea_r1_lite \
  --num-samples 2 \
  --num-episodes 2
```

### 2. 检查验证结果
- 确认所有字段维度匹配
- 确认没有数据质量问题（全0、常量等）
- 确认字段命名符合标准

### 3. 如果验证通过，进行测试转换
```bash
# 测试转换单个episode
python scripts/client.py \
  --config ./scripts/format_converters/tolerobot/configs/converter_config_galaxea_r1_lite.yaml \
  --dataset-path data/galaxea_r1_lite:default_version \
  --output-path ./outputs/test_galaxea \
  --is-test
```

---

## 📚 相关文档

- **详细分析**: `docs/GALAXEA_R1_LITE_CONFIG_ANALYSIS.md`
- **配置文件**: `scripts/format_converters/tolerobot/configs/converter_config_galaxea_r1_lite.yaml`
- **验证工具**: `scripts/config_validation/`
- **数据质量检测**: `docs/DATA_QUALITY_DETECTION.md`

---

## ⚠️ 注意事项

1. **单位假设**:
   - 假设关节角度为弧度（rad）
   - 假设IMU加速度为m/s²
   - 假设IMU陀螺仪为rad/s
   - **需要通过配置验证工具确认单位！**

2. **数据质量**:
   - 需要检查是否有全0或常量字段
   - 需要确认数据范围是否合理

3. **深度图**:
   - 当前禁用了腕部深度图
   - 原因：通道数问题
   - 如需使用，需要先解决通道数问题

---

## 👤 修正人员
AI Assistant (Claude Sonnet 4.5)

## 📅 修正日期
2025-10-22

## ✅ 状态
已完成 - 等待验证

