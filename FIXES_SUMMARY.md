[15404/20091] ❌ steamer_storage_baozi/20250911_184442_record0
      • JSON错误: Unterminated string starting at: line 1 column 10485757 (char 10485756)
  [15405/20091] ❌ steamer_storage_baozi/20250911_184533_record0
      • JSON错误: Expecting ',' delimiter: line 1 column 10485761 (char 10485760)













# 数据集转换器修复总结

本文档记录了最近对数据集转换器的重要修复。

## 修复 1: H5+MP4 格式支持多层嵌套目录结构

### 问题描述
- **错误**: `FileNotFoundError: No HDF5 file found in .../cover_the_pot_2`
- **原因**: 原代码只支持最多3层嵌套，但 RoboBrain 数据集有4层结构：
  ```
  cover_the_pot/                    # 任务根目录
  ├── cover_the_pot_white/         # 颜色变体 (第1层)
  │   └── cover_the_pot_2/         # 批次目录 (第2层)
  │       ├── 1340/                # episode目录 (第3层)
  │       │   └── *.hdf5           # HDF5文件 (第4层)
  │       └── 1341/
  ```

### 解决方案
- **文件**: `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_h5_mp4.py`
- **修改**: 将 `max_depth` 从 3 增加到 5
- **新增**: 跳过隐藏目录和特殊目录（以 `.` 或 `@` 开头）
- **结果**: 成功找到 392 个 episodes（包括 cover_the_pot_2 下的 93 个）

### 代码变更
```python
# 修改前
def find_episode_dirs(path: Path, max_depth: int = 3, current_depth: int = 0):
    ...

# 修改后
def find_episode_dirs(path: Path, max_depth: int = 5, current_depth: int = 0):
    """递归查找episode目录（最多支持5层嵌套）"""
    ...
    # 跳过隐藏目录和特殊目录
    if sub_dir.is_dir() and not sub_dir.name.startswith('.') and not sub_dir.name.startswith('@'):
        ...
```

---

## 修复 2: Yinhe (银河通用) 数据集字段名称不匹配

### 问题描述
- **错误**: `IndexError: Frame index out of range in JSON data. JSON path: 'cmd_body_joint', length: 0`
- **原因**: 配置文件中的字段名与实际JSON数据不匹配

### 字段名映射

| 配置中使用的字段名（错误）          | 实际JSON中的字段名（正确）         |
|----------------------------------|----------------------------------|
| `body_state_joint_position`      | `state_body_joint_position`      |
| `front_head_state_joint_position`| `state_front_head_joint`         |
| `left_arm_state_joint_position`  | `state_left_arm_joint_position`  |
| `left_arm_state_gripper_width`   | `state_left_arm_gripper_width`   |
| `right_arm_state_joint_position` | `state_right_arm_joint_position` |
| `right_arm_state_gripper_width`  | `state_right_arm_gripper_width`  |
| `left_arm_cmd_joint_position`    | `cmd_left_joint_state`           |
| `right_arm_cmd_joint_position`   | `cmd_right_joint_state`          |

### 解决方案
- **文件**: `scripts/format_converters/tolerobot/configs/converter_config_yinhe.yaml`
- **修改**: 更新所有state和action字段的 `json_path` 配置
- **特殊处理**: 
  - `cmd_body_joint` 和 `cmd_head_joint_state` 为空（长度0）
  - Body和Head的action改用state数据（因为cmd数据不可用）

### 数据特征
```
视频帧数: 645
State数据: ~5600条 (采样率 8-9x)
Command数据: ~2261条 (采样率 3.5x)
cmd_body_joint: 0条 (空)
cmd_head_joint_state: 0条 (空)
```

---

## 修复 3: 路径字符串前导/尾随空格问题

### 问题描述
- **错误**: `FileNotFoundError: Dataset path /mnt/.../task_45_倒水—外骨骼采集025 does not exist.`
- **原因**: 数据库或配置中的路径字符串包含前导或尾随空格

