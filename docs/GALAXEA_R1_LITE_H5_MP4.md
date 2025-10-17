# Galaxea R1 Lite H5+MP4 Configuration

## 数据集信息
- **数据源**: Galaxea R1 Lite 机器人
- **格式**: HDF5 + MP4 视频
- **位置**: `data/gax_h5/`

## 数据结构

### 1. **文件组织**
每个 episode 一个文件夹，包含：
```
0/
├── 0.hdf5                    # 状态和动作数据
├── 0.parquet                 # 元数据（可选）
├── 0_cam_high.mp4           # 高位相机视频
├── 0_cam_left_wrist.mp4     # 左腕相机视频
└── 0_cam_right_wrist.mp4    # 右腕相机视频
```

### 2. **H5 文件内容**
```python
qpos: shape=(626, 14), dtype=float64
  # 14D joint positions: [0-6] 左臂 + [7-13] 右臂
  
action: shape=(626, 14), dtype=float64
  # 14D joint actions: 与 qpos 同维度
```

**注意**: 
- ❌ **没有 eepose 数据**（与 h5_version 配置不同）
- ✅ 只有 qpos 和 action

### 3. **视频文件**
- **命名格式**: `{episode_idx}_cam_{camera_name}.mp4`
- **相机列表**:
  - `cam_high` - 高位相机
  - `cam_left_wrist` - 左腕相机
  - `cam_right_wrist` - 右腕相机
- **帧数**: 与 H5 中的 qpos/action 长度一致（如 626 帧）

### 4. **State 和 Action 维度**
- **State**: 14D (qpos only)
- **Action**: 14D (qpos only)
- **Total**: 无 eepose，比 h5_version 少 20D

## 配置对比

| 特性 | h5_version | h5_mp4_version |
|-----|-----------|----------------|
| H5 数据 | qpos + eepose | qpos only |
| 视频 | ❌ 无 | ✅ 3个 MP4 |
| State Dim | 34D | 14D |
| Action Dim | 34D | 14D |
| 适用场景 | 纯状态控制 | 视觉控制 |

## H5 数据路径映射

| LeRobot Feature | H5 Path | Shape | Range |
|----------------|---------|-------|-------|
| observation.state (14D) | qpos | (626, 14) | [0:14] |
| ↳ left_arm_qpos_0..6 | qpos | - | [0:7] |
| ↳ right_arm_qpos_0..6 | qpos | - | [7:14] |
| action (14D) | action | (626, 14) | [0:14] |

## 图像配置

| LeRobot Feature | Video Pattern | Camera Name |
|----------------|---------------|-------------|
| observation.images.cam_high | *cam_high.mp4 | cam_high |
| observation.images.cam_left_wrist | *cam_left_wrist.mp4 | cam_left_wrist |
| observation.images.cam_right_wrist | *cam_right_wrist.mp4 | cam_right_wrist |

## 使用方法

### 转换命令
```bash
python scripts/gen_info.py \
    --dataset_path "data/gax_h5" \
    --output_path "./outputs/galaxea_r1_lite_h5_mp4" \
    --config scripts/format_converters/tolerobot/configs/converter_config_galaxea_r1_lite_h5_mp4.yaml \
    --repo_id "your-org/galaxea-r1-lite-h5-mp4" \
    --device_model "galaxea_r1_lite" \
    --device_version "h5_mp4_version"
```

### 选择版本
```bash
# H5 only (无视频)
--device_version "h5_version"

# H5 + MP4 (有视频)
--device_version "h5_mp4_version"

# ROS bag (原始数据)
--device_version "default_version"
```

## 实现细节

### 1. **Converter 类**
使用 `LerobotFormatConverterH5Mp4` 类：
- 继承自基础 converter
- 支持 MP4 视频读取
- 使用 `video_file_pattern` 匹配视频文件

### 2. **视频文件查找**
```python
# 配置中指定 pattern
args:
  cam_name: cam_high
  video_file_pattern: "*cam_high.mp4"

# Converter 使用 glob 匹配
mp4_files = list(ep_dir.glob(video_file_pattern))
```

### 3. **帧数验证**
自动验证视频帧数与 H5 数据一致：
- 允许 ±1 帧误差
- 不一致时输出警告
- 验证首个 episode

## 重要说明

### ✅ 优势
1. **完整视觉信息** - 3个相机覆盖不同视角
2. **标准格式** - 使用 MP4 压缩，节省存储
3. **易于扩展** - 可添加更多相机

### ⚠️ 注意事项
1. **数据一致性**: 确保视频帧数 = H5 数据长度
2. **命名规范**: 视频文件必须匹配 `{episode_idx}_cam_{name}.mp4`
3. **颜色空间**: 视频从 BGR 转换为 RGB

### 📊 存储估算
- H5 文件: ~256 KB/episode
- MP4 视频: ~30 MB/episode (3个相机)
- 总计: ~30 MB/episode

## 文件位置
- **Config**: `scripts/format_converters/tolerobot/configs/converter_config_galaxea_r1_lite_h5_mp4.yaml`
- **Factory**: `converter_factory_config.yaml` (h5_mp4_version)
- **Documentation**: `docs/GALAXEA_R1_LITE_H5_MP4.md`
- **Test Data**: `data/gax_h5/0/`
