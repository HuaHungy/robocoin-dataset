# Episode Source Mapping 功能

## ✅ 已完成

为数据集转换添加了 episode 源文件映射功能，可以追溯每个转换后的 episode 对应的原始文件。

## 🎯 功能特点

1. **自动生成**: 转换完成后自动生成 `episode_source_mapping.json` 文件
2. **位置**: 与 `meta.json`、`info.json` 同级，在转换后数据集根目录
3. **内容**: 记录每个 episode 的：
   - 全局索引 (global_episode_index)
   - 任务名称和路径
   - 原始源文件详细信息（相对路径和绝对路径）

## 📁 修改的文件

### 核心修改
1. **`src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter.py`**
   - ✅ 添加 `episode_source_mapping` 字典
   - ✅ 添加 `_get_episode_source_files()` 抽象方法
   - ✅ 在 `convert()` 中收集映射信息
   - ✅ 添加 `save_episode_source_mapping()` 方法

2. **`scripts/format_converters/tolerobot/convert2lerobot.py`**
   - ✅ 转换完成后调用 `save_episode_source_mapping()`

### 转换器实现
3. **`src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_h5_jpg.py`** (软通)
   - ✅ 实现 `_get_episode_source_files()` 方法
   - ✅ 返回 H5 文件、meta 文件、camera 目录、图像统计等信息

4. **其他转换器** (G1, MMK2, Rosbag 等)
   - ⚪ 可根据需要选择性实现 `_get_episode_source_files()` 方法
   - ⚪ 如不实现，则返回空字典（默认行为）

### 工具和文档
5. **`scripts/format_converters/tolerobot/query_episode_mapping.py`** (新增)
   - ✅ 映射查询工具
   - ✅ 支持按 episode、任务、源文件查询

6. **`docs/episode_source_mapping_example.md`** (新增)
   - ✅ 详细使用说明和示例

7. **`docs/episode_source_mapping_implementation.md`** (新增)
   - ✅ 实现细节总结

## 🚀 使用方法

### 1. 转换数据集（自动生成映射）

```bash
# 软通数据集
python scripts/format_converters/tolerobot/convert2lerobot.py \
  --dataset_path "data/ruantong" \
  --output_path "outputs/lerobot_converter" \
  --device_model "ruantong_a2d" \
  --device_model_version "gt02_version" \
  --factory_config_path "scripts/format_converters/tolerobot/configs/converter_factory_config.yaml" \
  --repo_id "robocoin/ruantong_test"

# 转换完成后会自动生成:
# outputs/lerobot_converter/episode_source_mapping.json
```

### 2. 查询映射信息

```bash
# 查看数据集信息
python scripts/format_converters/tolerobot/query_episode_mapping.py \
  --dataset-path outputs/lerobot_converter \
  --info

# 查看特定 episode
python scripts/format_converters/tolerobot/query_episode_mapping.py \
  --dataset-path outputs/lerobot_converter \
  --episode 0

# 列出所有任务
python scripts/format_converters/tolerobot/query_episode_mapping.py \
  --dataset-path outputs/lerobot_converter \
  --list-tasks

# 按任务查找 episodes
python scripts/format_converters/tolerobot/query_episode_mapping.py \
  --dataset-path outputs/lerobot_converter \
  --task "pick_cube"

# 按源文件查找 episodes
python scripts/format_converters/tolerobot/query_episode_mapping.py \
  --dataset-path outputs/lerobot_converter \
  --source-file "episode_0"
```

### 3. Python 代码读取

```python
import json

# 加载映射
with open("outputs/lerobot_converter/episode_source_mapping.json") as f:
    mapping = json.load(f)

# 查看数据集信息
print(f"Total episodes: {mapping['dataset_info']['total_episodes']}")

# 查看第 0 个 episode 的源文件
episode_0 = mapping['episodes'][0]
print(f"Episode 0 source files:")
for key, value in episode_0['source_files'].items():
    print(f"  {key}: {value}")
```

## 📊 映射文件格式

```json
{
  "dataset_info": {
    "source_dataset_path": "/path/to/source",
    "output_dataset_path": "/path/to/output",
    "repo_id": "robocoin/dataset",
    "device_model": "device_model",
    "total_episodes": 100
  },
  "episodes": [
    {
      "global_episode_index": 0,
      "task": "task_name",
      "task_episode_index": 0,
      "task_path": "/path/to/task",
      "source_files": {
        "episode_directory": "relative/path/to/episode",
        "h5_file": "relative/path/to/file.h5",
        ...
      }
    }
  ]
}
```

## 🔧 扩展到其他转换器

如需为其他转换器（G1, MMK2, Rosbag 等）添加此功能：

```python
class MyConverter(LerobotFormatConverter):
    def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
        """返回源文件信息"""
        return {
            "my_data_file": "path/to/data.file",
            "my_image_dir": "path/to/images/",
            # ... 其他相关文件
        }
```

## ✅ 验证

所有文件编译通过，无语法错误：
```bash
python -m py_compile src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter.py
python -m py_compile src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_h5.py
python -m py_compile src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_h5_jpg.py
python -m py_compile scripts/format_converters/tolerobot/convert2lerobot.py
python -m py_compile scripts/format_converters/tolerobot/query_episode_mapping.py
```

## 📚 详细文档

- **使用说明**: `docs/episode_source_mapping_example.md`
- **实现细节**: `docs/episode_source_mapping_implementation.md`

## 🎉 完成状态

✅ 已实现所有核心功能
✅ 已为软通(H5+JPG)转换器实现映射功能
✅ 其他转换器使用默认实现（返回空字典）
✅ 已添加查询工具
✅ 已添加完整文档
✅ 代码编译通过
