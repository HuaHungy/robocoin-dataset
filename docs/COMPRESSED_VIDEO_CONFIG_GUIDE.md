# 压缩视频格式配置说明

## 概述

为了支持 H5 文件中的压缩视频格式（视频数据存储为 MP4 而不是图像数组），我们采用**配置驱动**的方式，而不是自动检测。这确保了转换行为的可预测性和可控性。

## 工作原理

### 1. 配置文件控制

在相机配置的 `args` 部分添加 `use_compressed_video` 字段：

```yaml
features:
  observation:
    images:
      - cam_name: camera_head_rgb
        args:
          h5_path: observations/camera/rgb/head/images
          use_compressed_video: true  # 显式指定使用压缩视频格式
```

### 2. 两种格式对比

| 格式 | H5 数据结构 | use_compressed_video 设置 |
|------|------------|------------------------|
| **传统格式** | `observations/camera/rgb/head/images: (N, H, W, 3)` | `false` 或不设置 |
| **压缩视频格式** | `observations/camera/rgb/head/video: ()` (MP4)<br>`observations/camera/rgb/head/video_index: (M,)` | `true` |

### 3. 数据加载行为

#### 当 `use_compressed_video: false` (默认)
- 加载 `observations/camera/rgb/head/images` 数组
- 直接读取帧数据

#### 当 `use_compressed_video: true`
- **跳过**加载 `images` 数组
- **加载** `observations/camera/rgb/head/video` (压缩视频数据)
- **加载** `observations/camera/rgb/head/video_index` (帧索引)
- 运行时解码视频帧

## 配置文件版本

### 现有的压缩视频配置

我们为智平方数据集创建了以下压缩视频专用配置：

1. **`converter_config_zhipingfang_left_arm_with_pose_compressed_video.yaml`**
   - 单左臂 + pose
   - 相机: head + left wrist (压缩视频)
   - State: 21D, Action: 20D

2. **`converter_config_zhipingfang_right_arm_with_pose_compressed_video.yaml`**
   - 单右臂 + pose
   - 相机: head + right wrist (压缩视频)
   - State: 21D, Action: 20D

3. **`converter_config_zhipingfang_dual_arm_with_pose_compressed_video.yaml`**
   - 双臂 + pose
   - 相机: head + left + right + chest (压缩视频)
   - State: 40D, Action: 40D

### 在工厂配置中注册

```yaml
zhipingfang:
  # ... 其他版本 ...
  
  # Compressed Video Format Versions
  - version: left_arm_with_pose_compressed_video
    verison_description: zhipingfang single left arm with pose (compressed video format - images stored as MP4)
    converter_config_path: converter_config_zhipingfang_left_arm_with_pose_compressed_video.yaml
  
  - version: right_arm_with_pose_compressed_video
    verison_description: zhipingfang single right arm with pose (compressed video format - images stored as MP4)
    converter_config_path: converter_config_zhipingfang_right_arm_with_pose_compressed_video.yaml
  
  - version: dual_arm_with_pose_compressed_video
    verison_description: zhipingfang dual arm with pose (compressed video format - images stored as MP4)
    converter_config_path: converter_config_zhipingfang_dual_arm_with_pose_compressed_video.yaml
```

## 使用方法

### 1. 数据库配置

在数据集的 `local_dataset_info.yaml` 中指定压缩视频版本：

```yaml
device_model:
  - zhipingfang

version: dual_arm_with_pose_compressed_video  # 使用压缩视频版本
device_model_version: dual_arm_with_pose_compressed_video
```

### 2. 标注数据库

```bash
python scripts/annotation/device_model_annotation.py /path/to/datasets.db
```

### 3. 运行转换

```bash
python scripts/format_converters/tolerobot/dataset_converter.py \
  --db /path/to/datasets.db \
  --task lerobot_format_convert
```

## 技术细节

### 视频解码流程

1. **格式检查**: 根据 `use_compressed_video` 配置决定使用哪种格式
2. **数据加载**: 
   - 如果是压缩视频，加载 `video` + `video_index`
   - 如果是传统格式，加载 `images` 数组
