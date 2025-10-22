# H5格式数据集批量分析报告

**生成时间**: 2025-10-22  
**分析范围**: Agilex MasterPuppet + Realman Default + Zhipingfang 8个版本  
**使用Converter**: `lerobot_format_converter_h5.py`

---

## 📊 总体概况

### 分析成功/失败统计

| 数据集 | 状态 | 原因 | Groups | Datasets |
|--------|------|------|---------|----------|
| **agilex_cobot_decoupled_magic:masterpuppet_version** | ❌ 失败 | 文件损坏 ("bad object header version number") | - | - |
| **realman_rmc_aidal:default_version** | ✅ 成功 | - | 2 | 5 |
| **zhipingfang:dual_arm_no_pose** | ✅ 成功 | - | 25 | 52 |
| **zhipingfang:dual_arm_no_pose_compressed_video** | ✅ 成功 | - | 25 | 52 |
| **zhipingfang:dual_arm_with_pose** | ✅ 成功 | - | 25 | 52 |
| **zhipingfang:dual_arm_with_pose_compressed_video** | ✅ 成功 | - | 25 | 52 |
| **zhipingfang:dual_arm_with_pose_no_left_chest_cam** | ✅ 成功 | - | 25 | 52 |
| **zhipingfang:left_arm_with_pose** | ✅ 成功 | - | 25 | 52 |
| **zhipingfang:right_arm_with_pose** | ✅ 成功 | - | 25 | 52 |

**成功率**: 8/9 (88.89%)

---

## 🔍 Part 1: Realman RMC Aidal (default_version)

### 基本信息
- **文件**: `episode_103.hdf5`
- **大小**: 55.58 MB
- **帧数**: 423帧
- **结构**: 极简（2 Groups, 5 Datasets）

### H5结构

```
/
├── action [Dataset] (423, 128) float32
│   └── ⚠️ 数据质量: 74.22% 全零
│
└── observations/
    ├── images/
    │   ├── cam_high [Dataset] (423,) object
    │   ├── cam_left_wrist [Dataset] (423,) object
    │   └── cam_right_wrist [Dataset] (423,) object
    │
    └── qpos [Dataset] (423, 128) float32
        └── ⚠️ 数据质量: 74.22% 全零（与action一致）
```

### 数据质量问题

1. **✅ 核心数据正常**:
   - `observations/qpos`: (423, 128) - 关节位置数据
   - `action`: (423, 128) - 动作数据
   - 范围: -2.64 ~ 886.0
   
2. **⚠️ 严重问题**:
   - **74.22%的数据为零** - 这意味着128维中约95维都是零
   - 需要确认哪些维度是有效的，哪些维度未使用

3. **✅ 图像数据**:
   - 3个相机: `cam_high`, `cam_left_wrist`, `cam_right_wrist`
   - 存储为object类型（可能是压缩的图像bytes）

### 配置需求

❗ **这个版本尚未有配置文件！需要创建。**

**维度分析建议**:
1. 检查128维中哪些维度有有效数据（非零）
2. 可能的分布：
   - Left arm: 7 joints
   - Right arm: 7 joints
   - Left gripper: 1-2 dims
   - Right gripper: 1-2 dims
   - 其他传感器数据（6-force, eef pose等）
   - **大量未使用的填充维度**（导致74%全零）

---

## 🔍 Part 2: Zhipingfang数据集家族

### 概览

| 版本 | 文件大小 | 帧数 | Left Arm | Right Arm | Cameras | 特点 |
|------|---------|------|----------|-----------|---------|------|
| **dual_arm_no_pose** | 308 MB | 686 | ✅ 有 | ✅ 有 | 4 (RGB+Depth) | 无pose数据 |
| **dual_arm_no_pose_compressed** | 6.6 MB | 292 | ✅ 有 | ✅ 有 | 4 (视频压缩) | 压缩视频 + Chassis有数据 |
| **dual_arm_with_pose** | 165 MB | 461 | ✅ 有 | ✅ 有 | 4 (RGB+Depth) | 有pose数据 |
| **dual_arm_with_pose_compressed** | 4.4 MB | 179 | ✅ 有 | ✅ 有 | 4 (视频压缩) | 压缩视频 + Chassis空 |
| **dual_arm_with_pose_no_left_chest_cam** | 24 MB | 127 | ❌ **全零** | ✅ 有 | 2 (Head+Right) | **左臂数据全零** |
| **left_arm_with_pose** | 27 MB | 99 | ✅ 有 | ❌ 空 | 2 (Head+Left) | 只有左臂 |
| **right_arm_with_pose** | 30 MB | 169 | ❌ **全零** | ✅ 有 | 2 (Head+Right) | **左臂数据全零** |

