# Yinhe数据集帧数验证修复报告

## 问题描述

用户在运行yinhe数据集转换时遇到警告：
```
⚠️ 无法从JSON获取帧数信息：data
💡 JSON结构可能不包含'data'列表，跳过帧数验证
```

## 根本原因

MP4+JSON转换器的视频帧数验证代码只支持一种JSON格式（简单格式），但yinhe数据集使用了不同的JSON结构：

### 预期的JSON格式（简单格式）
```json
{
  "data": [
    {"frame": 0, "timestamp": 123.456, ...},
    {"frame": 1, "timestamp": 123.467, ...},
    ...
  ]
}
```

### Yinhe数据集的实际JSON格式
```json
{
  "data": {
    "camera_front_head_rgb": [frame1, frame2, ...],    // 1110帧
    "camera_left_wrist": [frame1, frame2, ...],        // 1110帧
    "camera_right_wrist": [frame1, frame2, ...],       // 1110帧
    "cmd_action_list": [...],                          // 3712帧
    "state_body_joint_position": [...],                // 9304帧
    ...
  },
  "header": {
    "camera_front_head_rgb": {
      "num_data": 1110,
      "frequency": 29.83,
      "video_path": "camera_front_head_rgb.mp4"
    },
    ...
  }
}
```

**关键区别**：
- 简单格式：`json_data['data']` 是一个列表
- Yinhe格式：`json_data['data']` 是一个字典，包含多个数据流

原代码在第196行只检查了 `isinstance(json_data['data'], list)`，对于yinhe格式返回False，导致跳过帧数验证。

## 修复方案

修改了 `lerobot_format_converter_mp4_json.py` 的 `_prevalidate_files` 方法（第190-250行），使其能够处理两种JSON格式：

### 修复前
```python
if 'data' in json_data and isinstance(json_data['data'], list):
    expected_frame_count = len(json_data['data'])
    # ... 验证代码
else:
    self.logger.warning("无法从JSON获取帧数信息")
```

### 修复后
```python
expected_frame_count = None

if 'data' in json_data:
    # 处理两种JSON格式
    if isinstance(json_data['data'], list):
        # 简单格式：data是一个列表
        expected_frame_count = len(json_data['data'])
    elif isinstance(json_data['data'], dict):
        # yinhe格式：data是一个字典，包含多个数据流
        json_frame_counts = {}
        for key, value in json_data['data'].items():
            if isinstance(value, list) and len(value) > 0:
                json_frame_counts[key] = len(value)
        
        if json_frame_counts:
            expected_frame_count = min(json_frame_counts.values())
            if self.logger:
                self.logger.info(
                    f"🔍 Detected yinhe-style JSON format with {len(json_frame_counts)} data streams\n"
                    f"   📊 Frame counts: {json_frame_counts}\n"
                    f"   📊 Using minimum: {expected_frame_count}"
                )

if expected_frame_count is not None:
    # ... 验证视频帧数
else:
    self.logger.warning("无法从JSON获取帧数信息")
```

### 修复逻辑

1. **检测JSON格式类型**：
   - 如果 `json_data['data']` 是列表 → 简单格式
   - 如果 `json_data['data']` 是字典 → yinhe格式

2. **计算预期帧数**：
   - 简单格式：直接使用列表长度
   - Yinhe格式：遍历所有数据流，使用**最小帧数**作为预期值
   
3. **为什么使用最小帧数？**
   - Yinhe数据集包含多个数据流，采样频率不同：
     - 相机数据：1110帧 (30 Hz)
     - 关节状态：9304帧 (250 Hz)
   - 视频帧数应该匹配相机数据流（最小值）
   - 这与 `_get_episode_frames_num` 方法的逻辑一致

## 修复验证

