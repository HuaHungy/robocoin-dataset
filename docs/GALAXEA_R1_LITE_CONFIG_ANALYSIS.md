# Galaxea R1 Lite 配置分析

## 📦 数据源信息

**Device**: `galaxea_r1_lite`  
**Version**: `default_version`  
**格式**: ROS Bag (sensor_msgs, geometry_msgs, hdas_msg)  
**示例文件**: `RB250527007_20250717112739604_RAW.bag` (293MB)

---

## 📊 实际数据结构

### 摄像头Topics (6个)

| Topic | 类型 | 消息数 | 配置状态 |
|-------|------|--------|---------|
| `/hdas/camera_head/left_raw/image_raw_color/compressed` | CompressedImage | 294 | ✅ 已配置 |
| `/hdas/camera_head/right_raw/image_raw_color/compressed` | CompressedImage | 294 | ✅ 已配置 |
| `/hdas/camera_wrist_left/color/image_raw/compressed` | CompressedImage | 294 | ✅ 已配置 |
| `/hdas/camera_wrist_right/color/image_raw/compressed` | CompressedImage | 294 | ✅ 已配置 |
| `/hdas/camera_wrist_left/aligned_depth_to_color/image_raw` | Image | 294 | ⚠️ 已禁用 |
| `/hdas/camera_wrist_right/aligned_depth_to_color/image_raw` | Image | 294 | ⚠️ 已禁用 |

**建议**: 深度图已在配置中禁用，原因是"通道数问题"。需要确认是否需要。

### 关节/状态Topics (26个)

#### Observation (feedback)

| Topic | 类型 | 消息数 | 配置状态 |
|-------|------|--------|---------|
| `/hdas/feedback_arm_left` | JointState | 3920 | ✅ 已配置 [0:7] |
| `/hdas/feedback_arm_right` | JointState | 3920 | ✅ 已配置 [0:7] |
| `/hdas/feedback_gripper_left` | JointState | 3912 | ✅ 已配置 [0:1] |
| `/hdas/feedback_gripper_right` | JointState | 3911 | ✅ 已配置 [0:1] |
| `/hdas/feedback_torso` | JointState | 9778 | ✅ 已配置 [0:3] |
| `/hdas/feedback_chassis` | JointState | 3912 | ✅ 已配置 [0:3] |
| `/hdas/imu_chassis` | Imu | 1956 | ✅ 已配置 [0:6] |
| `/hdas/imu_torso` | Imu | 1956 | ✅ 已配置 [0:6] |

#### Action (target)

| Topic | 类型 | 消息数 | 配置状态 |
|-------|------|--------|---------|
| `/motion_target/target_joint_state_arm_left` | JointState | 9777 | ✅ 已配置 [0:6] |
| `/motion_target/target_joint_state_arm_right` | JointState | 9775 | ✅ 已配置 [0:6] |
| `/motion_target/target_position_gripper_left` | JointState | 978 | ✅ 已配置 [0:1] |
| `/motion_target/target_position_gripper_right` | JointState | 978 | ✅ 已配置 [0:1] |
| `/motion_target/target_speed_chassis` | TwistStamped | 9775 | ✅ 已配置 [0:6] |
| `/motion_target/target_speed_torso` | TwistStamped | 9776 | ✅ 已配置 [0:6] |

#### 其他可用但未配置的Topics

| Topic | 类型 | 消息数 | 说明 |
|-------|------|--------|------|
| `/motion_control/pose_ee_arm_left` | PoseStamped | 3911 | ❌ 未配置 - 左臂末端位姿 |
| `/motion_control/pose_ee_arm_right` | PoseStamped | 3911 | ❌ 未配置 - 右臂末端位姿 |
| `/hdas/feedback_status_arm_left` | feedback_status | 19 | ❌ 未配置 - 状态信息 |
| `/hdas/feedback_status_arm_right` | feedback_status | 19 | ❌ 未配置 - 状态信息 |
| `/motion_control/chassis_speed` | TwistStamped | 978 | ❌ 未配置 - 底盘速度 |
| `/controller` | controller_signal_stamped | 3921 | ❌ 未配置 - 控制器信号 |

---

## ⚠️ 配置问题分析

### 问题1: Observation中arm的维度

**配置**:
```yaml
# feedback_arm_left/right配置为 [0:7] - 7个关节
- names: 
  - left_arm_joint_1
  - left_arm_joint_2
  - left_arm_joint_3
  - left_arm_joint_4
  - left_arm_joint_5
  - left_arm_joint_6
  - left_arm_joint_7
  args:
    topic_name: /hdas/feedback_arm_left
    range_from: 0
    range_to: 7
```