3. **帧提取**: 
   - 压缩视频: 临时文件解码 → OpenCV 读取 → BGR→RGB 转换
   - 传统格式: 直接数组索引

### 帧映射策略

压缩视频通常帧数少于机械臂数据帧数（例如 10 视频帧 vs 327 臂数据帧），使用**最近邻插值**：

```python
video_frame_idx = min(int(arm_frame * total_video_frames / total_arm_frames), 
                     total_video_frames - 1)
```

示例映射（327 臂帧 → 10 视频帧）:
- 臂帧 0 → 视频帧 0
- 臂帧 100 → 视频帧 3
- 臂帧 200 → 视频帧 6
- 臂帧 326 → 视频帧 9

## 错误处理

### 配置不匹配

如果配置了 `use_compressed_video: true` 但 H5 文件中没有 video 数据：

```
❌ Compressed video format configured but video data not found.
   🔍 Expected video path: observations/camera/rgb/head/video
   🔍 Expected index path: observations/camera/rgb/head/video_index
   📁 Location: task=xxx, ep_idx=0, frame_idx=0
   📋 Available paths (showing first 10): [...]
   💡 Set use_compressed_video: false in config if using normal image format
```

### 混合格式支持

可以在同一配置中混合使用两种格式：

```yaml
images:
  - cam_name: camera_head_rgb
    args:
      h5_path: observations/camera/rgb/head/images
      use_compressed_video: true  # 这个相机使用压缩视频
  
  - cam_name: camera_wrist_rgb
    args:
      h5_path: observations/camera/rgb/wrist/images
      use_compressed_video: false  # 这个相机使用传统格式（或不设置）
```

## 性能对比

| 指标 | 传统格式 | 压缩视频格式 |
|------|---------|-------------|
| 存储空间 | ~300MB/episode | ~3MB/episode (99%↓) |
| 加载速度 | 快速 | 较慢（需解码） |
| 内存占用 | 高 | 低 |
| 图像质量 | 无损 | 有损（MP4压缩） |
| 帧率 | 30 FPS | ~3 FPS（降采样） |

## 最佳实践

1. **存储优先**: 使用压缩视频格式节省 99% 存储空间
2. **质量优先**: 使用传统格式保持无损图像
3. **明确配置**: 始终在配置文件中显式指定 `use_compressed_video`
4. **版本命名**: 使用 `*_compressed_video` 后缀区分压缩视频版本
5. **数据库标注**: 确保 `local_dataset_info.yaml` 中的 version 与配置文件匹配

## 迁移指南

### 从自动检测迁移

如果你之前使用的是自动检测版本，现在需要：

1. **检查数据格式**: 确认 H5 文件使用的是哪种格式
2. **选择配置版本**: 
   - 传统格式 → 使用原版配置（如 `dual_arm_with_pose`）
   - 压缩视频 → 使用新版配置（如 `dual_arm_with_pose_compressed_video`）
3. **更新数据库**: 修改 `local_dataset_info.yaml` 中的 `version` 字段
4. **重新标注**: 运行 `device_model_annotation.py`

### 创建新配置

如果需要为其他机器人创建压缩视频配置：

1. 复制现有的传统格式配置
2. 为所有相机添加 `use_compressed_video: true`
3. 文件命名添加 `_compressed_video` 后缀
4. 在 `converter_factory_config.yaml` 中注册
5. 添加描述说明这是压缩视频版本

## 总结

通过配置驱动的方式，我们实现了：

✅ **明确性**: 配置文件清楚地声明了使用哪种格式  
✅ **可控性**: 不依赖运行时的自动检测，避免意外行为  
✅ **灵活性**: 支持混合格式，可以为不同相机使用不同格式  
✅ **可维护性**: 配置文件作为唯一真实来源，易于理解和调试  
✅ **兼容性**: 不影响现有的传统格式配置  

这种设计确保了转换行为完全由配置文件控制，符合"配置即文档"的最佳实践。
