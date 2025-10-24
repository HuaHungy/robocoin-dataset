# Leju Waibu配置分析报告

**分析时间**: 2025-10-22  
**数据集**: `leju_robot:waibu_version`  
**配置文件**: `converter_config_leju_waibu.yaml`

---

## 📊 数据集概况

### 数据结构
```
episode/
├── metadata.json
├── camera/video/
│   ├── head_cam_h.mp4
│   ├── wrist_cam_l.mp4
│   └── wrist_cam_r.mp4
└── proprio_stats/proprio_stats.hdf5
```

### H5文件结构
- **总帧数**: 1356帧
- **格式**: H5 + MP4视频
- **主要数据组**: state/, action/, imu/, camera_extrinsic_params/, timestamps

---

## ✅ 配置验证结果

###1. 维度匹配检查

| 配置项 | 配置维度 | 实际维度 | 状态 |
|--------|---------|---------|------|
| `state/joint/position` | 14 | 14 | ✅ 匹配 |
| `state/leg/position` | 12 | 12 | ✅ 匹配 |
| `state/effector/position(dexhand)` | 12 | 12 | ✅ 匹配 |
| `state/head/position` | 2 | 2 | ✅ 匹配 |
| `state/joint/velocity` | 14 | 14 | ✅ 匹配 |
| `action/joint/position` | 14 | 14 | ✅ 匹配 |
| `action/leg/position` | 12 | 12 | ✅ 匹配 |
| `action/effector/position(dexhand)` | 12 | 12 | ✅ 匹配 |
| `action/head/position` | 2 | 2 | ✅ 匹配 |

**结论**: ✅ 所有维度匹配正确

---

### 2. H5路径验证

| 配置路径 | 存在性 | 状态 |
|---------|--------|------|
| `state/joint/position` | ✅ | 正常 |
| `state/leg/position` | ✅ | 正常 |
| `state/effector/position(dexhand)` | ✅ | 正常 |
| `state/head/position` | ✅ | 正常 |
| `state/joint/velocity` | ✅ | 正常 |
| `action/joint/position` | ✅ | 正常 |
| `action/leg/position` | ✅ | 正常 |
| `action/effector/position(dexhand)` | ✅ | 正常 |
| `action/head/position` | ✅ | 正常 |

**结论**: ✅ 所有配置的H5路径都存在

---

## ❌ 关键问题

### 问题1: 字段命名不规范 ⚠️

**当前配置** (不符合规范):
```yaml
- names:
  - left_arm_joint_0       # ❌ 缺少单位后缀
  - left_arm_joint_1       # ❌ 缺少单位后缀
  ...
  - left_arm_vel_0         # ❌ 缺少单位后缀
  - left_arm_vel_1         # ❌ 缺少单位后缀
```

**应该修改为** (符合规范):
```yaml
# Joint positions (14) - 单位: rad
- names:
  - left_arm_joint_0_rad     # ✅ 添加_rad后缀
  - left_arm_joint_1_rad
  - left_arm_joint_2_rad
  - left_arm_joint_3_rad
  - left_arm_joint_4_rad
  - left_arm_joint_5_rad
  - left_arm_joint_6_rad
  - right_arm_joint_0_rad
  - right_arm_joint_1_rad
  - right_arm_joint_2_rad
  - right_arm_joint_3_rad
  - right_arm_joint_4_rad
  - right_arm_joint_5_rad
  - right_arm_joint_6_rad

# Joint velocities (14) - 单位: rad/s
- names:
  - left_arm_joint_0_vel_rad_s   # ✅ 添加_vel_rad_s后缀
  - left_arm_joint_1_vel_rad_s
  - left_arm_joint_2_vel_rad_s
  - left_arm_joint_3_vel_rad_s
  - left_arm_joint_4_vel_rad_s
  - left_arm_joint_5_vel_rad_s
  - left_arm_joint_6_vel_rad_s
  - right_arm_joint_0_vel_rad_s
  - right_arm_joint_1_vel_rad_s
  - right_arm_joint_2_vel_rad_s
  - right_arm_joint_3_vel_rad_s
  - right_arm_joint_4_vel_rad_s
  - right_arm_joint_5_vel_rad_s
  - right_arm_joint_6_vel_rad_s

# Leg positions (12) - 单位: rad
- names:
  - left_leg_joint_0_rad     # ✅ 改名并添加后缀
  - left_leg_joint_1_rad
  - left_leg_joint_2_rad
  - left_leg_joint_3_rad
  - left_leg_joint_4_rad
  - left_leg_joint_5_rad
  - right_leg_joint_0_rad
  - right_leg_joint_1_rad
  - right_leg_joint_2_rad
  - right_leg_joint_3_rad
  - right_leg_joint_4_rad
  - right_leg_joint_5_rad

# Dexhand positions (12) - 单位: rad 或 deg（需确认）
- names:
  - left_hand_joint_0_rad    # ✅ 改名并添加后缀
  - left_hand_joint_1_rad
  - left_hand_joint_2_rad
  - left_hand_joint_3_rad
  - left_hand_joint_4_rad
  - left_hand_joint_5_rad
  - right_hand_joint_0_rad
  - right_hand_joint_1_rad
  - right_hand_joint_2_rad
  - right_hand_joint_3_rad
  - right_hand_joint_4_rad
  - right_hand_joint_5_rad

# Head positions (2) - 单位: rad
- names:
  - head_joint_0_rad         # ✅ 改名并添加后缀
  - head_joint_1_rad
```