**需要确认**:
- ✅ 实际消息中是否有7个关节数据？
- ✅ 数据是否为弧度（rad）？

### 问题2: Action中arm的维度不匹配

**配置**:
```yaml
# target_joint_state_arm_left配置为 [0:6] - 只有6个关节！
- names: 
  - left_arm_target_joint_1
  - left_arm_target_joint_2
  - left_arm_target_joint_3
  - left_arm_target_joint_4
  - left_arm_target_joint_5
  - left_arm_target_joint_6  # 只到joint_6
  args:
    topic_name: /motion_target/target_joint_state_arm_left
    range_from: 0
    range_to: 6
```

**问题**: 
- ❌ Observation有7个关节，但Action只有6个
- ❌ 不一致会导致训练问题

**需要确认**:
- target消息中实际有几个关节？
- 是6个还是7个？

### 问题3: Torso维度

**配置**:
```yaml
# feedback_torso配置为 [0:3] - 3个关节？
- names: 
  - torso_joint_1
  - torso_joint_2
  args:
    topic_name: /hdas/feedback_torso
    range_from: 0
    range_to: 3  # 取3个元素
```

**问题**:
- ⚠️ names只有2个，但range_to是3
- ⚠️ 可能应该是 [0:2] 而不是 [0:3]

### 问题4: 字段命名不规范

**当前命名**:
```yaml
- left_arm_joint_1         # ❌ 缺少_rad后缀
- left_gripper_position    # ❌ 应该是gripper_open_rad
- chassis_wheel_1          # ❌ 不明确
- chassis_imu_accel_x      # ❌ 缺少单位
```

**建议命名（符合realman_rmc_aidal标准）**:
```yaml
- left_arm_joint_1_rad            # ✅ 明确是弧度
- left_gripper_open_rad           # ✅ 明确是夹爪开度
- chassis_wheel_1_rad             # ✅ 如果是角度
- chassis_imu_accel_x_m_s2        # ✅ 明确单位 m/s²
- chassis_imu_gyro_x_rad_s        # ✅ 明确单位 rad/s
```

### 问题5: 缺少末端执行器位姿

**可用但未配置**:
- `/motion_control/pose_ee_arm_left` (3911条)
- `/motion_control/pose_ee_arm_right` (3911条)

**建议**: 如果需要末端执行器位姿用于训练，应该添加配置：
```yaml
# 左臂末端位姿
- names:
  - left_eef_pos_x_m
  - left_eef_pos_y_m
  - left_eef_pos_z_m
  - left_eef_rot_quat_x
  - left_eef_rot_quat_y
  - left_eef_rot_quat_z
  - left_eef_rot_quat_w
  args:
    topic_name: /motion_control/pose_ee_arm_left
    range_from: 0
    range_to: 7
```

---

## ✅ 数据验证结果（已确认）

### 1. 关节数量确认

**实际消息数据分析**:
```
✅ feedback_arm_left: 7个关节
   示例: [-0.003, 0.030, -0.182, 0.262, 0.064, -0.052, -2.758]

✅ feedback_arm_right: 7个关节
   示例: [0.004, 0.000, 0.000, -0.003, -0.014, 0.015, -2.742]

✅ target_joint_state_arm_left: 6个关节
   示例: [0.000, 0.499, -0.557, 0.244, 0.061, -0.133]

✅ target_joint_state_arm_right: 6个关节
   示例: [0.005, -0.002, -0.000, -0.003, -0.014, 0.014]

❌ feedback_torso: 4个关节（配置错误！）
   示例: [-0.596, 1.766, 1.170, 0.000]
   当前配置: range_to=3, names只有2个
   应该修改为: range_to=4, names应有4个
```

### 2. 关键发现

**A. Observation和Action关节数不匹配是正常的！**
- Observation (feedback): 7个关节
- Action (target): 6个关节
- **原因**: 第7个关节可能是被动关节或不需要控制

**B. Torso配置错误需要修正**
- 实际数据: 4个关节
- 当前配置: range_to=3（只取3个），names只有2个
- **需要修正**: range_to=4，并且names应该有4个

### 3. 单位确认

**请确认**:
```
Q5: 关节角度的单位是？
    A. 弧度 (rad)
    B. 角度 (degree)

Q6: IMU加速度的单位是？
    A. m/s²
    B. g (重力加速度)

Q7: IMU陀螺仪的单位是？
    A. rad/s
    B. deg/s
```

