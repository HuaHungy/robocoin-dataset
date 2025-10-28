# 银河(Yinhe)数据集格式分析

**日期**: 2025-10-27  
**数据集**: yinhe (银河机器人)  
**格式**: MP4 + JSON  
**Converter**: LerobotFormatConverterMp4Json

---

## ⚠️ 重要说明

**银河数据集使用的是 MP4+JSON Converter，不是 JPG+JSON Converter！**

这两个converter名称只差两个字母，但处理的数据格式完全不同。

---

## 📁 银河数据集目录结构

```
data/yinhe:default_version/
└── 20250328_record45/                  ← Episode目录
    ├── camera_front_head_rgb.mp4       ← 前置头部相机视频
    ├── camera_left_wrist.mp4           ← 左腕相机视频
    ├── camera_right_wrist.mp4          ← 右腕相机视频
    ├── data.json                       ← 状态/动作数据 (JSON格式)
    ├── local_task_info.yaml            ← 任务信息
    └── report.txt                      ← 报告文件
```

### 特点
- ✅ **扁平结构**：所有文件在同一目录，无arm/camera/等子目录
- ✅ **视频格式**：MP4视频文件（需要解码）
- ✅ **数据格式**：单个大JSON文件，包含所有帧的state/action

---

## 🔧 Converter配置

### Factory配置

来自 `converter_factory_config.yaml`:

```yaml
yinhe:
- version: default_version
  verison_description: yinhe robot with MP4 videos and JSON data
  module: robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_mp4_json
  class: LerobotFormatConverterMp4Json
  converter_config_path: converter_config_yinhe.yaml
```

### Converter类
- **类名**: `LerobotFormatConverterMp4Json`
- **文件**: `lerobot_format_converter_mp4_json.py`
- **配置**: `converter_config_yinhe.yaml`

---

## 📊 data.json 结构

银河的`data.json`是一个大型JSON文件，包含所有帧的数据：

```json
{
  "data": {
    "state_front_head_joint": [        // 头部关节状态（每帧一个对象）
      {
        "names": ["head_joint1", "head_joint2"],
        "position": [2.067e-05, 3.007e-05],
        "velocity": [0.0, 0.0],
        "effort": [0.0, 0.0],
        "timestamp": 1743171862.617
      },
      ...  // 每帧一个对象
    ],
    "state_body_joint_position": [...],      // 身体关节
    "state_left_arm_joint_position": [...],  // 左臂关节
    "state_right_arm_joint_position": [...], // 右臂关节
    "state_left_arm_gripper_width": [...],   // 左夹爪
    "state_right_arm_gripper_width": [...],  // 右夹爪
    
    "cmd_body_joint": [...],            // 身体控制指令（action）
    "cmd_head_joint_state": [...],      // 头部控制指令
    "cmd_left_joint_state": [...],      // 左臂控制指令
    "cmd_right_joint_state": [...]      // 右臂控制指令
  }
}
```

### 数据字段说明

每个状态/动作路径（如`state_left_arm_joint_position`）包含一个数组，每个元素对应一帧的数据。

**State字段结构**:
```json
{
  "names": ["joint1", "joint2", ...],  // 关节名称
  "position": [0.1, 0.2, ...],          // 位置
  "velocity": [0.0, 0.0, ...],          // 速度
  "effort": [0.0, 0.0, ...],            // 力矩
  "timestamp": 1743171862.617           // 时间戳
}
```

---

## 🔄 JPG+JSON vs MP4+JSON 对比

| 特性 | JPG+JSON Converter | MP4+JSON Converter (银河) |
|------|-------------------|-------------------------|
| **数据集示例** | alohaold, pika, mayi | yinhe, agilex_cobot_decoupled_magic |
| **目录结构** | 分层结构<br>`episode/arm/`, `episode/camera/` | 扁平结构<br>`episode/*.mp4`, `episode/data.json` |
| **图像格式** | JPG序列帧<br>每帧一个文件 | MP4视频<br>需要解码 |
| **数据格式** | 多个JSON文件<br>每帧一个JSON，分散在不同目录 | 单个大JSON<br>包含所有帧 |
| **Episode判断** | 检查`arm/`和`camera/`目录 | 检查`.mp4`文件和`data.json` |
| **子目录要求** | 必须有`arm/jointState/`等结构 | 无子目录要求 |

---

## 🎯 MP4+JSON Converter 工作流程

### 1️⃣ Episode定位 (`_is_episode`)

检查目录是否包含：
- `*.mp4` 文件
- `data.json` 文件

如果两者都存在，判定为episode。

### 2️⃣ 加载视频 (`_prepare_episode_images_buffer`)

```python
# 遍历配置中的相机
for camera_config in image_configs:
    cam_name = camera_config['cam_name']
    video_pattern = camera_config['args']['video_file_pattern']
    
    # 根据pattern匹配.mp4文件
    video_files = ep_dir.glob(video_pattern)
    
    # 使用video_backend解码视频
    frames = decode_video(video_file, backend='pyav')
    
    # 保存到buffer
    images[cam_name] = frames
```

**结果**: `images[cam_name] = [frame0, frame1, frame2, ...]`

### 3️⃣ 加载JSON数据 (`_prepare_episode_states_buffer`)

```python
# 读取data.json（单个大文件）
with open(ep_dir / 'data.json') as f:
    data = json.load(f)

# 解析整个JSON结构
buffer = {}
for key in data['data']:
    buffer[key] = data['data'][key]
```