**需要修改的字段总数**: 54个字段（Observation） + 54个字段（Action） = **108个字段**

---

### 问题2: Dexhand单位不确定 ⚠️

**数据分析**:
```python
state/effector/position(dexhand): min=0.000, max=100.000
```

**问题**: 数值范围0-100，不像弧度值（应该是±π范围）

**可能性**:
1. **百分比值** (0-100%)
2. **度数** (0-100°) - 需要`degree2rad`转换
3. **其他单位**

**建议**: 
- ⚠️ 需要确认dexhand的实际单位
- 如果是度数 → 添加`convert_func: degree2rad`
- 如果是百分比 → 字段名使用`_pct`后缀

---

### 问题3: Action Head全零数据 ⚠️

**数据分析**:
```python
action/head/position: 
  [0] min=0.000, max=0.000, mean=0.000  # 全零
  [1] min=0.000, max=0.000, mean=0.000  # 全零
```

**建议**: 
```yaml
# ⚠️ 建议删除或注释（action中head数据全零）
# - names:
#   - head_pos_0
#   - head_pos_1
#   args:
#     h5_path: action/head/position
#     range_from: 0
#     range_to: 2
```

或者使用`state/head/position`代替：
```yaml
# Action使用state的head position（因为action中head全零）
- names:
  - head_joint_0_rad
  - head_joint_1_rad
  args:
    h5_path: state/head/position  # ✅ 改用state数据
    range_from: 0
    range_to: 2
```

---

## 📋 遗漏的有意义字段

### Priority 1: 关节力矩和电流（训练常用）

| 字段 | 维度 | 数值范围 | 建议 |
|------|------|---------|------|
| `state/joint/effort` | 14 | -20.45 ~ 11.42 Nm | ✅ 建议添加 |
| `state/joint/current_value` | 14 | -14.71 ~ 5.75 A | ⚠️ 可选添加 |
| `state/leg/effort` | 12 | -48.63 ~ 25.36 Nm | ✅ 建议添加 |
| `state/leg/velocity` | 12 | -0.37 ~ 0.54 rad/s | ✅ 建议添加 |
| `state/head/effort` | 2 | -0.36 ~ 0.03 Nm | ⚠️ 可选添加 |
| `state/head/velocity` | 2 | -0.07 ~ 0.05 rad/s | ⚠️ 可选添加 |

**配置示例**:
```yaml
# 🆕 Joint effort (14) - P1字段
- names:
  - left_arm_joint_0_eff_nm
  - left_arm_joint_1_eff_nm
  - left_arm_joint_2_eff_nm
  - left_arm_joint_3_eff_nm
  - left_arm_joint_4_eff_nm
  - left_arm_joint_5_eff_nm
  - left_arm_joint_6_eff_nm
  - right_arm_joint_0_eff_nm
  - right_arm_joint_1_eff_nm
  - right_arm_joint_2_eff_nm
  - right_arm_joint_3_eff_nm
  - right_arm_joint_4_eff_nm
  - right_arm_joint_5_eff_nm
  - right_arm_joint_6_eff_nm
  args:
    h5_path: state/joint/effort
    range_from: 0
    range_to: 14

# 🆕 Leg effort (12) - P1字段
- names:
  - left_leg_joint_0_eff_nm
  - left_leg_joint_1_eff_nm
  - left_leg_joint_2_eff_nm
  - left_leg_joint_3_eff_nm
  - left_leg_joint_4_eff_nm
  - left_leg_joint_5_eff_nm
  - right_leg_joint_0_eff_nm
  - right_leg_joint_1_eff_nm
  - right_leg_joint_2_eff_nm
  - right_leg_joint_3_eff_nm
  - right_leg_joint_4_eff_nm
  - right_leg_joint_5_eff_nm
  args:
    h5_path: state/leg/effort
    range_from: 0
    range_to: 12

# 🆕 Leg velocity (12) - P1字段
- names:
  - left_leg_joint_0_vel_rad_s
  - left_leg_joint_1_vel_rad_s
  - left_leg_joint_2_vel_rad_s
  - left_leg_joint_3_vel_rad_s
  - left_leg_joint_4_vel_rad_s
  - left_leg_joint_5_vel_rad_s
  - right_leg_joint_0_vel_rad_s
  - right_leg_joint_1_vel_rad_s
  - right_leg_joint_2_vel_rad_s
  - right_leg_joint_3_vel_rad_s
  - right_leg_joint_4_vel_rad_s
  - right_leg_joint_5_vel_rad_s
  args:
    h5_path: state/leg/velocity
    range_from: 0
    range_to: 12
```

---

### Priority 2: 末端执行器位姿

