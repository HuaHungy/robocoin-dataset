# Converter深度支持完整分析报告

**生成时间**: 2025-10-22  
**报告目的**: 全面分析所有converter支持的Episode查找深度 + 数据字段深度

---

## 📊 总体概况表

| Converter | Episode查找深度 | Episode查找方式 | 数据字段深度 | 字段分隔符 |
|-----------|----------------|-----------------|--------------|------------|
| **基类 (Base)** | ♾️ 无限 (BFS) | 递归搜索`task_info.yml` | - | - |
| **H5+MP4** | ♾️ 继承基类 | BFS查找task目录 | N/A (直接切片) | - |
| **Leju Waibu** | 2层固定 | `dataset/subtask/episode` | ♾️ 无限 | `/` (h5py) |
| **MMK2 (BSON)** | ♾️ 继承基类 | 在task下找`episode*`目录 | 2-3层固定 | `/` |
| **MP4+JSON (Yinhe)** | 2-3层 | 扁平/嵌套两种模式 | ♾️ 无限 | `/` |
| **ROS Bag** | ♾️ 无限 (rglob) | 递归查找`*.bag` | N/A (直接切片) | - |
| **MCAP (Realman)** | 1层固定 | `dataset/episode_dir/*.mcap` | N/A (直接切片) | - |
| **G1 (JPG+JSON)** | 3层 (max_depth=3) | 递归模式匹配 | ♾️ 无限 | `.` |
| **JPG+JSON** | ♾️ 继承基类 | BFS查找task目录 | 2-3层固定 | - |
| **LeRobot** | 0层 (扁平) | 所有数据在一个目录 | 0层 (parquet) | - |

---

## 🔍 Part 1: Episode查找深度详细分析

### 1️⃣ **无限深度支持（理论上）**

#### **基类 (lerobot_format_converter.py)**
```python
# 行号: 350-377
def _get_dataset_task_paths(self) -> dict[Path, str]:
    """Get the paths of all tasks in the dataset."""
    dirs_to_scan = [self.dataset_path]
    task_paths_dict = {}
    while len(dirs_to_scan) > 0:
        current_path = dirs_to_scan.pop(0)
        files = Path(current_path).glob(LOCAL_TASK_INFO_FILE_NAME)
        has_task_file = False
        for file in files:
            # 找到task_info.yml，记录该目录
            task_paths_dict[file.parent] = task
            has_task_file = True
        
        if not has_task_file:
            # 继续递归搜索子目录
            sub_dirs = [item for item in Path(current_path).glob("*") if item.is_dir()]
            dirs_to_scan.extend(sub_dirs)
    
    return task_paths_dict
```

**特点**:
- ✅ 使用BFS（广度优先搜索）算法
- ✅ 理论上支持无限深度的目录嵌套
- ✅ 查找包含 `local_task_info.yaml` 的目录作为task目录
- ✅ 使用方：H5+MP4, MMK2, JPG+JSON等继承基类

**支持的结构**:
```
dataset/
  └── task_info.yml         # 深度0
  └── level1/
      └── task_info.yml     # 深度1
      └── level2/
          └── task_info.yml # 深度2
          └── ...           # 深度N (理论无限)
```

---

#### **ROS Bag Converter**
```python
# 行号: 600-639
def task_episode_rosbagfile_paths(self) -> dict[Path, list[Path]]:
    for path in self.path_task_dict.keys():
        # 首先尝试在当前目录查找bag文件
        rosbag_files = list(path.glob("*.bag"))
        
        # 如果当前目录没有，递归查找子目录
        if not rosbag_files:
            rosbag_files = list(path.rglob("*.bag"))  # ♾️ 无限深度
        
        rosbag_files = natsorted(rosbag_files)
        task_episode_paths[path] = valid_files
```

**特点**:
- ✅ 先在task目录查找，未找到则使用 `rglob` 递归搜索
- ✅ 理论上支持无限深度的bag文件查找
- ✅ 自动过滤无效和空文件
- ✅ 自然排序保证episode顺序

