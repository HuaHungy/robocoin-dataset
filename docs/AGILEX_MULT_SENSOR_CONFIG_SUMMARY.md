# Agilex Mult_Sensor 配置完善总结

## 数据集信息
- **路径**: `data/agilex_cobot_decoupled_magic:mult_sensor/`
- **格式**: JPG+JSON (使用 `lerobot_format_converter_jpg_json.py`)
- **Episode**: episode1 (2243帧 joint data, 336帧 images)

---

## 📊 数据结构

### 目录结构
```
episode1/
├── arm/
│   ├── jointState/
│   │   ├── masterLeft/    (2243 JSON files) - ⚠️ 全是常量
│   │   ├── masterRight/   (2239 JSON files)
│   │   ├── puppetLeft/    (2243 JSON files) - ⚠️ 前4维常量
│   │   └── puppetRight/   (2240 JSON files) - ✅ 有效数据
│   └── endPose/
├── camera/
│   ├── color/             (front, left, right - 各336张)
│   └── depth/             (front, left, right - 各336张)
├── localization/
│   └── pose/
│       ├── puppetLeft/    (2242 JSON files)
│       └── puppetRight/   (2240 JSON files)
├── gripper/
├── imu/
├── robotBase/
└── lidar/
```

### Joint State数据格式
```json
{
  "effort": [0, 0, 0, 0, 0, 0, 0],           // 7维，全零
  "position": [-0.135, 0.005, 0.037, ...],  // 7维 (6关节 + 1gripper)
  "velocity": [-0.003, 0.011, 0, ...]       // 7维
}
```

### Localization数据格式
```json
{
  "x": 0.053219,
  "y": -0.011055,
  "z": 0.164013,
  "roll": -2.4368,
  "pitch": 1.2424,
  "yaw": -2.5879
}
```

---

## ⚠️ 配置文件问题与修复

### 问题1: Joint索引从0开始 ❌
**旧配置**:
```yaml
- names:
    - puppet_left_joint_0
    - puppet_left_joint_1
    - puppet_left_joint_2
    ...
```

**新配置** ✅:
```yaml
- names:
    - puppet_left_arm_joint_1_rad
    - puppet_left_arm_joint_2_rad
    - puppet_left_arm_joint_3_rad
    ...
```

**改动**:
- ✅ 索引从1开始（符合标准）
- ✅ 添加 `_arm_` 中缀
- ✅ 添加单位后缀 `_rad`

---

### 问题2: Gripper命名缺少单位 ❌
**旧配置**:
```yaml
- names:
    - puppet_left_gripper
```

**新配置** ✅:
```yaml
- names:
    - puppet_left_gripper_open_rad  # 范围: [-0.00028, 0.00007] rad
```

**改动**:
- ✅ 添加 `_open_rad` 后缀
- ✅ 与其他数据集命名统一

---

### 问题3: Pose命名不规范 ❌
**旧配置**:
```yaml
- names:
    - puppet_left_pose_x
    - puppet_left_pose_y
    - puppet_left_pose_z
    - puppet_left_pose_roll
    - puppet_left_pose_pitch
    - puppet_left_pose_yaw
```

**新配置** ✅:
```yaml
# 位置 (3维)
- names:
    - puppet_left_eef_pos_x_m
    - puppet_left_eef_pos_y_m
    - puppet_left_eef_pos_z_m

# 姿态 (3维)
- names:
    - puppet_left_eef_rot_euler_roll_rad
    - puppet_left_eef_rot_euler_pitch_rad
    - puppet_left_eef_rot_euler_yaw_rad
```

**改动**:
- ✅ 拆分为 `_eef_pos_*_m` (位置) 和 `_eef_rot_euler_*_rad` (姿态)
- ✅ 明确单位：米(m) 和 弧度(rad)
- ✅ 与其他数据集命名一致

---

## 📐 最终维度统计

### Observation.State: 26维
```
puppet_left_arm_joint_{1-6}_rad         6维
puppet_left_gripper_open_rad            1维
puppet_right_arm_joint_{1-6}_rad        6维
puppet_right_gripper_open_rad           1维
puppet_left_eef_pos_{x,y,z}_m           3维
puppet_left_eef_rot_euler_{roll,pitch,yaw}_rad  3维
puppet_right_eef_pos_{x,y,z}_m          3维
puppet_right_eef_rot_euler_{roll,pitch,yaw}_rad 3维
────────────────────────────────────────
Total                                   26维
```

### Action: 26维 (与State相同)
- 使用 `timeline_offset: 1` 
- 直接使用 puppet 数据（无 master 数据）