**结果**: `buffer['state_left_arm_joint_position'] = [{frame0}, {frame1}, ...]`

### 4️⃣ 提取帧数据 (`_get_frame_sub_states/actions`)

对每一帧：

```python
# 配置示例
json_path = "state_left_arm_joint_position"
field_name = "position"
range_from = 0
range_to = 7

# 提取第5帧的左臂position
data = buffer[json_path][frame_idx]  # 第5帧
values = data[field_name][range_from:range_to]  # position字段的前7个值
return np.array(values)
```

**配置驱动**：通过`converter_config_yinhe.yaml`中的`json_path`, `field_name`, `range_from`, `range_to`指定数据提取路径。

---

## 📋 银河数据集的配置

### 相机配置 (3个相机)

```yaml
observation:
  images:
    - cam_name: cam_high_rgb
      args:
        cam_name: camera_front_head_rgb
        video_file_pattern: "*camera_front_head_rgb.mp4"
    
    - cam_name: cam_left_wrist_rgb
      args:
        cam_name: camera_left_wrist
        video_file_pattern: "*camera_left_wrist.mp4"
    
    - cam_name: cam_right_wrist_rgb
      args:
        cam_name: camera_right_wrist
        video_file_pattern: "*camera_right_wrist.mp4"
```

### State配置 (48维)

| 分类 | 维度 | 字段 | JSON路径 |
|------|------|------|----------|
| 身体 | 3维 | body_joint (position) | `state_body_joint_position` |
| 头部 | 2维 | head_joint (position) | `state_front_head_joint` |
| 左臂 | 7维 | left_arm_joint (position) | `state_left_arm_joint_position` |
| 左夹爪 | 1维 | left_gripper (width) | `state_left_arm_gripper_width` |
| 右臂 | 7维 | right_arm_joint (position) | `state_right_arm_joint_position` |
| 右夹爪 | 1维 | right_gripper (width) | `state_right_arm_gripper_width` |
| 左臂 | 7维 | left_arm_joint (velocity) | `state_left_arm_joint_position` (field: velocity) |
| 左臂 | 7维 | left_arm_joint (effort) | `state_left_arm_joint_position` (field: effort) |
| 右臂 | 7维 | right_arm_joint (velocity) | `state_right_arm_joint_position` (field: velocity) |
| 右臂 | 7维 | right_arm_joint (effort) | `state_right_arm_joint_position` (field: effort) |

**总计**: 48维

### Action配置 (19维, timeline_offset=1)

| 分类 | 维度 | JSON路径 |
|------|------|----------|
| 身体 | 3维 | `cmd_body_joint` |
| 头部 | 2维 | `cmd_head_joint_state` |
| 左臂 | 7维 | `cmd_left_joint_state` |
| 右臂 | 7维 | `cmd_right_joint_state` |

**总计**: 19维（注意：没有gripper action）

**timeline_offset=1**: action在时间上领先observation 1帧（t时刻的action对应t+1时刻的observation）

---

## ⚠️ 常见混淆点

### 1. 名称相似

- `LerobotFormatConverterJpgJson` (JPG+JSON)
- `LerobotFormatConverterMp4Json` (MP4+JSON, **银河用这个**)

只差两个字母(`Jpg` vs `Mp4`)！

### 2. 都有JSON

两种格式都包含JSON数据，但结构完全不同：
- **JPG+JSON**: 多个小JSON文件，每帧单独的JSON，分散在`arm/jointState/`等子目录
- **MP4+JSON**: 单个大JSON文件，包含所有帧的数据，扁平结构

### 3. 目录结构差异

- **JPG+JSON**: 必须有`arm/`, `camera/`等子目录
- **MP4+JSON**: 扁平结构，直接包含`.mp4`和`data.json`

---

## ✅ 快速识别方法

如何快速判断数据集格式？

```bash
# 查看episode目录
ls data/yinhe:default_version/20250328_record45/

# JPG+JSON格式会看到:
# arm/  camera/  gripper/  imu/  localization/

# MP4+JSON格式会看到（银河）:
# *.mp4  data.json  local_task_info.yaml
```

---

## 📚 总结

### 银河(yinhe)数据集

| 属性 | 值 |
|------|-----|
| **格式** | MP4 + JSON |
| **Converter类** | `LerobotFormatConverterMp4Json` |
| **配置文件** | `converter_config_yinhe.yaml` |
| **目录结构** | 扁平结构，包含`.mp4`和`data.json` |
| **相机数量** | 3个（front_head, left_wrist, right_wrist） |
| **State维度** | 48维 |
| **Action维度** | 19维 |
| **Timeline offset** | 1 |

### JPG+JSON vs MP4+JSON

| 特性 | JPG+JSON | MP4+JSON (银河) |
|------|----------|----------------|
| **用于** | alohaold, pika, mayi | yinhe, agilex_cobot_decoupled_magic |
| **图像** | JPG序列帧 | MP4视频 |
| **数据** | 多个小JSON | 单个大JSON |
| **结构** | 分层（arm/camera/） | 扁平 |

---

## 🔗 相关文件

- Converter实现: `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_mp4_json.py`
- 配置文件: `scripts/format_converters/tolerobot/configs/converter_config_yinhe.yaml`
- Factory配置: `scripts/format_converters/tolerobot/configs/converter_factory_config.yaml`
- 测试数据: `data/yinhe:default_version/`

---

**最后更新**: 2025-10-27