### 测试结果
```
📊 JSON结构分析:
   - 根键: ['data', 'header']
   - ✅ 检测到yinhe格式 (data是字典)
   - 📊 数据流数量: 13
   - 📊 各数据流帧数:
      • camera_front_head_rgb: 1110 帧
      • camera_left_wrist: 1110 帧
      • camera_right_wrist: 1110 帧
      • cmd_action_list: 3712 帧
      • state_body_joint_position: 9304 帧
      ...
   - 📊 使用最小帧数: 1110

✅ 找到 3 个MP4文件:
   - camera_front_head_rgb.mp4
   - camera_left_wrist.mp4
   - camera_right_wrist.mp4

✅ 测试成功：yinhe数据集JSON结构解析正确
   - 预期帧数: 1110
   - MP4文件数量: 3
```

### 验证要点
- ✅ 正确识别yinhe格式（data是字典）
- ✅ 正确解析13个数据流
- ✅ 正确计算最小帧数（1110）
- ✅ 与3个MP4文件匹配

## 兼容性

此修复保持了对原有简单格式的完全兼容：

| JSON格式 | data类型 | 处理方式 | 状态 |
|---------|---------|---------|------|
| 简单格式 | list | `len(json_data['data'])` | ✅ 兼容 |
| Yinhe格式 | dict | `min(各数据流长度)` | ✅ 支持 |
| 无效格式 | 其他 | 跳过验证，记录警告 | ✅ 降级 |

## 相关文件

### 修改的文件
- `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_mp4_json.py`
  - 第190-250行：`_prevalidate_files` 方法

### 测试文件
- `test_yinhe_validation.py` - 验证JSON格式解析逻辑的测试脚本

### 参考文档
- `docs/video_frame_validation.md` - 视频帧数验证完整文档
- `video_frame_validation_example.py` - 使用示例（包含5个场景）

## 已知信息

### Yinhe数据集特点
1. **多数据流结构**：包含相机、关节状态、命令等多种数据流
2. **不同采样频率**：
   - 相机：~30 Hz (1110帧)
   - 关节状态：~250 Hz (9000+帧)
   - 里程计：~50 Hz (1856帧)
3. **Header元数据**：包含每个数据流的详细信息（帧数、频率、视频路径）

### 数据流示例
```
camera_front_head_rgb    : 1110 帧 (29.83 Hz)
camera_left_wrist        : 1110 帧 (29.83 Hz)
camera_right_wrist       : 1110 帧 (29.83 Hz)
cmd_action_list          : 3712 帧 (99.99 Hz)
cmd_left_joint_state     : 3722 帧 (100.00 Hz)
cmd_right_joint_state    : 3722 帧 (100.00 Hz)
odom                     : 1856 帧 (50.00 Hz)
state_body_joint_position: 9304 帧 (249.99 Hz)
state_front_head_joint   : 9304 帧 (249.99 Hz)
state_left_arm_gripper   : 1480 帧 (39.89 Hz)
state_left_arm_joint     : 9304 帧 (250.00 Hz)
state_right_arm_gripper  : 1476 帧 (39.89 Hz)
state_right_arm_joint    : 9250 帧 (250.01 Hz)
```

## 总结

**修复前**：
- ❌ 仅支持简单JSON格式（data是列表）
- ⚠️ Yinhe数据集跳过帧数验证，输出警告

**修复后**：
- ✅ 支持两种JSON格式（list和dict）
- ✅ 正确识别和处理yinhe格式
- ✅ 使用最小帧数进行验证
- ✅ 保持向后兼容

**影响范围**：
- 仅影响 `lerobot_format_converter_mp4_json.py` 的帧数验证逻辑
- 不影响数据转换的核心功能
- 其他转换器（H5+MP4, Annotation+H5+MP4）不受影响

**后续建议**：
1. 可以考虑将JSON格式检测逻辑提取为独立方法，提高复用性
2. 如果出现更多JSON格式变体，建议实现配置化的格式适配器
3. 可以在header中添加格式版本信息，便于未来扩展

---

**修复日期**: 2025年2月
**修复人**: GitHub Copilot
**测试状态**: ✅ 通过
