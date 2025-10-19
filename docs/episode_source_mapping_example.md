# Episode Source Mapping 功能说明

## 功能概述

在转换数据集到 LeRobot 格式后，系统会自动生成一个 `episode_source_mapping.json` 文件，记录每个 episode 与其转换前的原始文件路径和文件名的对应关系。

## 文件位置

转换后，映射文件将与 `meta.json`、`info.json` 等文件同级，位于转换后的数据集根目录：

```
output_dataset/
├── meta.json
├── info.json
├── episode_source_mapping.json  ← 映射文件
├── data/
│   └── chunk-000/
│       ├── episode_000000.parquet
│       └── ...
└── videos/
    └── chunk-000/
        ├── observation.images.*.mp4
        └── ...
```

## 映射文件格式

### H5+JPG 格式 (如软通 Ruantong A2D)

```json
{
  "dataset_info": {
    "source_dataset_path": "/path/to/source/dataset",
    "output_dataset_path": "/path/to/output/dataset",
    "repo_id": "robocoin/ruantong_a2d",
    "device_model": "ruantong_a2d",
    "total_episodes": 100
  },
  "episodes": [
    {
      "global_episode_index": 0,
      "task": "pick_cube",
      "task_episode_index": 0,
      "task_path": "/path/to/source/dataset/pick_cube",
      "source_files": {
        "episode_directory": "pick_cube/episode_0",
        "episode_directory_absolute": "/absolute/path/to/episode_0",
        "h5_file": "pick_cube/episode_0/aligned_joints.h5",
        "meta_file": "pick_cube/episode_0/meta_info.json",
        "camera_directory": "pick_cube/episode_0/camera",
        "image_frames_count": 490,
        "total_images_count": 1960
      }
    },
    {
      "global_episode_index": 1,
      "task": "pick_cube",
      "task_episode_index": 1,
      "task_path": "/path/to/source/dataset/pick_cube",
      "source_files": {
        "episode_directory": "pick_cube/sub_task_A/episode_1",
        "episode_directory_absolute": "/absolute/path/to/episode_1",
        "h5_file": "pick_cube/sub_task_A/episode_1/aligned_joints.h5",
        "meta_file": "pick_cube/sub_task_A/episode_1/meta_info.json",
        "camera_directory": "pick_cube/sub_task_A/episode_1/camera",
        "image_frames_count": 450,
        "total_images_count": 1800
      }
    }
  ]
}
```

### 其他 H5 格式示例

对于简单的 H5 数据集格式，如果文件结构较为简单，可能不需要生成映射文件。
但对于其他需要追溯的复杂格式，可以参考软通的实现方式。

## 字段说明

### dataset_info 部分
- `source_dataset_path`: 源数据集的路径
- `output_dataset_path`: 转换后数据集的输出路径
- `repo_id`: HuggingFace 仓库 ID
- `device_model`: 机器人设备型号
- `total_episodes`: 总 episode 数量

### episodes 部分 (每个 episode)
- `global_episode_index`: 全局 episode 索引 (从 0 开始)
- `task`: 任务名称
- `task_episode_index`: 在该任务内的 episode 索引
- `task_path`: 任务目录路径
- `source_files`: 源文件详细信息（根据数据集格式不同而不同）

### source_files 字段（H5+JPG 格式）
- `episode_directory`: episode 目录（相对路径）
- `episode_directory_absolute`: episode 目录（绝对路径）
- `h5_file`: H5 文件路径（包含 state/action 数据）
- `meta_file`: 元数据 JSON 文件路径
- `camera_directory`: 相机图像目录路径
- `image_frames_count`: 图像帧数量
- `total_images_count`: 总图像文件数量

### source_files 字段（其他格式）
根据不同的数据集格式，字段内容会有所不同。具体实现由各个转换器的 `_get_episode_source_files()` 方法决定。

## 使用场景

1. **追溯源文件**: 根据 LeRobot episode 索引快速找到原始数据文件
2. **数据验证**: 检查哪些原始文件被成功转换
3. **错误排查**: 当某个 episode 有问题时，快速定位源文件进行检查
4. **数据管理**: 了解数据集的组织结构和文件分布
5. **再处理**: 需要重新处理特定 episode 时，可以找到原始文件

## 代码示例

### Python 读取映射文件

```python
import json
from pathlib import Path

def load_episode_mapping(output_dataset_path: str) -> dict:
    """加载 episode 源文件映射"""
    mapping_file = Path(output_dataset_path) / "episode_source_mapping.json"
    with open(mapping_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_source_files_for_episode(mapping: dict, global_ep_idx: int) -> dict:
    """获取指定 episode 的源文件信息"""
    for episode in mapping["episodes"]:
        if episode["global_episode_index"] == global_ep_idx:
            return episode["source_files"]
    return None

# 使用示例
mapping = load_episode_mapping("/path/to/output/dataset")
print(f"Total episodes: {mapping['dataset_info']['total_episodes']}")

# 查找第 10 个 episode 的源文件
source_files = get_source_files_for_episode(mapping, 10)
if source_files:
    print(f"Episode 10 source H5 file: {source_files['h5_file']}")
```

### 查找特定原始文件对应的 episode

```python
def find_episode_by_source_file(mapping: dict, filename: str) -> list[int]:
    """查找使用特定源文件的 episode"""
    episodes = []
    for episode in mapping["episodes"]:
        source_files = episode["source_files"]
        # 检查所有文件路径
        for key, value in source_files.items():
            if isinstance(value, str) and filename in value:
                episodes.append(episode["global_episode_index"])
                break
    return episodes

# 使用示例
episodes = find_episode_by_source_file(mapping, "episode_0")
print(f"Episodes using 'episode_0': {episodes}")
```

## 注意事项

1. **自动生成**: 该文件在转换完成后自动生成，无需手动创建
2. **相对路径**: 文件中使用相对路径，便于数据集迁移
3. **格式差异**: 不同的数据集格式（H5, H5+JPG, JPG+JSON等）会有不同的 `source_files` 结构
4. **测试模式**: 在测试模式 (`--is-test`) 下不会生成映射文件
5. **文件大小**: 对于大型数据集，映射文件可能会较大（数千个 episodes）

## 扩展自定义转换器

如果你实现了新的转换器，需要覆盖 `_get_episode_source_files` 方法：

```python
class MyCustomConverter(LerobotFormatConverter):
    def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
        """获取 episode 的源文件信息"""
        # 返回你的数据格式的源文件信息
        return {
            "custom_file": "path/to/custom/file",
            "custom_directory": "path/to/custom/directory",
            # ... 其他相关文件
        }
```