### 共同结构 (所有zhipingfang版本)

```
/
├── action/ (或 actions/) [Group]  # 空group，数据可能在别处
│
├── infos/ [Group]
│   ├── camera_params/
│   │   ├── chest [Dataset] - 相机内参
│   │   ├── head [Dataset]
│   │   ├── left [Dataset]
│   │   └── right [Dataset]
│   └── task_info/
│       ├── collection_frequency [Dataset] - 采集频率
│       ├── task_name [Dataset] - 任务名称
│       └── total_frames [Dataset] - 总帧数
│
└── observations/ [Group]
    ├── arm/
    │   ├── left/
    │   │   ├── joints [Dataset] (N, 7) float64 - 关节角度
    │   │   ├── pose [Dataset] (N, 6) float64 - 末端执行器姿态
    │   │   └── wrench [Dataset] (N, 6) float64 - 力/力矩（⚠️ 全零）
    │   └── right/
    │       ├── joints [Dataset] (N, 7)
    │       ├── pose [Dataset] (N, 6)
    │       └── wrench [Dataset] (N, 6) ⚠️ 全零
    │
    ├── camera/
    │   ├── rgb/
    │   │   ├── chest/ (images/video/video_index)
    │   │   ├── head/
    │   │   ├── left/
    │   │   └── right/
    │   └── depth/
    │       ├── chest/ (images/video/video_index)
    │       ├── head/
    │       ├── left/
    │       └── right/
    │
    ├── chassis/
    │   ├── pose [Dataset] (N, 3) - x, y, theta
    │   ├── status [Dataset] (N, 4) - 底盘状态（⚠️ 大多全零）
    │   └── vel [Dataset] (N, 3) - 速度（⚠️ 大多全零）
    │
    ├── effector/ (末端执行器/夹爪)
    │   ├── left/
    │   │   ├── dof_num [Dataset] () - 自由度数
    │   │   ├── position [Dataset] (N, 1 或 N, 1000) - 夹爪位置
    │   │   └── type [Dataset] () - 执行器类型
    │   └── right/
    │       ├── dof_num [Dataset]
    │       ├── position [Dataset] (N, 1)
    │       └── type [Dataset]
    │
    ├── neck/
    │   ├── joints [Dataset] (N, 2) - 颈部关节（⚠️ 大多全零）
    │   └── pose [Dataset] - 颈部姿态
    │
    ├── timestamp [Dataset] (N, 1) - 时间戳
    │
    └── torso/ (躯干)
        ├── joints [Dataset] (N, 4) - 躯干关节
        ├── pose [Dataset] (N, 4) - 躯干姿态
        └── state [Dataset] - 躯干状态
```

### 数据质量问题汇总

#### ✅ 正常数据字段

| 字段 | 维度 | 说明 |
|------|------|------|
| `observations/arm/left/joints` | (N, 7) | 左臂关节角度 |
| `observations/arm/right/joints` | (N, 7) | 右臂关节角度 |
| `observations/arm/left/pose` | (N, 6) | 左臂末端姿态 (仅with_pose版本) |
| `observations/arm/right/pose` | (N, 6) | 右臂末端姿态 (仅with_pose版本) |
| `observations/effector/left/position` | (N, 1) | 左夹爪位置 |
| `observations/effector/right/position` | (N, 1) | 右夹爪位置 |
| `observations/timestamp` | (N, 1) | 时间戳 |

#### ⚠️ 全零/常量字段（不建议使用）

| 字段 | 问题 | 影响版本 |
|------|------|----------|
| `observations/arm/*/wrench` | ❌ **100% 全零** | **所有版本** |
| `observations/chassis/pose` | ❌ **全零** | dual_arm_no_pose, dual_arm_with_pose |
| `observations/chassis/status` | ❌ **全零** | **所有版本** |
| `observations/chassis/vel` | ❌ **全零** | **所有版本** |
| `observations/neck/joints` | ❌ **全零** | dual_arm_no_pose, dual_arm_with_pose |
| `observations/torso/joints` | ❌ **全零** | dual_arm_no_pose, dual_arm_with_pose |
| `observations/torso/pose` | ❌ **全零** | dual_arm_no_pose, dual_arm_with_pose |

#### 🔧 特殊问题