**支持的结构**:
```
task_path/
  ├── episode_0.bag               # 深度0 (优先)
  └── recordings/
      └── 2025/
          └── 10/
              └── episode_1.bag   # 深度N (兜底)
```

---

### 2️⃣ **固定深度支持**

#### **Leju Waibu Converter (2层固定)**
```python
# 行号: 76-140
def _get_dataset_task_paths(self) -> dict[Path, str]:
    """
    Leju dataset structure:
    dataset_path/ (e.g., Scan_code_for_weighing/)
      ├── local_dataset_info.yaml
      └── subtask/ (e.g., more_scan_code_for_weighing/)  ← 第1层
          ├── local_task_info.yaml
          └── episode_uuid/                              ← 第2层
              ├── metadata.json
              └── proprio_stats/proprio_stats.hdf5
    """
    
    # 第1层：遍历subtask目录
    subtask_dirs = [d for d in self.dataset_path.iterdir() if d.is_dir()]
    
    for subtask_dir in subtask_dirs:
        local_task_info_path = subtask_dir / "local_task_info.yaml"
        if not local_task_info_path.exists():
            continue
        
        # 第2层：遍历episode目录
        episode_dirs = [...]
        for episode_dir in episode_dirs:
            # 返回 episode_dir 作为 task_path (特殊！)
            task_paths_dict[episode_dir] = task
```

**特点**:
- ⚠️ **固定2层深度**: `dataset/subtask/episode`
- ⚠️ 特殊设计：返回的 `task_path` 实际是 **episode目录**
- ✅ 严格验证每层的标识文件（`local_task_info.yaml`, `metadata.json`）
- ✅ 适合Leju数据集的固定结构

---

#### **MCAP Converter (Realman) (1层固定)**
```python
# 行号: 268-318
def _get_dataset_task_paths(self) -> dict[Path, str]:
    """
    MCAP dataset structure:
    dataset_path/
      ├── local_task_info.yaml
      └── episode_dir_1/         ← 第1层
          └── *.mcap
      └── episode_dir_2/
          └── *.mcap
    """
    
    # 读取根目录的task info
    local_task_info_path = self.dataset_path / "local_task_info.yaml"
    with open(local_task_info_path) as f:
        task_index = yaml.safe_load(f)["task_index"]
        task = self.tasks[task_index]
    
    # 第1层：扫描子目录，查找包含.mcap文件的目录
    for subdir in self.dataset_path.iterdir():
        if subdir.is_dir():
            mcap_files = list(subdir.glob("*.mcap"))
            if mcap_files:
                task_paths_dict[subdir] = task
```

**特点**:
- ⚠️ **固定1层深度**: `dataset/episode_dir/*.mcap`
- ✅ 每个子目录作为一个episode容器
- ✅ task信息在dataset根目录
- ✅ 适合MCAP数据集的目录分组结构

**计算episode数量**:
```python
# 行号: 744-745
def _get_task_episodes_num(self, task_path: Path) -> int:
    return len(list(task_path.glob("*.mcap")))
```

---

### 3️⃣ **可配置深度支持**

#### **MP4+JSON Converter (Yinhe) (2-3层)**
```python
# 行号: 476-508
def _get_all_episode_dirs(self, task_path: Path) -> list[Path]:
    """
    支持两种结构：
    1. 扁平结构：task_path/episode_0/data.json       (深度1)
    2. 嵌套结构：task_path/xiyiji-1/20250501_record0/data.json (深度2)
    """
    # 首先检查扁平结构
    direct_episodes = [
        ep_dir for ep_dir in task_path.glob("*") 
        if ep_dir.is_dir() and (ep_dir / "data.json").exists()
    ]
    
    if direct_episodes:
        return sorted(direct_episodes)
    
    # 如果不是扁平结构，尝试嵌套结构
    nested_episodes = [
        ep_dir
        for parent_dir in task_path.glob("*")           # 第1层
        if parent_dir.is_dir()
        for ep_dir in parent_dir.glob("*")               # 第2层
        if ep_dir.is_dir() and (ep_dir / "data.json").exists()
    ]
    
    if nested_episodes:
        return sorted(nested_episodes)
    
    raise FileNotFoundError(...)
```

