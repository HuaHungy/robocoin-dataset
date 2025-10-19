# Episode Source Mapping 功能实现总结

## 需求

为软通数据集（以及其他数据集）的转换过程添加源文件映射功能：
- 在转换后的数据集目录中生成一个映射文件
- 记录每个 episode 与其转换前的原始文件路径和文件名的对应关系
- 映射文件与 `meta.json`、`info.json` 等文件同级

## 实现的更改

### 1. 基类修改 (`lerobot_format_converter.py`)

#### a) 添加映射字典初始化
在 `__init__` 方法中添加：
```python
# Episode source file mapping: {global_ep_idx: {task, task_ep_idx, source_files}}
self.episode_source_mapping: dict[int, dict] = {}
```

#### b) 添加抽象方法
新增 `_get_episode_source_files` 方法供子类实现：
```python
def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
    """获取 episode 的源文件信息
    
    Returns:
        dict: 包含源文件信息的字典
    """
    return {}  # 默认实现
```

#### c) 在转换过程中收集映射信息
在 `convert` 方法的 `save_episode()` 之后添加：
```python
# Collect source file mapping information
source_files = self._get_episode_source_files(task_path, task_ep_idx)
self.episode_source_mapping[ep_idx] = {
    "task": task,
    "task_path": str(task_path),
    "task_ep_idx": task_ep_idx,
    "global_ep_idx": ep_idx,
    "source_files": source_files,
}
```

#### d) 添加保存映射文件的方法
```python
def save_episode_source_mapping(self, mapping_filename: str = "episode_source_mapping.json") -> None:
    """保存 episode 源文件映射到 JSON 文件"""
    # 生成格式化的 JSON 文件
    # 包含 dataset_info 和 episodes 两部分
```

### 2. 转换脚本修改 (`convert2lerobot.py`)

在转换完成后调用保存方法：
```python
# Save episode source mapping after conversion completes
if not is_test:
    converter.save_episode_source_mapping()
```

### 3. H5+JPG 转换器实现 (`lerobot_format_converter_h5_jpg.py`)

实现 `_get_episode_source_files` 方法：
```python
def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
    ep_dir = self._get_episode_dir(task_path, ep_idx)
    relative_ep_dir = ep_dir.relative_to(self.dataset_path)
    
    return {
        "episode_directory": str(relative_ep_dir),
        "episode_directory_absolute": str(ep_dir),
        "h5_file": "...",
        "meta_file": "...",
        "camera_directory": "...",
        "image_frames_count": ...,
        "total_images_count": ...,
    }
```

### 4. H5 转换器实现 (`lerobot_format_converter_h5.py`)

实现 `_get_episode_source_files` 方法：
```python
def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
    h5_file_path = self.task_episode_h5file_paths[task_path][ep_idx]
    relative_h5_file = h5_file_path.relative_to(self.dataset_path)
    
    return {
        "h5_file": str(relative_h5_file),
        "h5_file_absolute": str(h5_file_path),
        "h5_file_name": h5_file_path.name,
        "h5_file_size_mb": ...,
    }
```

## 生成的映射文件格式

```json
{
  "dataset_info": {
    "source_dataset_path": "/path/to/source",
    "output_dataset_path": "/path/to/output",
    "repo_id": "robocoin/dataset_name",
    "device_model": "device_model_name",
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
    },
    ...
  ]
}
```

## 使用方式

### 自动生成
转换数据集时自动生成，无需额外操作：
```bash
python scripts/format_converters/tolerobot/convert2lerobot.py \
  --dataset_path "data/ruantong" \
  --output_path "outputs/lerobot_converter" \
  --device_model "ruantong_a2d" \
  --device_model_version "gt02_version" \
  --factory_config_path "scripts/format_converters/tolerobot/configs/converter_factory_config.yaml" \
  --repo_id "robocoin/ruantong_test"
```

转换完成后，在输出目录会自动生成 `episode_source_mapping.json`

### 读取映射
```python
import json

with open("outputs/lerobot_converter/episode_source_mapping.json") as f:
    mapping = json.load(f)

# 查看总 episode 数
print(f"Total episodes: {mapping['dataset_info']['total_episodes']}")

# 查看第 0 个 episode 的源文件
episode_0 = mapping['episodes'][0]
print(f"Episode 0 source: {episode_0['source_files']}")
```

## 扩展到其他转换器

如需为其他转换器（如 G1, MMK2, Rosbag 等）添加此功能，只需：

1. 在转换器类中实现 `_get_episode_source_files` 方法
2. 返回包含源文件信息的字典
3. 系统会自动收集并生成映射文件

示例：
```python
class LerobotFormatConverterG1(LerobotFormatConverter):
    def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
        json_file_path = self.task_episode_jsonfile_paths[task_path][ep_idx]
        episode_dir = json_file_path.parent
        
        return {
            "episode_directory": str(episode_dir.relative_to(self.dataset_path)),
            "json_file": str(json_file_path.relative_to(self.dataset_path)),
            "json_file_name": json_file_path.name,
            # 添加其他相关文件...
        }
```

## 优势

1. **完整追溯**: 可以从 LeRobot episode 追溯到原始源文件
2. **灵活格式**: 不同数据集格式可以有不同的源文件结构
3. **自动生成**: 无需手动操作，转换完成自动生成
4. **易于扩展**: 新的转换器只需实现一个方法即可支持
5. **人类可读**: JSON 格式，易于查看和处理
6. **数据完整**: 包含相对路径和绝对路径，便于不同使用场景

## 测试建议

1. 测试 H5+JPG 格式（软通）：
```bash
python scripts/format_converters/tolerobot/convert2lerobot.py \
  --dataset_path "data/ruantong" \
  --output_path "outputs/test_mapping" \
  --device_model "ruantong_a2d" \
  --device_model_version "gt02_version" \
  --factory_config_path "scripts/format_converters/tolerobot/configs/converter_factory_config.yaml" \
  --repo_id "robocoin/test"
```

2. 测试 H5 格式（智平方）：
```bash
python scripts/format_converters/tolerobot/convert2lerobot.py \
  --dataset_path "data/zhipingfang" \
  --output_path "outputs/test_mapping_h5" \
  --device_model "zhipingfang" \
  --device_model_version "dual_arm_no_pose" \
  --factory_config_path "scripts/format_converters/tolerobot/configs/converter_factory_config.yaml" \
  --repo_id "robocoin/test"
```

3. 检查生成的文件：
```bash
cat outputs/test_mapping/episode_source_mapping.json | jq '.'
```

## 文件列表

### 修改的文件
1. `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter.py`
   - 添加映射字典、抽象方法、收集逻辑、保存方法

2. `scripts/format_converters/tolerobot/convert2lerobot.py`
   - 添加保存映射文件的调用

3. `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_h5_jpg.py`
   - 实现 `_get_episode_source_files` 方法

4. `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_h5.py`
   - 实现 `_get_episode_source_files` 方法

### 新增的文件
1. `docs/episode_source_mapping_example.md`
   - 功能说明和使用示例文档

2. `docs/episode_source_mapping_implementation.md`
   - 实现总结文档（本文件）
