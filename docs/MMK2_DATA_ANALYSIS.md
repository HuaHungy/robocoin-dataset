# MMK2 数据结构分析（2025-10-22）

## 📊 数据集概况

**Device**: discover_robotics_aitbot_mmk2  
**Version**: third_view  
**数据格式**: BSON + JPG images  
**示例**: `data/discover_robotics_aitbot_mmk2:third_view/episode_24/`

---

## 📁 文件结构

```
episode_24/
├── episode_0.bson           # 主机器人数据（臂、头、脊柱、末端执行器）
├── xhand_control_data.bson  # 手部数据（左右手各12关节）
├── camera_head/             # 头部相机图像
│   └── frame_*.jpg
├── camera_left_wrist/       # 左腕相机图像
│   └── frame_*.jpg
├── camera_right_wrist/      # 右腕相机图像
│   └── frame_*.jpg
└── camera_third_view/       # 第三人称相机图像
    └── frame_*.jpg
```

---

## 🔍 episode_0.bson 数据结构

### 整体结构
```json
{
  "id": "...",
  "timestamp": 1734076528859,
  "metadata": {...},
  "data": {
    "/observation/...": [...],
    "/action/...": [...]
  }
}
```

### Observation 字段

#### 1. Left Arm (左臂)
```python
/observation/left_arm/joint_state: [
  {
    "t": timestamp,
    "data": {
      "pos": [j1, j2, j3, j4, j5, j6],  # ✅ 配置已用
      "vel": [v1, v2, v3, v4, v5, v6],  # ❌ 配置未用
      "eff": [e1, e2, e3, e4, e5, e6]   # ❌ 配置未用
    }
  },
  ...  # 186帧
]
```

#### 2. Left Arm Pose (左臂末端姿态)
```python
/observation/left_arm/pose: [
  {
    "t": timestamp,
    "data": {
      "r": [qx, qy, qz, qw],  # ❌ 四元数，配置未用
      "t": [x, y, z]          # ❌ 位置(m)，配置未用
    }
  },
  ...
]
```

#### 3. Right Arm (右臂)
```python
/observation/right_arm/joint_state: [
  {
    "data": {
      "pos": [j1, j2, j3, j4, j5, j6],  # ✅ 配置已用
      "vel": [v1, v2, v3, v4, v5, v6],  # ❌ 配置未用
      "eff": [e1, e2, e3, e4, e5, e6]   # ❌ 配置未用
    }
  },
  ...
]
```

#### 4. Right Arm Pose (右臂末端姿态)
```python
/observation/right_arm/pose: [
  {
    "data": {
      "r": [qx, qy, qz, qw],  # ❌ 四元数，配置未用
      "t": [x, y, z]          # ❌ 位置(m)，配置未用
    }
  },
  ...
]
```

#### 5. Head (头部)
```python
/observation/head/joint_state: [
  {
    "data": {
      "pos": [j1, j2],  # ✅ 配置已用
      "vel": [v1, v2],  # ❌ 配置未用
      "eff": [e1, e2]   # ❌ 配置未用
    }
  },
  ...
]
```

#### 6. Spine (脊柱)
```python
/observation/spine/joint_state: [
  {
    "data": {
      "pos": [j1],  # ✅ 配置已用
      "vel": [v1],  # ❌ 配置未用
      "eff": [e1]   # ❌ 配置未用
    }
  },
  ...
]
```

#### 7. End Effectors (末端执行器)
```python
// ❌ 在metadata中提到，但data中未找到
/observation/left_arm_eef/joint_state
/observation/right_arm_eef/joint_state
```

### Action 字段

**重要**: Action只有`pos`字段，没有`vel`和`eff`

#### 1. Left Arm Action
```python
/action/left_arm/joint_state: [
  {
    "data": {
      "pos": [j1, j2, j3, j4, j5, j6],  # ✅ 6维（与observation相同）
      "vel": None,
      "eff": None
    }
  },
  ...
]
```

**✅ 确认**: Action的left_arm是6维（数据已验证）

#### 2. Right Arm Action
```python
/action/right_arm/joint_state: [
  {
    "data": {
      "pos": [j1, j2, j3, j4, j5, j6],  # ✅ 6维（与observation相同）
      "vel": None,
      "eff": None
    }
  },
  ...
]
```

**✅ 确认**: Action的right_arm是6维（数据已验证）

#### 3. Head & Spine Action
```python
/action/head/joint_state: [
  {"data": {"pos": [j1, j2]}}
]

/action/spine/joint_state: [
  {"data": {"pos": [j1]}}
]
```

---

## 🔍 xhand_control_data.bson 数据结构

### 整体结构
```json
{
  "frames": [
    {
      "t": 0.200,
      "observation": {
        "left_hand": [12个值],
        "right_hand": [12个值]
      },
      "action": {
        "left_hand": [12个值],
        "right_hand": [12个值]
      }
    },
    ...  // 186帧
  ]
}
```

### 数据示例
```python
observation.left_hand:  [51.56, 44.23, 0.0, 1.87, 15.58, ...]  # 12个值
observation.right_hand: [60.0, 50.25, 0.58, 0.08, 29.0, ...]   # 12个值

action.left_hand:  [0.874, 0.794, 0.039, 0.057, 0.262, ...]  # 12个值
action.right_hand: [1.041, 0.900, 0.013, 0.0, 0.505, ...]    # 12个值
```