**特点**:
- ✅ 支持扁平结构（1层）和嵌套结构（2层）
- ✅ 自动检测并选择合适的结构
- ✅ 以 `data.json` 存在作为episode标识
- ✅ 灵活适配不同的数据集组织方式

---

#### **G1 (JPG+JSON) Converter (3层 max_depth=3)**
```python
# 行号: 868-922
def _find_episode_directories_g1(self, task_path: Path) -> list[Path]:
    """
    支持多种episode目录命名模式：
    - episode1, episode2, episode10
    - episode_1, episode_2, episode_10
    - ep1, ep2, ep10
    - ep_1, ep_2, ep_10
    - 001, 002, 010
    """
    
    # 递归搜索所有子目录（限制深度避免过深搜索）
    def find_all_directories(root_path, max_depth=3, current_depth=0):
        dirs = []
        if current_depth >= max_depth:  # 最大深度3层
            return dirs
        
        for item in root_path.iterdir():
            if item.is_dir():
                dirs.append(item)
                # 递归搜索子目录
                dirs.extend(find_all_directories(item, max_depth, current_depth + 1))
        
        return dirs
    
    all_dirs = find_all_directories(task_path, max_depth=3)
    
    # 使用正则模式匹配episode目录
    episode_patterns = [
        r"^episode(\d+)$",
        r"^episode_(\d+)$",
        r"^ep(\d+)$",
        r"^ep_(\d+)$",
        r"^(\d+)$",
    ]
    
    # 匹配并排序
    matched_episodes = [...]
    return matched_episodes
```

**特点**:
- ✅ 支持多种episode命名模式（正则匹配）
- ⚠️ **最大深度限制为3层**（避免性能问题）
- ✅ 智能episode编号提取和排序
- ✅ 回退到递归JSON搜索（如果模式匹配失败）

**回退方案**:
```python
# 行号: 817-820
# 如果智能发现失败，回退到递归搜索所有JSON文件
json_files = natsorted(list(path.rglob("*.json")))  # ♾️ 无限深度
task_episode_paths[path] = json_files
```

---

### 4️⃣ **扁平结构（0层）**

#### **LeRobot Converter**
```python
# 行号: 296-300
def _get_dataset_task_paths(self) -> dict[Path, str]:
    """For LeRobot format, all data is typically in one location"""
    tasks = self._get_tasks()
    return {self.lerobot_data_path: tasks[0]}  # 所有数据在一个目录
```

**特点**:
- ✅ 所有数据都在 `lerobot_data_path` 目录
- ✅ 使用parquet文件存储，无episode子目录
- ✅ 极简结构，适合已转换的LeRobot数据集

---

## 🔍 Part 2: 数据字段深度详细分析

### 1️⃣ **无限深度支持（动态路径解析）**

#### **MP4+JSON Converter (Yinhe)**
```python
# 行号: 718-728
json_path = args_dict.get('json_path', '')

for key in json_path.split('/'):  # 使用 '/' 分隔符
    if key:
        if not isinstance(frame_data, dict):
            raise ValueError(...)
        frame_data = frame_data.get(key, {})
```

**配置示例**:
```yaml
# Yinhe配置
observation:
  state:
    sub_state:
      - names: ["left_arm_joint_1_rad", ...]
        args:
          json_path: "observation/state/left_arm/position"  # 4层深度
          field_name: "joint"
```

**支持深度**: ♾️ 无限（理论上）  
**实际常用**: 3-4层  
**分隔符**: `/`

---

#### **G1 Converter**
```python
# 行号: 581-625
json_path = args_dict["json_path"]

for i, path_part in enumerate(json_path.split(".")):  # 使用 '.' 分隔符
    current_path = ".".join(json_path.split(".")[:i+1])
    if isinstance(data, dict) and path_part in data:
        data = data[path_part]
    else:
        # 提供详细错误和相似键查找
        raise ValueError(...)
```