### 测试结果
```python
# 无空格: Path.exists() = True
path = "/mnt/nas/.../task_45_倒水—外骨骼采集025"  

# 有尾随空格: Path.exists() = False  ❌
path = "/mnt/nas/.../task_45_倒水—外骨骼采集025 "  

# 去空格后: Path.exists() = True  ✅
path = Path("/mnt/nas/.../task_45_倒水—外骨骼采集025 ".strip())
```

### 解决方案

#### 1. client.py 中的路径预处理
```python
# 修改前
dataset_path = Path(task_content.get(DATASET_PATH))

# 修改后
dataset_path_str = task_content.get(DATASET_PATH)
if isinstance(dataset_path_str, str):
    dataset_path_str = dataset_path_str.strip()
dataset_path = Path(dataset_path_str)
```

#### 2. lerobot_format_converter.py 中的双重保护
```python
# 新增路径清理逻辑
if isinstance(dataset_path, str):
    dataset_path = Path(dataset_path.strip())
elif isinstance(dataset_path, Path):
    dataset_path = Path(str(dataset_path).strip())

if not dataset_path.exists():
    raise FileNotFoundError(
        f"Dataset path {dataset_path} does not exist.\n"
        f"  Path repr: {repr(str(dataset_path))}\n"
        f"  Path length: {len(str(dataset_path))}\n"
        f"  Please check for trailing spaces or special characters."
    )
```

---

## 修复 4: agilex_cobot_decoupled_magic (aloha15000条) 新数据集支持

### 数据集特征
- **路径**: `/mnt/nas/synnas/docker/外部数据/aloha15000条`
- **结构**: 任务/颜色/episode (3层嵌套)
  ```
  bottle_back_shelf-AH202503280005/
  ├── blue/          (100 episodes)
  ├── brown/         (100 episodes)
  ├── green/         (100 episodes)
  ├── grey/          (100 episodes)
  ├── pink/          (100 episodes)
  └── white/         (99 episodes)
  ```
- **Episode结构**: `data.hdf5` + 3个MP4视频
  - `front.mp4` (1280x720 @ 30fps)
  - `left.mp4` (1280x720 @ 30fps)
  - `right.mp4` (1280x720 @ 30fps)
- **数据维度**: 14D (7+7: 每臂6关节+1夹爪)
- **HDF5结构**: 扁平的 `qpos` 和 `action`（无 observations 嵌套）

### 解决方案
- **新建配置**: `converter_config_agilex_cobot_decoupled_magic_aloha15000.yaml`
- **FPS**: 30 (视频实际帧率)
- **相机命名**: front/left/right (不是 cam_high/cam_left_wrist/cam_right_wrist)
- **HDF5路径**: 直接使用 `qpos` 和 `action` (不是 `observations/qpos`)

### 工厂配置更新
```yaml
agilex_cobot_magic:
  - version: h5_mp4_aloha15000
    verison_description: agilex_cobot_decoupled_magic/aloha15000条 dataset with HDF5+MP4 (14D, flat structure, 30fps, front/left/right videos)
    module: robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_h5_mp4
    class: LerobotFormatConverterH5Mp4
    converter_config_path: converter_config_agilex_cobot_decoupled_magic_aloha15000.yaml
```

### 测试结果
- ✅ 成功找到 599 个episodes（bottle_back_shelf任务）
- ✅ 所有字段名匹配
- ✅ 视频帧数与HDF5时间步一致（342帧）

---

## 验证清单

### H5+MP4 转换器
- [x] 支持1-5层目录嵌套
- [x] 跳过 `.` 和 `@` 开头的特殊目录
- [x] 正确识别episode目录（包含 .hdf5 或 .h5 文件）
- [x] 成功测试 RoboBrain cover_the_pot (4层嵌套, 392 episodes)
- [x] 成功测试 aloha15000条 (3层嵌套, 599 episodes)

### Yinhe 配置
- [x] 所有state字段名修正 (state_XXX)
- [x] 所有action字段名修正 (cmd_XXX_joint_state)
- [x] Body/Head action 使用 state 数据（cmd数据为空）
- [x] Left/Right arm action 使用 cmd 数据
- [x] 配置验证通过（所有字段匹配）