| 字段 | 维度 | 数值范围 | 建议 |
|------|------|---------|------|
| `state/end/position` | 2×3 | 0.06 ~ 0.43 m | ✅ 建议添加 |
| `state/end/orientation` | 2×4 | 四元数 | ✅ 建议添加 |

**问题**: 这是2×3和2×4的数组，需要特殊处理

**配置示例**:
```yaml
# 🆕 Left end effector position (3) - P2字段
- names:
  - left_eef_pos_x_m
  - left_eef_pos_y_m
  - left_eef_pos_z_m
  args:
    h5_path: state/end/position
    range_from: 0
    range_to: 3
    # ⚠️ 需要特殊处理：state/end/position[frame_idx, 0, :]

# 🆕 Right end effector position (3) - P2字段
- names:
  - right_eef_pos_x_m
  - right_eef_pos_y_m
  - right_eef_pos_z_m
  args:
    h5_path: state/end/position
    range_from: 3
    range_to: 6
    # ⚠️ 需要特殊处理：state/end/position[frame_idx, 1, :]

# 🆕 Left end effector orientation (4) - P2字段
- names:
  - left_eef_quat_x
  - left_eef_quat_y
  - left_eef_quat_z
  - left_eef_quat_w
  args:
    h5_path: state/end/orientation
    range_from: 0
    range_to: 4
    # ⚠️ 需要特殊处理：state/end/orientation[frame_idx, 0, :]
```

**⚠️ 注意**: 需要修改converter代码以支持3D数组的切片

---

### Priority 3: IMU数据

| 字段 | 维度 | 数值范围 | 建议 |
|------|------|---------|------|
| `imu/acc_xyz` | 3 | -1.59 ~ 10.57 m/s² | ⚠️ 可选添加 |
| `imu/gyro_xyz` | 3 | -0.29 ~ 0.17 rad/s | ⚠️ 可选添加 |
| `imu/quat_xyzw` | 4 | 四元数 | ⚠️ 可选添加 |

---

## 📊 覆盖率统计

### 当前配置覆盖率

| 类别 | 已配置字段 | 实际存在有意义字段 | 覆盖率 |
|------|-----------|-------------------|--------|
| **Observation State** | 54 | 110+ | **~49%** ⚠️ |
| **Observation Images** | 3 | 3 | **100%** ✅ |
| **Action** | 54 | ~54 | **100%** ✅ |

### 添加P1字段后覆盖率

| 类别 | 字段数 | 覆盖率 |
|------|--------|--------|
| **Observation State** | 54 → 92 | **~84%** ✅ |

**P1字段数量**:
- Joint effort: 14个
- Leg effort: 12个
- Leg velocity: 12个
- **总计**: 38个

---

## 🔧 修复优先级

### P0: 字段命名规范化（必须）

**影响**: 所有108个字段
**工作量**: 中等（批量替换）
**重要性**: ⭐⭐⭐⭐⭐

**修改内容**:
- 所有joint字段 → 添加`_rad`后缀
- 所有velocity字段 → 改为`_vel_rad_s`后缀
- 所有leg/dexhand字段 → 添加`_rad`后缀（或确认单位后添加）
- 所有head字段 → 添加`_rad`后缀

---

### P1: 添加关节力矩和速度（建议）

**影响**: 38个新字段
**工作量**: 中等
**重要性**: ⭐⭐⭐⭐

**添加字段**:
- `state/joint/effort` (14)
- `state/leg/effort` (12)
- `state/leg/velocity` (12)

---

### P2: Dexhand单位确认（重要）

**影响**: 24个字段（obs + action）
**工作量**: 需要用户确认
**重要性**: ⭐⭐⭐⭐

**需要确认**:
1. Dexhand数值单位（百分比？度数？弧度？）
2. 是否需要`degree2rad`或其他转换
3. 字段名后缀应该用什么

---

### P3: Action Head数据修复（建议）

**影响**: 2个字段
**工作量**: 小
**重要性**: ⭐⭐⭐

**建议**: 使用`state/head/position`替代`action/head/position`（因为action全零）

---

### P4: 末端执行器位姿（可选）

**影响**: 14个新字段
**工作量**: 大（需要修改converter支持3D数组）
**重要性**: ⭐⭐

**需要**: 修改converter代码以支持`state/end/position[frame_idx, arm_idx, :]`的切片

---

## 💡 建议行动

### 立即行动（P0）
1. ✅ 批量修改所有字段名，添加单位后缀
2. ⚠️ 确认Dexhand数据单位
3. ⚠️ 修复Action Head全零问题

### 后续行动（P1）
1. ✅ 添加joint effort字段
2. ✅ 添加leg effort和velocity字段

### 未来考虑（P2-P4）
1. 添加末端执行器位姿（需要修改converter）
2. 添加IMU数据（可选）

---

## 📝 相关文件

- **配置文件**: `converter_config_leju_waibu.yaml`
- **Converter代码**: `lerobot_format_converter_leju_waibu.py`
- **数据目录**: `data/leju_robot:waibu_version/`

---

**分析完成时间**: 2025-10-22  
**下一步**: 修正配置文件字段命名