**配置示例**:
```yaml
# G1配置
observation:
  state:
    sub_state:
      - names: ["left_arm_qpos_1_rad", ...]
        args:
          json_path: "states.left_arm.qpos"  # 3层深度
```

**支持深度**: ♾️ 无限（理论上）  
**实际常用**: 3-4层  
**分隔符**: `.`  
**特色**: 最详细的错误信息和相似键建议

---

#### **Leju Waibu Converter**
```python
# 行号: 656-674
h5_path = args_dict["h5_path"]
array_index = args_dict.get("array_index")  # 🆕 支持3D数组

if sub_states_buffer is not None and h5_path in sub_states_buffer:
    data = sub_states_buffer[h5_path][frame_idx]
else:
    with h5py.File(h5_file, "r") as f:
        data = f[h5_path][frame_idx]  # h5py原生支持多层路径

# 🆕 处理3D数组
if array_index is not None:
    data = data[array_index]

return np.array(data[range_from:range_to], dtype=np.float32)
```

**配置示例**:
```yaml
# Leju Waibu配置
observation:
  state:
    sub_state:
      # 2D数组（普通）
      - names: ["left_arm_joint_1_rad", ...]
        args:
          h5_path: "state/joint/position"  # 3层深度
          range_from: 0
          range_to: 7
      
      # 3D数组（特殊）
      - names: ["left_eef_pos_x_m", "left_eef_pos_y_m", "left_eef_pos_z_m"]
        args:
          h5_path: "state/end/position"  # 3层深度
          array_index: 0  # 🆕 取第0个arm（左臂）
          range_from: 0
          range_to: 3
```

**支持深度**: ♾️ 无限（由h5py库原生支持）  
**实际常用**: 3-4层  
**分隔符**: `/`（HDF5标准）  
**特色**: 支持3D数组的 `array_index` 参数

---

### 2️⃣ **固定深度支持（2-3层）**

#### **MMK2 (BSON) Converter**
```python
# 行号: 676-738
data_path = args_dict["data_path"]
field = args_dict.get("field", "pos")  # 默认使用pos字段

# 规范化路径
normalized_data_path = data_path if data_path.startswith('/') else f'/{data_path}'

# 第1层：从缓冲区获取路径对应的数据列表
data_list = sub_states_buffer["main_data"][normalized_data_path]

# 第2层：获取帧数据
frame_data = data_list[frame_idx]

# 第3层：访问 data[field]
values = frame_data["data"][field]
```

**配置示例**:
```yaml
# MMK2配置
observation:
  state:
    sub_state:
      - names: ["left_arm_joint_1_rad", ...]
        args:
          bson_file: "episode_0.bson"
          data_path: "observation.left_arm"  # 用于查找，不是实际深度
          field: "pos"                        # 实际访问: frame_data["data"]["pos"]
          range_from: 0
          range_to: 7
```

**实际访问深度**: 2-3层固定  
**路径深度**: `data_path` 仅用于查找，实际访问是 `frame_data["data"][field]`  
**分隔符**: `/` 或 `.`（用于data_path）

---

#### **JPG+JSON Converter**
```python
# 行号: 498-580
data_type = args_dict.get('data_type', 'joint')

if data_type == 'gripper':
    # 深度2: buffer_key → frame_data[field_name]
    frame_data = sub_states_buffer[buffer_key][frame_idx]
    return np.array([frame_data[field_name]], dtype=np.float32)

elif data_type == 'imu':
    # 深度3: buffer_key → frame_data[field_name][subfield]
    frame_data = sub_states_buffer[buffer_key][frame_idx]
    values = [frame_data[field_name].get(sf, 0.0) for sf in subfields]
    return np.array(values, dtype=np.float32)

else:
    # 深度2: joint_type → frame_data[field_name]
    data = sub_states_buffer[joint_type]
    frame_data = data[frame_idx]
    return frame_data[field_name][range_from:range_to]
```

