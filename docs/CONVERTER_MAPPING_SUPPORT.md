# Episode Source Mapping - 转换器支持说明

## 🎯 支持状态

### ✅ 已实现映射功能的转换器

#### 1. 软通 (Ruantong A2D) - H5+JPG 格式
**文件**: `lerobot_format_converter_h5_jpg.py`

**映射信息**:
```json
{
  "episode_directory": "relative/path/to/episode",
  "episode_directory_absolute": "/absolute/path/to/episode",
  "h5_file": "relative/path/to/aligned_joints.h5",
  "meta_file": "relative/path/to/meta_info.json",
  "camera_directory": "relative/path/to/camera/",
  "image_frames_count": 490,
  "total_images_count": 1960
}
```

**适用场景**: 软通数据集具有复杂的目录结构，包含多个文件类型，需要详细的源文件追溯。

---

### ⚪ 使用默认实现的转换器

以下转换器使用基类的默认实现，返回空字典 `{}`：

#### 2. 智平方 (Zhipingfang) - H5 格式
**文件**: `lerobot_format_converter_h5.py`

**原因**: 
- 数据结构简单，一个 H5 文件对应一个 episode
- 文件名已经包含足够的信息
- 不需要额外的源文件追溯

#### 3. G1 (Unitree G1) - JPG+JSON 格式
**文件**: `lerobot_format_converter_g1.py`

**原因**: 暂时不需要映射功能

#### 4. MMK2 - JPG+BSON 格式
**文件**: `lerobot_format_converter_mmk2.py`

**原因**: 暂时不需要映射功能

#### 5. Rosbag 格式
**文件**: `lerobot_format_converter_rosbag.py`

**原因**: 暂时不需要映射功能

#### 6. 其他转换器
- H5+MP4: `lerobot_format_converter_h5_mp4.py`
- MCAP: `lerobot_format_converter_mcap.py`
- JPG+JSON: `lerobot_format_converter_jpg_json.py`
- MP4+JSON: `lerobot_format_converter_mp4_json.py`

---

## 🔧 如何为新转换器添加映射功能

如果你需要为某个转换器添加映射功能，只需实现 `_get_episode_source_files()` 方法：

```python
class MyConverter(LerobotFormatConverter):
    def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
        """获取 episode 的源文件信息
        
        Returns:
            dict: 包含源文件详细信息，例如：
                {
                    "source_file_1": "path/to/file1",
                    "source_directory": "path/to/dir",
                    "file_count": 100,
                    # ... 任何你需要记录的信息
                }
        """
        # 你的实现逻辑
        # 例如：获取 episode 目录
        episode_dir = self._get_episode_dir(task_path, ep_idx)
        
        return {
            "episode_directory": str(episode_dir.relative_to(self.dataset_path)),
            "data_file": str((episode_dir / "data.bin").relative_to(self.dataset_path)),
            # ... 更多信息
        }
```

---

## 📋 决策建议

### 什么时候需要实现映射功能？

✅ **应该实现**：
- 数据集有复杂的目录结构
- 一个 episode 由多个文件组成
- 需要追溯具体的源文件用于调试
- 文件命名不规则，难以从文件名推断关系

❌ **可以不实现**：
- 数据结构简单（如单个 H5 文件）
- 文件命名已经足够清晰
- 不需要追溯源文件
- 数据集是临时性的或测试用途

### 示例判断

| 转换器 | 数据结构 | 是否需要映射 | 原因 |
|-------|---------|------------|------|
| 软通 H5+JPG | episode_dir/aligned_joints.h5 + camera/*/\*.jpg | ✅ 需要 | 多文件、多层目录 |
| 智平方 H5 | single_file.h5 | ❌ 不需要 | 单文件、结构简单 |
| G1 JPG+JSON | episode_dir/data.json + images/\*.jpg | ⚪ 可选 | 中等复杂度 |
| Rosbag | dataset.bag | ❌ 不需要 | 单文件 |

---

## 🎯 总结

- **软通转换器**: ✅ 已实现完整的源文件映射功能
- **其他转换器**: ⚪ 使用默认实现（返回空字典）
- **生成的映射文件**: 即使某些 episode 信息为空，仍会生成完整的映射文件框架
- **扩展性**: 随时可以为任何转换器添加映射功能，只需实现 `_get_episode_source_files()` 方法

---

## 📄 映射文件示例

### 混合模式（部分有映射，部分无映射）

```json
{
  "dataset_info": {
    "source_dataset_path": "/path/to/source",
    "output_dataset_path": "/path/to/output",
    "repo_id": "robocoin/mixed_dataset",
    "device_model": "mixed_model",
    "total_episodes": 3
  },
  "episodes": [
    {
      "global_episode_index": 0,
      "task": "ruantong_task",
      "task_episode_index": 0,
      "task_path": "/path/to/ruantong",
      "source_files": {
        "episode_directory": "task/episode_0",
        "h5_file": "task/episode_0/aligned_joints.h5",
        "camera_directory": "task/episode_0/camera",
        "image_frames_count": 490
      }
    },
    {
      "global_episode_index": 1,
      "task": "zhipingfang_task",
      "task_episode_index": 0,
      "task_path": "/path/to/zhipingfang",
      "source_files": {}
    },
    {
      "global_episode_index": 2,
      "task": "g1_task",
      "task_episode_index": 0,
      "task_path": "/path/to/g1",
      "source_files": {}
    }
  ]
}
```

注意：即使 `source_files` 为空，仍会保留该字段，保持 JSON 结构的一致性。