### Images: 6个
- **RGB**: camera_front_rgb, camera_left_rgb, camera_right_rgb
- **Depth**: camera_front_depth, camera_left_depth, camera_right_depth

---

## 🔍 数据质量分析

### PuppetLeft (左臂)
| 维度 | min | max | 状态 |
|------|-----|-----|------|
| Dim[0] | -0.135645 | -0.135645 | ⚠️ 常量 |
| Dim[1] | 0.005320 | 0.005320 | ⚠️ 常量 |
| Dim[2] | 0.037243 | 0.037243 | ⚠️ 常量 |
| Dim[3] | -0.141820 | -0.141820 | ⚠️ 常量 |
| Dim[4] | 0.295728 | 0.311655 | ✅ 有数据 (std=0.0003) |
| Dim[5] | -0.070892 | -0.070648 | ✅ 有数据 (std=0.000005) |
| **Dim[6]** | -0.000280 | 0.000070 | ✅ Gripper (几乎不动) |

**结论**: 左臂大部分关节固定，仅第5、6关节和gripper有微小运动

### PuppetRight (右臂)
| 维度 | min | max | unique | 状态 |
|------|-----|-----|--------|------|
| Dim[0] | 0.011321 | 0.624024 | 372 | ✅ 有效 |
| Dim[1] | -0.035952 | 2.079185 | 1023 | ✅ 有效 |
| Dim[2] | -1.942895 | 0.040906 | 552 | ✅ 有效 |
| Dim[3] | -0.115235 | 0.749848 | 779 | ✅ 有效 |
| Dim[4] | -0.428041 | 1.306939 | 947 | ✅ 有效 |
| Dim[5] | -0.793842 | 0.194902 | 794 | ✅ 有效 |
| **Dim[6]** | -0.000420 | 0.064190 | 239 | ✅ Gripper |

**结论**: 右臂所有关节都有丰富的运动数据

### MasterLeft & MasterRight
- **MasterLeft**: 全7维都是常量 ⚠️
- **MasterRight**: (未在当前分析中检查)

**结论**: 该数据集可能不是传统遥操作，或仅使用右臂主控

---

## ✅ 字段命名规范检查

| 检查项 | 状态 | 详情 |
|--------|------|------|
| Joint索引从1开始 | ✅ | `*_joint_1_rad` ... `*_joint_6_rad` |
| Gripper独立 | ✅ | `*_gripper_open_rad` |
| 末端位置 | ✅ | `*_eef_pos_x_m`, `*_eef_pos_y_m`, `*_eef_pos_z_m` |
| 末端姿态 | ✅ | `*_eef_rot_euler_roll_rad`, `*_eef_rot_euler_pitch_rad`, `*_eef_rot_euler_yaw_rad` |
| 单位后缀 | ✅ | `_rad`, `_m` |
| 命名一致性 | ✅ | 与其他数据集统一 |

---

## 📝 配置文件

**路径**: `scripts/format_converters/tolerobot/configs/converter_config_agilex_cobot_decoupled_magic_mult_sensor.yaml`

**转换器**: `lerobot_format_converter_jpg_json.py`

**FPS**: 50

---

## 🎯 下一步

1. ⏳ 测试配置文件（小样本转换）
2. ⏳ 验证图像加载（RGB + Depth）
3. ⏳ 确认帧数对齐（joint: 2243, image: 336）
4. ⏳ 检查 timeline_offset 逻辑

---

## 📚 相关数据集对比

| 数据集 | Joint命名 | Gripper命名 | Pose命名 |
|--------|-----------|-------------|----------|
| **mult_sensor** | `*_arm_joint_1_rad` ✅ | `*_gripper_open_rad` ✅ | `*_eef_pos_*_m`, `*_eef_rot_euler_*_rad` ✅ |
| masterpuppet | `*_arm_joint_1_rad` ✅ | `*_gripper_open_rad` ✅ | `*_eef_pose_1` ... |
| h5_mp4 | `*_arm_joint_1_rad` ✅ | `*_gripper_open_rad` ✅ | N/A |

**命名统一度**: 🟢 **优秀**

---

## 总结

| 项目 | 状态 |
|------|------|
| ✅ 数据结构分析 | 完成 |
| ✅ Joint命名修正 | 完成 (0→1索引) |
| ✅ Gripper命名修正 | 完成 (添加_open_rad) |
| ✅ Pose命名修正 | 完成 (拆分pos/rot + 单位) |
| ✅ 字段命名规范 | 完成 |
| ⏳ 配置测试 | 待执行 |

**配置质量**: 🟢 **优秀** - 命名规范，可用于测试