**配置示例**:
```yaml
# JPG+JSON配置
observation:
  state:
    sub_state:
      # 关节数据（深度2）
      - names: ["left_arm_joint_1_rad", ...]
        args:
          data_type: "joint"
          joint_type: "puppet_left"
          field_name: "position"
      
      # IMU数据（深度3）
      - names: ["left_imu_angular_x", "left_imu_angular_y", "left_imu_angular_z"]
        args:
          data_type: "imu"
          imu_side: "pika_l"
          field_name: "angular_velocity"
          subfields: ["x", "y", "z"]
```

**支持深度**: 2-3层（硬编码）  
**分隔符**: 无（使用固定字段访问）

---

### 3️⃣ **预处理+直接切片（无深度概念）**

#### **H5+MP4 Converter (Agilex, Galaxea)**
```python
# 行号: 515
return sub_states_buffer[frame_idx, from_idx:to_idx].astype(np.float32)
```

**特点**:
- ✅ 数据在 `_prepare_episode_states_buffer` 阶段已完全展平为2D数组
- ✅ 运行时只做numpy切片，性能极高
- ✅ 适合所有维度在同一个H5 dataset的情况

**数据准备阶段**:
```python
# _prepare_episode_states_buffer 中已完成路径解析
with self._h5_file_cache.open(h5_file) as f:
    # 例如读取 /observations/qpos
    states_buffer = f[h5_path][:]  # h5py原生支持多层路径
```

---

#### **MCAP Converter (Realman)**
```python
# 行号: 800
return sub_states_buffer[frame_idx][from_idx:to_idx]
```

**特点**:
- ✅ 数据在 `_parse_mcap_episode` 阶段已解析为2D列表
- ✅ 运行时只做列表切片
- ✅ 支持自定义CDR解析（绕过rosbags bug）

**数据准备阶段**:
```python
# _parse_mcap_episode 中已完成topic解析和消息反序列化
for schema, channel, message in reader.iter_messages():
    if channel.topic == "/joint_states":
        joint_state = parse_cdr_joint_state(message.data)  # 手动CDR解析
        states_buffer.append(joint_state.position)
```

---

#### **ROS Bag Converter (Galaxea)**
```python
# 行号: 475
return np.array(state_data, dtype=np.float32)[from_idx:to_idx]
```

**特点**:
- ✅ 数据在 `_prepare_episode_states_buffer` 阶段已按topic组织
- ✅ 运行时只做数组切片
- ✅ 适合ROS topic结构的数据

**数据准备阶段**:
```python
# _get_episode_rosbag_data 中已完成topic读取和消息解析
with AnyReader([bag_file]) as reader:
    for connection, timestamp, rawdata in reader.messages():
        if connection.topic == topic_name:
            msg = deserialize_cdr(...)
            buffer[topic_name].append(msg.data)
```

---

## 📈 深度支持对比矩阵

### Episode查找深度

| Converter | 最小深度 | 最大深度 | 推荐结构 | 查找方式 |
|-----------|----------|----------|----------|----------|
| **基类 (BFS)** | 0 | ♾️ 无限 | 任意 | 递归查找`task_info.yml` |
| **H5+MP4** | 0 | ♾️ 继承 | `dataset/task/episode_X/` | 继承基类BFS |
| **Leju Waibu** | 2 | 2 | `dataset/subtask/episode/` | 固定2层遍历 |
| **MMK2** | 0 | ♾️ 继承 | `dataset/task/episode_X/` | 继承基类BFS + `episode*` |
| **MP4+JSON** | 1 | 2 | `task/episode/` 或 `task/group/episode/` | 双模式检测 |
| **ROS Bag** | 0 | ♾️ 无限 | `task/*.bag` 或任意深度 | `glob` + `rglob` |
| **MCAP** | 1 | 1 | `dataset/episode_dir/*.mcap` | 固定1层扫描 |
| **G1** | 0 | 3 | `task/episode_X/` | 模式匹配(max 3层) + rglob回退 |
| **JPG+JSON** | 0 | ♾️ 继承 | `dataset/task/episode_X/` | 继承基类BFS |
| **LeRobot** | 0 | 0 | `data/` (扁平) | 单目录 |