1. **left_arm_with_pose版本**:
   - ⚠️ `observations/effector/left/position` 维度异常：**(N, 1000)**
   - 正常版本是 (N, 1)
   - 这1000维中99.95%全零，应该只使用第1维

2. **dual_arm_with_pose_no_left_chest_cam版本**:
   - ❌ **左臂所有数据全零**：
     - `observations/arm/left/joints` 全零
     - `observations/arm/left/pose` 全零
     - `observations/effector/left/position` 全零
   - 这个版本实际只有右臂数据

3. **right_arm_with_pose版本**:
   - ❌ **左臂所有数据全零** (与上面类似)
   - 只有右臂数据有效

4. **压缩视频版本 (compressed_video)**:
   - ✅ 使用压缩视频存储，文件大小显著减小
   - 格式: `video` (scalar, void类型) + `video_index` (帧索引)
   - `no_pose_compressed`: Chassis有数据
   - `with_pose_compressed`: Chassis/Neck/Torso全部为空 (shape=(0,))

---

## 📋 配置文件需求

### 1. Realman Default Version

❗ **需要创建新配置**: `converter_config_realman_rmc_aidal_default.yaml`

**关键问题**:
- 确认128维中哪些维度有效（目前74%全零）
- 需要数据提供方确认维度映射

**建议维度分配** (需验证):
```yaml
observation:
  state:
    sub_state:
      # 假设前30维是有效数据 (需验证)
      - names: [left_arm_joint_1_rad, ..., left_arm_joint_7_rad]
        args: {h5_path: "observations/qpos", range_from: 0, range_to: 7}
      - names: [right_arm_joint_1_rad, ..., right_arm_joint_7_rad]
        args: {h5_path: "observations/qpos", range_from: 7, range_to: 14}
      - names: [left_gripper_rad]
        args: {h5_path: "observations/qpos", range_from: 14, range_to: 15}
      - names: [right_gripper_rad]
        args: {h5_path: "observations/qpos", range_from: 15, range_to: 16}
      # ... 其他有效维度 (需确认)
```

### 2. Zhipingfang版本

#### 需要创建的配置文件

| 版本 | 配置文件名 | 优先级 | 特殊处理 |
|------|-----------|--------|----------|
| dual_arm_no_pose | `converter_config_zhipingfang_dual_arm_no_pose.yaml` | 🔥 高 | 排除depth |
| dual_arm_no_pose_compressed | `converter_config_zhipingfang_dual_arm_no_pose_compressed.yaml` | 🔥 高 | use_compressed_video=true |
| dual_arm_with_pose | `converter_config_zhipingfang_dual_arm_with_pose.yaml` | 🔥 高 | 包含pose字段 + 排除depth |
| dual_arm_with_pose_compressed | `converter_config_zhipingfang_dual_arm_with_pose_compressed.yaml` | 🔥 高 | pose + compressed |
| dual_arm_with_pose_no_left_chest_cam | `converter_config_zhipingfang_dual_arm_with_pose_no_left_chest_cam.yaml` | 中 | **排除左臂** + 排除chest cam |
| left_arm_with_pose | `converter_config_zhipingfang_left_arm_with_pose.yaml` | 中 | **只保留左臂** + effector[0:1] |
| right_arm_with_pose | `converter_config_zhipingfang_right_arm_with_pose.yaml` | 中 | **只保留右臂** |

#### 通用配置模板（以dual_arm_with_pose为例）

