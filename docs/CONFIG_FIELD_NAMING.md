# 配置文件字段命名规范

本文档说明不同数据格式的配置文件字段命名约定。

## 配置字段标准化

| 格式 | 图片配置字段 | 状态/动作配置字段 | 说明 |
|-----|------------|----------------|-----|
| H5 | `h5_path` | `h5_path` | H5内部路径，如`/observations/images/cam1` |
| H5+MP4 | N/A（MP4独立） | `h5_path` | H5内部状态，MP4外部视频 |
| H5+JPG | `h5_path`（实为文件路径）⚠️ | `h5_path` | 混淆但功能正确，见下方说明 |
| MCAP | `mcap_topic` | `mcap_topic` | 如`/camera_head/color/image_raw` |
| RosBag | `topic_name` | `topic_name` | 如`/hdas/camera_head/left_raw` |
| MP4+JSON | N/A（MP4独立） | `json_path` | JSON数据路径 |
| JPG+JSON | N/A（JPG独立） | `json_path` | JSON数据路径 |
| BSON | N/A（JPG独立） | `data_path` | BSON数据路径 |

## H5+JPG格式的特殊性 ⚠️

**重要说明**：H5+JPG格式（如Ruantong数据集）的配置字段命名存在混淆，但功能正确。

### 问题说明

在H5+JPG格式中，图片数据使用`h5_path`字段，但实际含义与纯H5格式不同：

**纯H5格式**（如Zhipingfang）：
```yaml
images:
  - cam_name: cam_high_rgb
    args:
      h5_path: /observations/images/top   # H5文件内部路径
```
- `h5_path`指向H5文件内部的dataset路径
- 图片数据存储在H5文件中

**H5+JPG格式**（如Ruantong）：
```yaml
images:
  - cam_name: head_color
    args:
      h5_path: camera/{frame_idx}/head_color.jpg   # 文件系统路径！
      file_type: jpg
```
- `h5_path`实际是**文件系统路径**，不是H5内部路径
- `{frame_idx}`占位符会被替换为实际帧索引
- 图片文件独立存储为JPG文件

### 为什么这样命名？

虽然命名混淆，但保持统一字段名`h5_path`有以下好处：
1. 配置文件解析器可以使用统一的逻辑
2. 避免修改大量现有配置文件
3. `file_type`字段已经标识了数据类型

### 实现细节

在`lerobot_format_converter_h5_jpg.py`中：

**状态/动作数据**（从H5读取）：
```python
# h5_path指向H5文件内部路径
h5_path = "/state/robot/positions"
data = h5_file[h5_path][frame_idx]
```

**图片数据**（从文件系统读取）：
```python
# h5_path实际是文件路径模板
h5_path = "camera/{frame_idx}/head_color.jpg"
image_path = h5_path.replace("{frame_idx}", str(actual_frame_idx))
full_path = episode_dir / image_path
image = Image.open(full_path)
```

### 最佳实践

**新配置文件**：
- 如果是H5+JPG格式，继续使用`h5_path`字段（保持一致性）
- 明确标注`file_type: jpg`或`file_type: png`
- 使用`{frame_idx}`占位符表示帧索引

**配置检测器**：
- 检测配置时，需要根据`file_type`字段判断实际含义
- `file_type: jpg/png` → `h5_path`是文件系统路径
- 无`file_type`或`file_type: h5` → `h5_path`是H5内部路径

## 示例对比

### 纯H5格式（Zhipingfang）

```yaml
features:
  observation:
    images:
      - cam_name: cam_high_rgb
        args:
          h5_path: /observations/images/top
    state:
      sub_state:
        - names: [left_arm_joint_1_rad, ...]
          args:
            h5_path: /observations/qpos
            range_from: 0
            range_to: 7
```

### H5+JPG格式（Ruantong）

```yaml
features:
  observation:
    images:
      - cam_name: head_color
        args:
          h5_path: camera/{frame_idx}/head_color.jpg  # 文件路径！
          file_type: jpg
    state:
      sub_state:
        - names: [robot_joint_3_rad, ...]
          args:
            h5_path: /state/robot/positions  # H5内部路径
            range_from: 2
            range_to: 3
```

### MCAP格式（Realman）

```yaml
features:
  observation:
    images:
      - cam_name: cam_high_rgb
        args:
          mcap_topic: /camera_head/color/image_raw/compressed
    state:
      sub_state:
        - names: [right_arm_joint_1_rad, ...]
          args:
            mcap_topic: /right_arm_controller/joint_states
            range_from: 0
            range_to: 7
```

### RosBag格式（Galaxea）

```yaml
features:
  observation:
    images:
      - cam_name: cam_high_left_rgb
        args:
          topic_name: /hdas/camera_head/left_raw/image_raw_color/compressed
    state:
      sub_state:
        - names: [left_arm_joint_1_rad, ...]
          args:
            topic_name: /hdas/feedback_arm_left
            range_from: 0
            range_to: 7
```

## 配置检测器实现指南

检测器应该根据配置自动识别路径字段名：

```python
def get_path_field_name(config):
    """自动检测配置使用的路径字段名"""
    sample_args = config['features']['observation']['state']['sub_state'][0]['args']
    
    if 'h5_path' in sample_args:
        return 'h5_path'
    elif 'mcap_topic' in sample_args:
        return 'mcap_topic'
    elif 'topic_name' in sample_args:
        return 'topic_name'
    elif 'json_path' in sample_args:
        return 'json_path'
    elif 'data_path' in sample_args:
        return 'data_path'
    else:
        raise ValueError("Unknown path field type")
```

## 总结

- 不同格式使用不同的字段名标识数据路径
- H5+JPG格式的`h5_path`存在命名混淆，但功能正确
- 配置检测器需要格式感知，自动识别正确的字段名
- 新配置应遵循现有约定，保持一致性