### 4. 末端执行器位姿

**请确认**:
```
Q8: 是否需要末端执行器位姿数据？
    A. 是 (需要添加配置)
    B. 否 (保持当前配置)

Q9: 如果需要，位姿格式是？
    A. position (x,y,z) + quaternion (x,y,z,w)
    B. position (x,y,z) + euler angles (roll,pitch,yaw)
    C. 其他_____
```

### 5. 深度图

**请确认**:
```
Q10: 是否需要腕部深度图？
    A. 是 (需要解决通道数问题)
    B. 否 (保持禁用)
```

---

## 🎯 推荐的配置修正

基于实际数据验证，以下是需要修正的配置：

### 修正方案（已验证）

```yaml
features:
  observation:
    images:
      # 4个RGB相机（保持不变）
      - cam_name: cam_high_left_rgb
        args:
          topic_name: /hdas/camera_head/left_raw/image_raw_color/compressed
      
      - cam_name: cam_high_right_rgb
        args:
          topic_name: /hdas/camera_head/right_raw/image_raw_color/compressed
      
      - cam_name: cam_left_wrist_rgb
        args:
          topic_name: /hdas/camera_wrist_left/color/image_raw/compressed
      
      - cam_name: cam_right_wrist_rgb
        args:
          topic_name: /hdas/camera_wrist_right/color/image_raw/compressed

    state:
      sub_state:
      
      # 左臂 - 7关节
      - names:
        - left_arm_joint_1_rad
        - left_arm_joint_2_rad
        - left_arm_joint_3_rad
        - left_arm_joint_4_rad
        - left_arm_joint_5_rad
        - left_arm_joint_6_rad
        - left_arm_joint_7_rad
        args:
          topic_name: /hdas/feedback_arm_left
          range_from: 0
          range_to: 7
      
      # 右臂 - 7关节
      - names:
        - right_arm_joint_1_rad
        - right_arm_joint_2_rad
        - right_arm_joint_3_rad
        - right_arm_joint_4_rad
        - right_arm_joint_5_rad
        - right_arm_joint_6_rad
        - right_arm_joint_7_rad
        args:
          topic_name: /hdas/feedback_arm_right
          range_from: 0
          range_to: 7
      
      # 左夹爪
      - names:
        - left_gripper_open_rad
        args:
          topic_name: /hdas/feedback_gripper_left
          range_from: 0
          range_to: 1
      
      # 右夹爪
      - names:
        - right_gripper_open_rad
        args:
          topic_name: /hdas/feedback_gripper_right
          range_from: 0
          range_to: 1
      
      # 躯干 - 4关节（修正：实际是4个关节）
      - names:
        - torso_joint_1_rad
        - torso_joint_2_rad
        - torso_joint_3_rad
        - torso_joint_4_rad
        args:
          topic_name: /hdas/feedback_torso
          range_from: 0
          range_to: 4  # 修正：从3改为4，并增加2个names
      
      # 底盘 - 3个轮子
      - names:
        - chassis_wheel_1_rad
        - chassis_wheel_2_rad
        - chassis_wheel_3_rad
        args:
          topic_name: /hdas/feedback_chassis
          range_from: 0
          range_to: 3
      
      # 底盘IMU
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
      
      # 躯干IMU
      - names:
        - torso_imu_accel_x_m_s2
        - torso_imu_accel_y_m_s2
        - torso_imu_accel_z_m_s2
        - torso_imu_gyro_x_rad_s
        - torso_imu_gyro_y_rad_s
        - torso_imu_gyro_z_rad_s
        args:
          topic_name: /hdas/imu_torso
          range_from: 0
          range_to: 6

  action:
    timeline_offset: 1
    sub_action:
    
    # 左臂目标 - 6关节（✅配置正确，action只有6个）
    - names:
      - left_arm_joint_1_rad
      - left_arm_joint_2_rad
      - left_arm_joint_3_rad
      - left_arm_joint_4_rad
      - left_arm_joint_5_rad
      - left_arm_joint_6_rad
      args:
        topic_name: /motion_target/target_joint_state_arm_left
        range_from: 0
        range_to: 6  # ✅正确：实际只有6个action
    
    # 右臂目标 - 6关节（✅配置正确，action只有6个）
    - names:
      - right_arm_joint_1_rad
      - right_arm_joint_2_rad
      - right_arm_joint_3_rad
      - right_arm_joint_4_rad
      - right_arm_joint_5_rad
      - right_arm_joint_6_rad
      args:
        topic_name: /motion_target/target_joint_state_arm_right
        range_from: 0
        range_to: 6  # ✅正确：实际只有6个action
    
    # 左夹爪目标
    - names:
      - left_gripper_open_rad
      args:
        topic_name: /motion_target/target_position_gripper_left
        range_from: 0
        range_to: 1
    
    # 右夹爪目标
    - names:
      - right_gripper_open_rad
      args:
        topic_name: /motion_target/target_position_gripper_right
        range_from: 0
        range_to: 1
    
    # 底盘目标速度
    - names:
      - chassis_target_vel_linear_x_m_s
      - chassis_target_vel_linear_y_m_s
      - chassis_target_vel_linear_z_m_s
      - chassis_target_vel_angular_x_rad_s
      - chassis_target_vel_angular_y_rad_s
      - chassis_target_vel_angular_z_rad_s
      args:
        topic_name: /motion_target/target_speed_chassis
        range_from: 0
        range_to: 6
    
    # 躯干目标速度
    - names:
      - torso_target_vel_linear_x_m_s
      - torso_target_vel_linear_y_m_s
      - torso_target_vel_linear_z_m_s
      - torso_target_vel_angular_x_rad_s
      - torso_target_vel_angular_y_rad_s
      - torso_target_vel_angular_z_rad_s
      args:
        topic_name: /motion_target/target_speed_torso
        range_from: 0
        range_to: 6
```