```yaml
fps: 30  # 需根据collection_frequency确认

features:
  observation:
    images:
      # RGB cameras (不包含depth)
      - cam_name: cam_chest_rgb
        args: {h5_path: "observations/camera/rgb/chest/images"}
      - cam_name: cam_head_rgb
        args: {h5_path: "observations/camera/rgb/head/images"}
      - cam_name: cam_left_wrist_rgb
        args: {h5_path: "observations/camera/rgb/left/images"}
      - cam_name: cam_right_wrist_rgb
        args: {h5_path: "observations/camera/rgb/right/images"}

    state:
      sub_state:
        # 左臂关节
        - names: [left_arm_joint_1_rad, ..., left_arm_joint_7_rad]
          args: {h5_path: "observations/arm/left/joints", range_from: 0, range_to: 7}
        
        # 左臂末端姿态 (with_pose版本)
        - names: [left_eef_pos_x_m, left_eef_pos_y_m, left_eef_pos_z_m,
                  left_eef_euler_x_rad, left_eef_euler_y_rad, left_eef_euler_z_rad]
          args: {h5_path: "observations/arm/left/pose", range_from: 0, range_to: 6}
        
        # 右臂关节
        - names: [right_arm_joint_1_rad, ..., right_arm_joint_7_rad]
          args: {h5_path: "observations/arm/right/joints", range_from: 0, range_to: 7}
        
        # 右臂末端姿态
        - names: [right_eef_pos_x_m, right_eef_pos_y_m, right_eef_pos_z_m,
                  right_eef_euler_x_rad, right_eef_euler_y_rad, right_eef_euler_z_rad]
          args: {h5_path: "observations/arm/right/pose", range_from: 0, range_to: 6}
        
        # 夹爪
        - names: [left_gripper_pos]
          args: {h5_path: "observations/effector/left/position", range_from: 0, range_to: 1}
        - names: [right_gripper_pos]
          args: {h5_path: "observations/effector/right/position", range_from: 0, range_to: 1}
        
        # ⚠️ 以下字段全零，不建议包含:
        # - observations/arm/*/wrench (全零)
        # - observations/chassis/* (大多全零)
        # - observations/neck/joints (全零)
        # - observations/torso/* (全零)

  action:
    timeline_offset: 1
    # ⚠️ action group为空，可能需要用observation数据代替
    # 或从其他地方获取action数据
```

#### 压缩视频版本额外配置

```yaml
  observation:
    images:
      - cam_name: cam_chest_rgb
        args:
          h5_path: "observations/camera/rgb/chest/images"
          use_compressed_video: true  # 启用压缩视频
```

---

## 🎯 优先级建议

### 高优先级（立即处理）

1. **Zhipingfang: dual_arm_with_pose** (165 MB, 461帧)
   - 完整数据：双臂 + pose + 4相机
   - 适合作为基准配置

2. **Zhipingfang: dual_arm_with_pose_compressed** (4.4 MB, 179帧)
   - 测试压缩视频功能
   - 文件小，适合快速验证

3. **Zhipingfang: dual_arm_no_pose** (308 MB, 686帧)
   - 无pose版本，需单独配置

### 中优先级

4. **Zhipingfang: left_arm_with_pose** (27 MB, 99帧)
   - ⚠️ 需修复 effector维度问题 (1000→1)

5. **Zhipingfang: right_arm_with_pose** (30 MB, 169帧)
   - 单臂版本

6. **Realman: default_version** (56 MB, 423帧)
   - 需确认128维度映射

### 低优先级（数据质量问题）

7. **Zhipingfang: dual_arm_with_pose_no_left_chest_cam** (24 MB, 127帧)
   - ❌ 左臂数据全零
   - 只能用右臂数据

8. **Agilex: masterpuppet_version** (8.2 GB)
   - ❌ 文件损坏，需重新生成

---

## 🔧 Converter优化需求

### 当前H5 Converter功能

✅ **已支持**:
- 基本H5数据读取
- 压缩视频支持 (`use_compressed_video`)
- H5结构验证
- 帧数一致性检查
- 自动错误文件移动

⚠️ **需要增强**:
1. **高维数据处理**:
   - 支持从高维数组中提取单维（如 effector (N, 1000) → (N, 1)）
   - 当前只支持 range_from/range_to 切片

2. **稀疏数据处理**:
   - 74%全零的数据（如Realman）需要更智能的维度提取
   - 建议添加配置项指定"有效维度列表"

3. **Action数据缺失处理**:
   - Zhipingfang的action group为空
   - 需支持从observation复制或生成action

---

## 📊 数据统计摘要

| 类别 | 数量 | 占比 |
|------|------|------|
| 总数据集 | 9 | 100% |
| 分析成功 | 8 | 88.9% |
| 文件损坏 | 1 | 11.1% |
| 需创建配置 | 8 | - |
| 存在数据质量问题 | 6 | 75% |

**主要数据质量问题**:
- ❌ 全零字段: wrench (100%), chassis (大部分), neck, torso
- ⚠️ 异常维度: left_arm_with_pose的effector (1000维)
- ⚠️ 稀疏数据: Realman (74%全零)
- ❌ 左臂全零: dual_arm_with_pose_no_left_chest_cam, right_arm_with_pose

---

**下一步行动**:
1. 为Zhipingfang dual_arm_with_pose创建基准配置
2. 修复left_arm_with_pose的effector维度问题
3. 确认Realman的128维度映射
4. 测试压缩视频功能
5. 解决action数据缺失问题

**文档生成**: AI Assistant  
**最后更新**: 2025-10-22

