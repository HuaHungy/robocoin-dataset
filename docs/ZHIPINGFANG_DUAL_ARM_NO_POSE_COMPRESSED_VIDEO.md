# Zhipingfang Dual Arm No Pose Compressed Video Configuration

## 数据集信息
- **数据源**: 智平方 30k数采-第一批-20250930-32274条
- **任务路径**: `task_58_补采-工业5-积木-工业框`
- **文件命名**: `compressed_converted_*.h5`
- **总帧数**: 272 frames (示例文件)

## 数据结构特点

### 1. **双臂机器人配置**
- **Left Arm**: 7 joints + 6 wrench + 1 gripper = 14D
- **Right Arm**: 7 joints + 6 wrench + 1 gripper = 14D
- **Total State**: 29D (14 + 14 + 1 timestamp)

### 2. **无 Arm Pose 数据 ❌**
```
observations/arm/left/pose: shape=(0,) - EMPTY
observations/arm/right/pose: shape=(0,) - EMPTY
```
- 与之前的智平方单臂配置不同，这个版本**没有 6D pose (xyz+rpy)**
- 只有 joint angles 和 wrench (force/torque)

### 3. **Effector 数据已修复 ✅**
```
observations/effector/left/position: shape=(272, 1) ✅
observations/effector/right/position: shape=(272, 1) ✅
```
- **之前的问题**: 旧版本是 `(frames, 1000)` - 1000长度缓冲区
- **新版本修复**: 现在是 `(frames, 1)` - 每帧只有1个gripper值
- **数据类型**: int64, 取值范围 ~450-1006
- **切片行为**: `frame_data[0:1]` → `shape=(1,)` ✅ 正确的1D数组

### 4. **压缩视频格式**
所有相机都使用压缩视频：
- **RGB Cameras**: chest, head, left, right (4个)
- **Depth Cameras**: chest, head, left, right (4个)
- **存储方式**: 
  - `observations/camera/{rgb|depth}/{pos}/video` - 压缩视频数据
  - `observations/camera/{rgb|depth}/{pos}/video_index` - 帧索引数组
  - `observations/camera/{rgb|depth}/{pos}/images` - 空数组 `shape=(0,)`

**示例**:
```
observations/camera/rgb/chest/video: dtype=|V509158 (压缩数据)
observations/camera/rgb/chest/video_index: shape=(29,) dtype=int64
observations/camera/rgb/chest/images: shape=(0,) - EMPTY
```

### 5. **额外传感器数据** (未使用)
数据集包含但配置未使用的数据：
- **Chassis**: pose (3D), status (4D), vel (3D)
- **Neck**: joints (2D)
- **Torso**: joints (4D), pose (4D)

## 配置文件

### State Dimension Breakdown (29D)
```yaml
Left Arm:
  - joints: 7D  [left_arm_joint_0..6]
  - wrench: 6D  [fx, fy, fz, tx, ty, tz]
  - gripper: 1D [left_effector_position]

Right Arm:
  - joints: 7D  [right_arm_joint_0..6]
  - wrench: 6D  [fx, fy, fz, tx, ty, tz]
  - gripper: 1D [right_effector_position]

Timestamp:
  - normalized: 1D

Total: 14 + 14 + 1 = 29D
```

### Action Configuration
Action 复制 observation state (29D)，因为没有显式的 action 数据。

## H5 数据路径映射

### Observations
| LeRobot Feature | H5 Path | Shape | Range |
|----------------|---------|-------|-------|
| observation.state (29D) | Multiple paths | - | - |
| ↳ left_arm_joint_* | observations/arm/left/joints | (272, 7) | [0:7] |
| ↳ left_arm_wrench_* | observations/arm/left/wrench | (272, 6) | [0:6] |
| ↳ left_effector_position | observations/effector/left/position | (272, 1) | [0:1] ✅ |
| ↳ right_arm_joint_* | observations/arm/right/joints | (272, 7) | [0:7] |
| ↳ right_arm_wrench_* | observations/arm/right/wrench | (272, 6) | [0:6] |
| ↳ right_effector_position | observations/effector/right/position | (272, 1) | [0:1] ✅ |
| ↳ timestamp_normalized | observations/timestamp | (272, 1) | [0:1] |

### Images (8 cameras)
| LeRobot Feature | H5 Video Path | H5 Index Path |
|----------------|---------------|---------------|
| observation.images.chest | observations/camera/rgb/chest/video | .../video_index |
| observation.images.head | observations/camera/rgb/head/video | .../video_index |
| observation.images.left | observations/camera/rgb/left/video | .../video_index |
| observation.images.right | observations/camera/rgb/right/video | .../video_index |
| observation.images.chest_depth | observations/camera/depth/chest/video | .../video_index |
| observation.images.head_depth | observations/camera/depth/head/video | .../video_index |
| observation.images.left_depth | observations/camera/depth/left/video | .../video_index |
| observation.images.right_depth | observations/camera/depth/right/video | .../video_index |

## 与其他智平方配置的对比

| Feature | Old Single Arm | New Dual Arm |
|---------|---------------|--------------|
| Arms | Left only | Left + Right |
| Arm Pose | ✅ 6D xyz+rpy | ❌ Empty |
| Wrench | ✅ 6D | ✅ 6D (both arms) |
| Gripper Data | ❌ (272, 1000) bug | ✅ (272, 1) fixed |
| Video Format | Images | Compressed Video |
| State Dim | 21D | 29D |
| Cameras | 4 (2 RGB + 2 Depth) | 8 (4 RGB + 4 Depth) |

## 使用方法

```bash
# 转换示例
python scripts/gen_info.py \\
    --dataset_path "/mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批-20250930-32274条/task_58_补采-工业5-积木-工业框" \\
    --output_path "./outputs/zhipingfang_dual_arm" \\
    --config examples/configs/converter_config_zhipingfang_dual_arm_no_pose_compressed_video.yaml \\
    --repo_id "your-org/zhipingfang-dual-arm" \\
    --device_model "zhipingfang_dual_arm"
```

## 重要说明

### ✅ Effector 数据修复验证
新版本的 effector 数据已经是正确格式：
```python
# 测试结果
LEFT EFFECTOR:
  DOF: 1
  Type: b'gripper'
  Data shape: (272, 1) ✅
  Frame 10 shape: (1,)
  Sliced [0:1] shape: (1,), ndim: 1 ✅
```

### 🔧 H5 Converter 自动修复
即使遇到意外的 2D 数据，converter 会自动处理：
- 如果 `result.shape = (1, N)`，会 squeeze 成 `(N,)`
- 这个修复对新旧版本智平方数据都有效

### 📊 Action 数据策略
由于没有显式的 action 数据，配置将 observation state 复制为 action：
- 这在模仿学习场景中很常见
- Action 可以理解为"下一时刻的目标状态"

## 文件位置
- **Config**: `examples/configs/converter_config_zhipingfang_dual_arm_no_pose_compressed_video.yaml`
- **Documentation**: `docs/ZHIPINGFANG_DUAL_ARM_NO_POSE_COMPRESSED_VIDEO.md`