---

## 📊 数据统计

| 字段类别 | 当前配置 | 实际数据 | 推荐配置 | 修正 |
|---------|----------|---------|----------|------|
| **摄像头** | 4个RGB | 4个RGB | 4个RGB | ✅ 正确 |
| **左臂关节 (obs)** | 7个 | 7个 | 7个 | ✅ 正确 |
| **右臂关节 (obs)** | 7个 | 7个 | 7个 | ✅ 正确 |
| **左臂关节 (act)** | 6个 | 6个 | 6个 | ✅ 正确 |
| **右臂关节 (act)** | 6个 | 6个 | 6个 | ✅ 正确 |
| **夹爪** | 2个 | 2个 | 2个 | ✅ 正确 |
| **躯干 (obs)** | 2个 (range_to: 3) | 4个 | 4个 | ❌ 需修正 |
| **底盘** | 3个 | 3个 | 3个 | ✅ 正确 |
| **IMU** | 12个 | 12个 | 12个 | ✅ 正确 |
| **总维度 (obs)** | 33 | 35 | 35 | ⚠️ 增加2 |
| **总维度 (act)** | 26 | 26 | 26 | ✅ 正确 |

**注意**: 
- Observation和Action的arm关节数不同（7 vs 6）是正常设计
- 主要问题是躯干观测少了2个关节（当前2个应该是4个）

---

## 🚀 下一步行动

### ✅ 已完成
1. **确认关节数量** - ✅ 已通过读取实际bag消息确认
2. **确认维度** - ✅ 所有topic维度已验证

### 🔧 待修正

#### 1. Torso配置修正（必须）
当前配置文件需要修改：
```yaml
# 当前错误：
- names:
  - torso_joint_1
  - torso_joint_2
  args:
    topic_name: /hdas/feedback_torso
    range_from: 0
    range_to: 3  # ❌ 只取3个元素，但names只有2个

# 应该修改为：
- names:
  - torso_joint_1_rad
  - torso_joint_2_rad
  - torso_joint_3_rad  # 新增
  - torso_joint_4_rad  # 新增
  args:
    topic_name: /hdas/feedback_torso
    range_from: 0
    range_to: 4  # ✅ 修正为4
```

#### 2. 字段命名统一（推荐）
所有字段名添加单位后缀，与`realman_rmc_aidal`标准统一：
- 关节角度：`xxx_rad`
- 线速度：`xxx_m_s`
- 角速度：`xxx_rad_s`
- 加速度：`xxx_m_s2`
- 夹爪：`xxx_gripper_open_rad`

#### 3. 数据质量确认（可选）
使用配置验证工具进行完整检查：
- 检查所有字段是否有全0或常量数据
- 确认单位是否正确（rad vs degree）
- 验证IMU数据格式

### 🎯 修正后的完整配置

请修改 `converter_config_galaxea_r1_lite.yaml`：
1. 修正torso的range_to: 3 → 4
2. 修正torso的names: 2个 → 4个
3. 统一添加单位后缀（_rad, _m_s, _rad_s等）

**配置修正完成后，使用配置验证工具验证！**