### 路径处理
- [x] client.py 中 strip() 路径字符串
- [x] lerobot_format_converter.py 中双重保护
- [x] 增强错误消息（显示repr和长度）
- [x] 测试通过（带空格路径正确处理）

---

## 影响范围

### 修改的文件
1. `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_h5_mp4.py`
   - `_get_all_episode_dirs()` 方法

2. `scripts/format_converters/tolerobot/configs/converter_config_yinhe.yaml`
   - 所有 state 和 action 字段的 json_path

3. `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter.py`
   - `LerobotFormatConverterFactory.create_converter()` 方法

4. `src/robocoin_dataset/format_converter/tolerobot/client.py`
   - `_sync_process_task()` 方法

### 新建的文件
1. `scripts/format_converters/tolerobot/configs/converter_config_agilex_cobot_decoupled_magic_aloha15000.yaml`
2. `test_aloha15000_config.py`
3. `test_nested_episodes.py`

### 更新的配置
1. `scripts/format_converters/tolerobot/configs/converter_factory_config.yaml`
   - 新增 h5_mp4_aloha15000 版本
   - 更新描述（aloha → agilex_cobot_decoupled_magic）

---

## 修复 5: H5+JPG 格式支持多层嵌套目录结构

### 问题描述
- **错误**: `IndexError: Episode index out of range. Available episodes: 0`
- **路径**: `/mnt/nas/synnas/docker2/外部数据/软通天擎/jx01/zy/102_备料区场景11/490`
- **原因**: H5+JPG 转换器只搜索一层深度，但数据有2层嵌套：
  ```
  490/                          # 子任务目录
  └── A2D0015AC00587/           # 批次目录 (第1层)
      ├── 174549/               # episode目录 (第2层)
      │   ├── aligned_joints.h5
      │   ├── camera/
      │   └── ...
      └── 174552/
  ```

### 解决方案
- **文件**: `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_h5_jpg.py`
- **修改**: 
  - 将 `_get_all_episode_dirs()` 从单层 `glob("*")` 改为递归查找
  - 支持最多5层嵌套
  - 跳过隐藏目录和特殊目录（`.` 和 `@` 开头）
  - Episode 判断标准：包含 `aligned_joints.h5` 文件
- **测试结果**: ✅ 成功找到 448 个 episodes

### 代码变更
```python
# 修改前（只搜索一层）
def _get_all_episode_dirs(self, task_path: Path) -> list[Path]:
    episodes = [
        item for item in task_path.glob("*")
        if item.is_dir() and (item / "aligned_joints.h5").exists()
    ]
    return sorted(episodes)

# 修改后（递归搜索5层）
def _get_all_episode_dirs(self, task_path: Path) -> list[Path]:
    """获取所有 episode 目录（支持嵌套结构）"""
    def find_episode_dirs(path: Path, max_depth: int = 5, current_depth: int = 0):
        if current_depth > max_depth:
            return []
        
        # 检查是否包含 aligned_joints.h5
        if (path / "aligned_joints.h5").exists():
            return [path]
        
        # 递归搜索子目录
        episode_dirs = []
        for sub_dir in path.iterdir():
            if sub_dir.is_dir() and not sub_dir.name.startswith('.') and not sub_dir.name.startswith('@'):
                episode_dirs.extend(find_episode_dirs(sub_dir, max_depth, current_depth + 1))
        return episode_dirs
    
    return sorted(find_episode_dirs(task_path))
```

---

## 后续建议

1. **路径验证增强**
   - 考虑在数据库写入时就进行路径清理
   - 添加路径规范化验证脚本

2. **配置验证工具**
   - 创建自动化工具验证配置文件字段名
   - 在运行前检查实际数据字段与配置是否匹配

3. **嵌套深度监控**
   - 记录数据集的实际嵌套深度
   - 如果发现超过5层的结构，发出警告

