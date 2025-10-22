# Galaxea R1 Lite 数据质量问题报告

## 🔍 分析日期
2025-10-22

## 📦 数据源
- Device: `galaxea_r1_lite:default_version`
- 示例文件: `RB250527007_20250717112739604_RAW.bag`

---

## 🚨 发现的严重问题

### 问题1: Gripper单位错误（Critical）

#### 实际数据
```
/hdas/feedback_gripper_left:
  position[0] = 97.881347

/hdas/feedback_gripper_right:
  position[0] = 97.341041

/motion_target/target_position_gripper_left:
  position[0] = 100.000000

/motion_target/target_position_gripper_right:
  position[0] = 100.000000
```

#### 问题分析
- ❌ **值范围约97-100，明显不是弧度（rad）**
- 弧度范围应该是0-2π（约0-6.28）
- 可能的单位：
  - 百分比（0-100%）
  - 角度（degree）
  - 编码器值
  - 毫米（mm）

#### 当前配置
```yaml
# ❌ 错误：使用了_rad后缀
- names: 
  - left_gripper_open_rad
  args:
    topic_name: /hdas/feedback_gripper_left
    range_from: 0
    range_to: 1
```

#### 修正建议
```yaml
# 方案A: 如果是百分比
- names: 
  - left_gripper_open_pct  # 或 left_gripper_open_percent
  args:
    topic_name: /hdas/feedback_gripper_left
    range_from: 0
    range_to: 1

# 方案B: 如果是角度
- names: 
  - left_gripper_open_deg
  args:
    topic_name: /hdas/feedback_gripper_left
    range_from: 0
    range_to: 1

# 方案C: 如果是距离
- names: 
  - left_gripper_open_mm  # 或 _m
  args:
    topic_name: /hdas/feedback_gripper_left
    range_from: 0
    range_to: 1
```

#### Action Required
**需要询问数据采集方或查看文档确认gripper的实际单位！**

---

### 问题2: Chassis Position全为0（Warning）

#### 实际数据
```
/hdas/feedback_chassis:
  关节名称: ['chassis']
  Position (3个): [0.0, 0.0, 0.0]  # ❌ 全是0
  Velocity (6个): [0.001, -0.001, 0.001, 0.0, 0.0, 0.0]  # ✅ 有数据
  Effort (6个): [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
```

#### 问题分析
- ❌ Position字段**全是0**（可能是无效数据）
- ✅ Velocity字段有数据（虽然很小）
- Velocity实际有**6个元素**（不是我们配置的3个）

#### 当前配置
```yaml
# ❌ 取position，但全是0
- names: 
  - chassis_wheel_1_rad
  - chassis_wheel_2_rad
  - chassis_wheel_3_rad
  args:
    topic_name: /hdas/feedback_chassis
    range_from: 0
    range_to: 3  # 只取position的前3个
```

#### 修正建议

**方案A: 如果需要底盘状态，应该用velocity而不是position**
```yaml
# 需要确认converter是否支持取velocity字段
# 或者需要创建专门的velocity extractor
```

**方案B: 如果position确实无效，应该禁用或标记为可选**
```yaml
# 标记为warning并继续，或完全移除这个配置
```

#### Action Required
1. 确认是否需要底盘的position数据
2. 如果需要，确认为什么position全是0
3. 考虑是否应该用velocity代替position

---

### 问题3: Torso第4个关节全为0（Warning）

#### 实际数据
```
/hdas/feedback_torso:
  关节名称: ['torso']
  Position (4个):
    [0] = -0.596000  ✅
    [1] =  1.766400  ✅
    [2] =  1.170100  ✅
    [3] =  0.000000  ❌ 全为0
  Velocity (4个):
    [0] =  0.002333  ✅
    [1] = -0.007000  ✅
    [2] = -0.002333  ✅
    [3] =  0.000000  ❌ 全为0
  Effort (4个):
    [0] =  0.035000  ✅
    [1] =  5.481667  ✅
    [2] =  0.378333  ✅
    [3] =  0.000000  ❌ 全为0
```

#### 问题分析
- 前3个关节有正常数据
- 第4个关节**position、velocity、effort全是0**
- 可能原因：
  - 未使用的关节
  - 数据采集bug
  - 占位符字段
  - 传感器故障

#### 当前配置
```yaml
# 包含了第4个关节
- names: 
  - torso_joint_1_rad
  - torso_joint_2_rad
  - torso_joint_3_rad
  - torso_joint_4_rad  # ❌ 这个全是0
  args:
    topic_name: /hdas/feedback_torso
    range_from: 0
    range_to: 4
```

#### 修正建议

**方案A: 只使用前3个关节**
```yaml
- names: 
  - torso_joint_1_rad
  - torso_joint_2_rad
  - torso_joint_3_rad
  args:
    topic_name: /hdas/feedback_torso
    range_from: 0
    range_to: 3  # 只取前3个
```

**方案B: 保留但标记为可能全0**
```yaml
# 保持range_to: 4，但在文档中注明第4个关节可能无效
# 训练时可以通过数据质量检测工具识别并报warning
```