### 数据字段深度

| Converter | 字段深度 | 分隔符 | 解析方式 | 特色功能 |
|-----------|----------|--------|----------|----------|
| **MP4+JSON** | ♾️ 无限 | `/` | 动态循环 | 自动类型检查 |
| **G1** | ♾️ 无限 | `.` | 动态循环 | 最详细错误 + 相似键提示 |
| **Leju Waibu** | ♾️ 无限 | `/` | h5py原生 | 支持3D数组 `array_index` |
| **MMK2** | 2-3层 | `/` | 固定结构 | 两种BSON文件支持 |
| **JPG+JSON** | 2-3层 | - | 固定字段 | 多数据类型（joint/imu/gripper） |
| **H5+MP4** | N/A | - | 预处理展平 | 极致性能 |
| **MCAP** | N/A | - | 预处理展平 | 自定义CDR解析 |
| **ROS Bag** | N/A | - | 预处理展平 | Topic按需反序列化 |

---

## 💡 最佳实践建议

### 选择Episode查找策略

| 需求场景 | 推荐Converter | 理由 |
|----------|---------------|------|
| 目录结构简单、层数少 | MCAP, MP4+JSON | 固定深度，查找快 |
| 目录结构复杂、嵌套深 | 基类BFS, ROS Bag | 无限深度支持 |
| 严格固定结构 | Leju Waibu | 验证严格，错误提示清晰 |
| 需要灵活适配 | G1, MP4+JSON | 多模式检测 + 回退机制 |
| 已标准化数据集 | LeRobot | 扁平结构，最简单 |

### 选择数据字段访问策略

| 需求场景 | 推荐Converter | 理由 |
|----------|---------------|------|
| JSON嵌套结构，层数不定 | MP4+JSON, G1 | 动态路径解析 |
| H5文件，需要灵活访问 | Leju Waibu | h5py原生支持 + 3D数组 |
| 性能优先，结构固定 | H5+MP4, MCAP, ROS Bag | 预处理展平，极致性能 |
| 固定JSON结构 | JPG+JSON | 简单高效，类型安全 |
| 特定BSON格式 | MMK2 | 针对MMK2优化 |

### 性能优化策略

1. **Episode查找优化**:
   ```python
   # 优先使用 glob，避免过深递归
   episodes = list(task_path.glob("episode_*"))  # 快
   # 避免无限制 rglob（仅作回退）
   episodes = list(task_path.rglob("**/episode_*"))  # 慢
   ```

2. **数据字段访问优化**:
   ```python
   # 如果数据结构固定，预处理展平
   # 好：一次性加载并展平
   buffer = h5_file["/observations/qpos"][:]  # (N, D)
   
   # 避免：运行时动态解析（除非必要）
   for frame_idx in range(N):
       for key in path.split("/"):
           data = data[key]  # 每帧都重复解析
   ```

3. **混合策略**（推荐）:
   - **Episode查找**: 优先固定模式 → 回退到递归搜索
   - **数据访问**: 能预处理的预处理 → 动态路径作为兜底

---

## 🎯 总结

### Episode查找深度
- **最灵活**: 基类BFS, ROS Bag（理论无限）
- **最快速**: MCAP, Leju Waibu（固定深度）
- **最智能**: G1, MP4+JSON（多模式检测）

### 数据字段深度
- **最强通用性**: MP4+JSON, G1（动态解析，无限深度）
- **最佳性能**: H5+MP4, MCAP, ROS Bag（预处理展平）
- **最适合H5**: Leju Waibu（h5py原生 + 3D数组支持）

### 综合推荐
- **新数据集**：优先使用基类BFS（Episode）+ 动态路径解析（字段）
- **性能关键**：使用预处理展平策略
- **固定结构**：使用固定深度查找 + 固定字段访问

---

**文档生成**: AI Assistant  
**最后更新**: 2025-10-22  
**版本**: v2.0 (完整版：Episode + 字段)