4. **字段名规范化**
   - 建立字段命名规范文档
   - 统一不同数据集的字段命名模式

5. **统一递归搜索逻辑**
   - H5+MP4 和 H5+JPG 转换器都已实现递归搜索
   - 考虑提取为公共基类方法，避免代码重复

---

## 修复 6: H5+MP4 转换器相机名称键不匹配

### 问题描述
- **错误**: `KeyError: 'Camera cam_front not found in episode 0'`
- **数据集**: aloha15000条 (agilex_cobot_decoupled_magic)
- **原因**: 图像缓冲区字典和图像获取使用不同的键
  - 缓冲区准备时：使用顶层 `cam_name` (如 `cam_front_rgb`)
  - 图像获取时：使用 `args.cam_name` (如 `cam_front`)
  - 结果：字典键不匹配，无法找到相机

### 配置结构
```yaml
features:
  observation:
    images:
      - cam_name: cam_front_rgb      # 顶层 cam_name（用于LeRobot格式）
        args:
          cam_name: cam_front          # args 中的 cam_name（用于查找视频文件）
          video_file_pattern: "*front.mp4"
```

### 解决方案
- **文件**: `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_h5_mp4.py`
- **方法**: `_prepare_episode_images_buffer()`
- **修改**: 统一使用 `args.cam_name` 作为字典键

### 代码变更
```python
# 修改前（错误）
def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int):
    ...
    for image_config in image_configs:
        cam_name = image_config.get(CAM_NAME_KEY)  # 使用顶层 cam_name
        video_pattern = image_config.get(ARGS_KEY, {}).get('video_file_pattern', '*')
        ...
        images[cam_name] = frames  # 字典键: cam_front_rgb
    
    # 后续在 _get_frame_image 中
    cam_name = args_dict.get(CAM_NAME_KEY)  # 从 args 获取: cam_front
    return images_buffer[cam_name]  # KeyError! cam_front 不在字典中

# 修改后（正确）
def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int):
    ...
    for image_config in image_configs:
        # 从 args 中获取 cam_name，保持一致性
        args = image_config.get(ARGS_KEY, {})
        cam_name = args.get(CAM_NAME_KEY)  # 使用 args.cam_name
        video_pattern = args.get('video_file_pattern', '*')
        ...
        images[cam_name] = frames  # 字典键: cam_front
    
    # 后续在 _get_frame_image 中
    cam_name = args_dict.get(CAM_NAME_KEY)  # 从 args 获取: cam_front
    return images_buffer[cam_name]  # 成功！cam_front 在字典中
```

### 影响范围
- **影响数据集**: 所有使用 H5+MP4 格式的数据集
- **必须更新**: 所有相机配置必须同时包含顶层 `cam_name` 和 `args.cam_name`
- **配置示例**:
  ```yaml
  - cam_name: cam_front_rgb       # LeRobot格式中的相机名
    args:
      cam_name: cam_front           # 用于视频文件查找和缓冲区键
      video_file_pattern: "*front.mp4"
  ```

---

## 后续建议

1. **路径验证增强**
   - 考虑在数据库写入时就进行路径清理
   - 添加路径规范化验证脚本

2. **配置验证工具**
   - 创建自动化工具验证配置文件字段名
   - 在运行前检查实际数据字段与配置是否匹配

3. **嵌套深度监控**
   - 记录数据集的实际嵌套深度
   - 如果发现超过5层的结构，发出警告

4. **字段名规范化**
   - 建立字段命名规范文档
   - 统一不同数据集的字段命名模式

5. **统一递归搜索逻辑**
   - H5+MP4 和 H5+JPG 转换器都已实现递归搜索
   - 考虑提取为公共基类方法，避免代码重复

6. **配置一致性检查**
   - 添加初始化时的配置一致性验证
   - 确保顶层 `cam_name` 和 `args.cam_name` 的关系明确
   - 文档化配置字段的用途和关系

---

**最后更新**: 2025年10月14日
**修复者**: GitHub Copilot