#### Action Required
1. 确认第4个关节是否应该有数据
2. 如果确实无效，修改配置只用前3个
3. 在其他episode中验证是否也是全0

---

### 问题4: IMU Orientation未使用（Info）

#### 实际数据
```
/hdas/imu_chassis 和 /hdas/imu_torso 都有:
  Linear Acceleration (3个)  ✅ 已使用
  Angular Velocity (3个)     ✅ 已使用
  Orientation Quaternion (4个)  ❌ 未使用
```

#### 当前配置
```yaml
# 只取了6个元素（加速度+角速度）
- names:
  - chassis_imu_accel_x_m_s2
  - chassis_imu_accel_y_m_s2
  - chassis_imu_accel_z_m_s2
  - chassis_imu_gyro_x_rad_s
  - chassis_imu_gyro_y_rad_s
  - chassis_imu_gyro_z_rad_s
  args:
    topic_name: /hdas/imu_chassis
    range_from: 0
    range_to: 6
```

#### 建议
如果需要使用orientation（姿态）信息，可以添加：
```yaml
# 额外添加orientation（如果需要）
- names:
  - chassis_imu_orient_quat_x
  - chassis_imu_orient_quat_y
  - chassis_imu_orient_quat_z
  - chassis_imu_orient_quat_w
  args:
    topic_name: /hdas/imu_chassis
    field: orientation  # 需要确认converter是否支持
```

**注意**：大多数机器人控制任务不需要绝对姿态，只需要角速度和加速度，所以当前配置可能是合理的。

---

## 📊 数据质量统计

| Topic | 字段 | 状态 | 问题 |
|-------|------|------|------|
| feedback_arm_left | position[0-6] | ✅ 正常 | - |
| feedback_arm_right | position[0-6] | ✅ 正常 | - |
| feedback_gripper_left | position[0] | ⚠️ 单位错误 | 值97.88，不是rad |
| feedback_gripper_right | position[0] | ⚠️ 单位错误 | 值97.34，不是rad |
| feedback_torso | position[0-2] | ✅ 正常 | - |
| feedback_torso | position[3] | ❌ 全为0 | 可能无效 |
| feedback_chassis | position[0-2] | ❌ 全为0 | 无效数据 |
| imu_chassis | acceleration | ✅ 正常 | - |
| imu_chassis | gyro | ✅ 正常 | - |
| imu_torso | acceleration | ✅ 正常 | - |
| imu_torso | gyro | ✅ 正常 | - |
| target_arm_left | position[0-5] | ✅ 正常 | - |
| target_arm_right | position[0-5] | ✅ 正常 | - |
| target_gripper_left | position[0] | ⚠️ 单位错误 | 值100.0，不是rad |
| target_gripper_right | position[0] | ⚠️ 单位错误 | 值100.0，不是rad |
| target_speed_chassis | twist | ✅ 正常 | 当前帧全0（可能是静止） |
| target_speed_torso | twist | ✅ 正常 | 当前帧全0（可能是静止） |

---

## 🎯 优先级修正建议

### 🔴 Critical（必须修正）
1. **Gripper单位确认和修正**
   - 确认实际单位（pct/deg/mm/rad？）
   - 修改配置文件中的字段后缀
   - 如果需要，添加单位转换

### 🟡 High（强烈建议修正）
2. **Chassis position全0问题**
   - 确认是否应该用velocity代替position
   - 或者标记为可选/禁用

3. **Torso第4个关节全0**
   - 验证其他episode是否也是全0
   - 如果是，修改配置只用前3个关节

### 🟢 Low（可选）
4. **IMU Orientation未使用**
   - 评估是否需要姿态信息
   - 如果不需要，保持当前配置

---

## 📝 下一步行动

### 1. 立即行动
- [ ] 确认gripper的实际单位
- [ ] 检查其他episode的torso[3]和chassis position
- [ ] 运行配置验证工具确认数据质量

### 2. 修正配置
- [ ] 修改gripper字段命名
- [ ] 决定是否移除torso[3]
- [ ] 处理chassis position问题

### 3. 验证
- [ ] 使用修正后的配置运行测试转换
- [ ] 检查转换后的数据是否合理

---

## 📞 需要确认的问题

1. **Gripper单位是什么？**
   - [ ] 百分比（0-100%）
   - [ ] 角度（degree）
   - [ ] 距离（mm/m）
   - [ ] 其他？

2. **Chassis position为什么全是0？**
   - [ ] 正常（底盘不记录累积位置）
   - [ ] Bug（应该有数据但是没有）
   - [ ] 应该用velocity代替

3. **Torso第4个关节是否有效？**
   - [ ] 有效（当前刚好是0）
   - [ ] 无效（应该只用前3个）
   - [ ] 需要检查更多episode

---

## 🔗 相关文档
- 配置文件: `converter_config_galaxea_r1_lite.yaml`
- 分析报告: `GALAXEA_R1_LITE_CONFIG_ANALYSIS.md`
- 修正总结: `GALAXEA_R1_LITE_FIX_SUMMARY.md`