**⚠️ 关键问题**: 
- 当前配置使用`data_path: observation.left_hand`
- **但实际数据在`frames[i].observation.left_hand`**
- 需要特殊的数据提取逻辑

---

## ❌ 配置文件遗漏的字段

### 1. Observation - 遗漏字段

| 字段路径 | 维度 | 配置状态 | 建议 |
|---------|------|---------|------|
| `left_arm/joint_state/vel` | 6 | ❌ 未配置 | 建议添加 |
| `left_arm/joint_state/eff` | 6 | ❌ 未配置 | 建议添加 |
| `left_arm/pose/r` | 4 | ❌ 未配置 | 建议添加（末端姿态四元数） |
| `left_arm/pose/t` | 3 | ❌ 未配置 | 建议添加（末端位置） |
| `right_arm/joint_state/vel` | 6 | ❌ 未配置 | 建议添加 |
| `right_arm/joint_state/eff` | 6 | ❌ 未配置 | 建议添加 |
| `right_arm/pose/r` | 4 | ❌ 未配置 | 建议添加 |
| `right_arm/pose/t` | 3 | ❌ 未配置 | 建议添加 |
| `head/joint_state/vel` | 2 | ❌ 未配置 | 可选 |
| `head/joint_state/eff` | 2 | ❌ 未配置 | 可选 |
| `spine/joint_state/vel` | 1 | ❌ 未配置 | 可选 |
| `spine/joint_state/eff` | 1 | ❌ 未配置 | 可选 |

### 2. 字段命名问题

**当前配置** (❌ 不规范):
```yaml
- names: [left_arm_joint_1, left_arm_joint_2, ...]
```

**应该是** (✅ 规范):
```yaml
- names: [left_arm_joint_1_rad, left_arm_joint_2_rad, ...]
```

**需要修改的字段**:
- 所有joint字段 → 添加`_rad`后缀
- 末端位置`t` → 添加`_m`后缀 
- 末端姿态`r` → 改名为`_quat`字段

---

## 📋 建议的配置修正

### 1. 添加遗漏的velocity字段
```yaml
# Observation - Left Arm Velocity
- names:
  - left_arm_joint_1_vel_rad_s
  - left_arm_joint_2_vel_rad_s
  - left_arm_joint_3_vel_rad_s
  - left_arm_joint_4_vel_rad_s
  - left_arm_joint_5_vel_rad_s
  - left_arm_joint_6_vel_rad_s
  args:
    bson_file: episode_0.bson
    data_path: observation/left_arm/joint_state
    field: vel
    range_from: 0
    range_to: 6
```

### 2. 添加末端姿态
```yaml
# Observation - Left Arm End Effector Position
- names:
  - left_eef_pos_x_m
  - left_eef_pos_y_m
  - left_eef_pos_z_m
  args:
    bson_file: episode_0.bson
    data_path: observation/left_arm/pose
    field: t
    range_from: 0
    range_to: 3

# Observation - Left Arm End Effector Orientation (Quaternion)
- names:
  - left_eef_quat_x
  - left_eef_quat_y
  - left_eef_quat_z
  - left_eef_quat_w
  args:
    bson_file: episode_0.bson
    data_path: observation/left_arm/pose
    field: r
    range_from: 0
    range_to: 4
```

### 3. ~~修正Action维度~~ (已验证：维度正确)
```yaml
# Action - Left Arm (✅ 6维，与observation相同)
- names:
  - left_arm_action_1_rad
  - left_arm_action_2_rad
  - left_arm_action_3_rad
  - left_arm_action_4_rad
  - left_arm_action_5_rad
  - left_arm_action_6_rad
  args:
    bson_file: episode_0.bson
    data_path: action/left_arm/joint_state
    field: pos
    range_from: 0
    range_to: 6  # ✅ 6维（数据已验证）
```

---

## 🎯 优先修正清单

### P0 - Critical（必须修正）
1. ✅ 字段命名：所有joint添加`_rad`后缀
2. ✅ Action维度：left/right_arm从6改为5
3. ❌ xhand数据路径：需要特殊处理`frames`数组

### P1 - High（强烈建议）
4. ❌ 添加velocity字段（vel）
5. ❌ 添加effort字段（eff）
6. ❌ 添加末端姿态（pose/r和pose/t）

### P2 - Medium（可选）
7. ❌ 添加head/spine的vel和eff

---

## 🔧 下一步操作

1. **立即**: 修正配置文件字段命名（添加`_rad`后缀）
2. **立即**: 修正Action维度（6→5）
3. **短期**: 添加遗漏的vel、eff、pose字段
4. **中期**: 研究xhand数据的正确提取方式

---

## 📊 统计总结

| 类别 | 配置的字段数 | 实际存在的字段数 | 遗漏数 |
|------|------------|----------------|--------|
| Observation State | 16 | 50+ | 34+ |
| Observation Images | 4 | 4 | 0 |
| Action | 30 | 30 | 0 |

**遗漏率**: 约40%的observation字段未被配置！

---

**分析完成时间**: 2025-10-22  
**下一步**: 修正配置文件

