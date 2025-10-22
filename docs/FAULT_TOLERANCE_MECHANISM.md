# 数据转换容错与跳过机制总结

## 概述

本文档详细说明数据转换系统中所有会导致episode被跳过或转换停止的情况。系统采用**智能容错机制**，区分配置错误和数据质量问题。

---

## 核心设计原则

### 1. **Episode级容错，帧级不容错**
- **任何单帧错误都会导致整个episode被跳过**
- 原因：跳过单帧会破坏observation-action的时间对齐关系
- 保证数据的时序连续性

### 2. **严格模式与非严格模式**
- **严格模式**：前N个episode（默认3个），错误会被视为配置问题，立即停止转换
- **非严格模式**：后续episodes，错误会被视为数据质量问题，跳过episode继续转换
- **失败率阈值**：如果前N个episode失败率超过80%，判定为配置错误，停止转换

### 3. **异常分类体系**

```
ConverterError (基类)
├── ConfigError          → 配置错误，立即停止整个转换
├── DataQualityError     → 数据质量问题，跳过当前帧（实际会升级为跳过整个episode）
├── CriticalDataError    → 严重数据错误，跳过整个episode
│   └── FrameCountMismatchError  → 帧数不匹配（特殊的CriticalDataError）
└── ResourceError        → 系统资源问题
```

---

## Episode跳过场景详解

### 场景1: H5文件损坏 (Corrupted H5 Files)

**触发位置**: `lerobot_format_converter_h5.py`

#### 1.1 **"bad global heap collection signature"**
```python
# 文件: lerobot_format_converter_h5.py, 行891-901
except OSError as e:
    if "bad global heap collection signature" in error_str:
        raise ValueError("H5 file corruption detected")
```
- **触发时机**: 尝试打开或读取H5文件时
- **处理方式**: 
  - 在 `_get_episode_frames_num` 中被捕获，返回 `-1`
  - 在 `_get_episode_h5_data` 中被捕获，抛出 `ValueError`
  - 上层转换为 `CriticalDataError`，跳过episode
- **典型案例**: `agilex_cobot_decoupled_magic:masterpuppet_version/episode_4.hdf5`

#### 1.2 **"unable to open file"**
```python
# 文件: lerobot_format_converter_h5.py, 行1045-1054
elif "unable to open file" in error_str.lower():
    error_msg = "H5 File Access Error: Cannot open H5 file"
```
- **触发时机**: H5文件无法打开（权限、锁定、格式错误）
- **处理方式**: 抛出 `ValueError`，转换为 `CriticalDataError`

#### 1.3 **"bad object header version number"**
```python
# 例子: agilex masterpuppet episode_4
OSError: Unable to synchronously open file (bad object header version number)
```
- **触发时机**: H5文件头部损坏或版本不兼容
- **处理方式**: 同上，抛出 `ValueError`

---

### 场景2: H5帧数不一致 (Frame Count Mismatch in H5)

**触发位置**: `lerobot_format_converter_h5.py::_get_episode_frames_num`

#### 2.1 **多个sub_state数据集帧数不同**
```python
# 文件: lerobot_format_converter_h5.py, 行807-889
if frame_counts_dict:
    min_frame = min(frame_counts_dict.values())
    max_frame = max(frame_counts_dict.values())
    if min_frame != max_frame:
        # 自动移动到 error/ 目录
        # 返回 -1 表示跳过
```

**示例**:
```
observations/qpos: 500 frames
observations/qvel: 498 frames  ❌ 不一致
actions/joint_positions: 500 frames
```

- **自动处理**: 
  1. 在H5文件所在目录创建 `error/` 子目录
  2. 将问题文件移动到 `error/` 目录
  3. 返回 `-1` 标记episode需跳过
  4. 记录详细日志
- **如果移动失败**: 抛出 `ValueError` 并提供手动移动命令

---

### 场景3: 视频文件问题

#### 3.1 **MP4帧数与JSON/H5数据不匹配** (MP4+JSON, H5+MP4)
**触发位置**: 
- `lerobot_format_converter_h5_mp4.py::_prevalidate_files`
- `lerobot_format_converter_mp4_json.py::_prevalidate_files`

```python
# 文件: lerobot_format_converter_mp4_json.py, 行261-269
if video_frames != expected_frames:
    raise ValueError(
        f"帧数不匹配:\n"
        f"  视频: {video_frames} 帧\n"
        f"  JSON: {expected_frames} 帧"
    )
```
- **处理方式**: 在预验证阶段就会被检测并报错
- **影响范围**: 整个转换任务会停止（如果在严格模式）

#### 3.2 **视频文件不存在或损坏**
```python
# 文件: lerobot_format_converter_mp4_json.py, 行580-588
except FileNotFoundError:
    failed_cameras.append(f"{cam_name}: File not found")
except RuntimeError as e:
    failed_cameras.append(f"{cam_name}: {e}")
```
- **处理方式**: 记录失败，根据模式决定跳过或停止

#### 3.3 **压缩视频Blob损坏** (Zhipingfang compressed)
**触发位置**: `lerobot_format_converter_h5.py::_get_frame_image`
```python
# 临时MP4文件写入失败或OpenCV无法读取
cv2.VideoCapture(temp_mp4_path)
```
- **处理方式**: 抛出异常，转换为 `CriticalDataError`

---

### 场景4: BSON文件问题 (MMK2)

**触发位置**: `lerobot_format_converter_mmk2.py`

#### 4.1 **BSON解析失败**
```python
# 自定义BSON解析器
data = parse_bson_file(bson_file_path)
```
- **可能原因**: 文件截断、格式错误、编码问题
- **处理方式**: 抛出异常 → `CriticalDataError`

#### 4.2 **JPG图像文件损坏**
```python
# 文件: lerobot_format_converter_mmk2.py, 行609-612
except OSError as e:
    if "truncated" in str(e):
        raise ValueError(f"Image file truncated: {image_path}")
```
- **处理方式**: 抛出 `ValueError` → `CriticalDataError`

---

### 场景5: JSON文件问题 (MP4+JSON, Leju Waibu)

#### 5.1 **JSON解析失败**
**触发位置**: 
- `lerobot_format_converter_mp4_json.py`
- `lerobot_format_converter_leju_waibu.py`

```python
# 文件: lerobot_format_converter_mp4_json.py, 行166-169
except json.JSONDecodeError as e:
    raise ValueError(
        f"❌ MP4+JSON文件解析失败\n"
        f"   文件：{json_file}\n"
        f"   Error: {e}"
    )
```
- **常见原因**: 语法错误、不完整的JSON、编码问题
- **处理方式**: 抛出 `ValueError` → `CriticalDataError`

#### 5.2 **JSON编码错误**
```python
# 文件: lerobot_format_converter_mp4_json.py, 行181-186
except UnicodeDecodeError as e:
    raise ValueError(
        f"❌ MP4+JSON文件编码错误\n"
        f"   文件：{json_file}"
    )
```

---

### 场景6: ROS Bag/MCAP问题

#### 6.1 **MCAP文件损坏或无法打开**
**触发位置**: `lerobot_format_converter_mcap.py`
```python
from mcap.reader import make_reader
reader.iter_messages()  # 可能失败
```
- **处理方式**: 抛出异常 → `CriticalDataError`

#### 6.2 **消息反序列化失败**
```python
# ROS2 CDR消息解析
parse_cdr_joint_state(msg.data)
```
- **特殊处理**: 实现了自定义CDR解析器作为fallback
- **如果仍失败**: 抛出异常 → `CriticalDataError`

---

### 场景7: 数据字段缺失或路径错误

#### 7.1 **H5路径不存在**
```python
# 文件: lerobot_format_converter_h5.py, 行385-390
except KeyError as e:
    raise KeyError(
        f"❌ Missing required 'h5_path' in args_dict.\n"
        f"   Available keys: {available_keys}"
    )
```
- **原因**: 配置文件中的 `h5_path` 在实际H5文件中不存在
- **严格模式**: 升级为 `ConfigError`，停止转换
- **非严格模式**: 转换为 `CriticalDataError`，跳过episode

#### 7.2 **JSON路径提取失败**
```python
# 文件: lerobot_format_converter_mp4_json.py
# 使用json_path提取数据失败
value = extract_json_path(data, json_path)
```

---

### 场景8: 数据维度/索引越界

#### 8.1 **帧索引超出范围**
```python
# 文件: lerobot_format_converter_h5.py, 行432-440
except IndexError as e:
    max_frames = len(images_buffer[h5_path])
    raise IndexError(
        f"❌ Frame index out of range.\n"
        f"   Requested: {frame_idx}\n"
        f"   Max frames: {max_frames}"
    )
```
- **原因**: 
  - 配置的帧数与实际数据不符
  - 帧数验证逻辑有bug
- **处理方式**: 抛出 `IndexError` → `CriticalDataError`

#### 8.2 **3D数组索引错误** (Leju Waibu)
```python
# 需要指定array_index从3D数据中提取
data = h5_data[array_index]  # array_index必须正确
```

---

### 场景9: 空Episode或有效数据不足

#### 9.1 **Episode完全为空**
```python
# 文件: lerobot_format_converter.py, 行868-885
if converted_frames == 0 and skipped_frames == 0:
    self._conversion_stats['skipped_episodes'] += 1
    self.logger.info("⏭️ 跳过空episode")
```

#### 9.2 **有效帧数低于阈值**
```python
# 文件: exceptions.py, 行81-84
if valid_frames / total_frames < 0.5:
    raise CriticalDataError(
        f"有效帧数仅 {valid_frames}/{total_frames} (低于50%)"
    )
```

---

### 场景10: 文件系统问题

#### 10.1 **文件不存在**
```python
# 各converter的_prevalidate_files
except FileNotFoundError as e:
    raise FileNotFoundError(f"❌ Required file not found: {file_path}")
```

#### 10.2 **权限错误**
```python
# 移动文件到error/目录失败
except PermissionError:
    self.logger.error("无法移动文件，权限不足")
```

---

## 异常处理流程图

```
Frame处理异常
    ↓
DataQualityError?
    ├─ 是 → 严格模式? 
    │       ├─ 是 → ConfigError → 停止整个转换
    │       └─ 否 → CriticalDataError → 跳过Episode
    └─ 否 → 其他Exception?
            ├─ 严格模式 → ConfigError → 停止
            └─ 非严格模式 → CriticalDataError → 跳过Episode

Episode转换完成
    ↓
converted_frames == 0?
    ├─ 是 → 记录为跳过，继续下一个episode
    └─ 否 → 成功，保存episode

全局检查（在第N个episode后）
    ↓
失败率 > 80%?
    ├─ 是 → ConfigError → 停止整个转换
    └─ 否 → 继续转换
```

---

## 统计与日志

### 转换统计信息
```python
_conversion_stats = {
    'total_episodes': 100,           # 尝试转换的总episodes
    'successful_episodes': 95,        # 成功转换的episodes
    'skipped_episodes': 5,            # 跳过的episodes
    'total_frames': 50000,            # 成功转换的总帧数
    'skipped_frames': 0,              # 跳过的帧数（当前设计下始终为0）
    'skip_details': [...]             # 最近50条跳过详情
}
```

### 跳过详情示例
```python
{
    'episode': 42,
    'task': 'pick_and_place',
    'task_episode': 12,
    'reason': 'H5 file corruption: bad global heap collection signature',
    'skipped_entire_episode': True
}
```

---

## 特殊优化：自动文件移动

对于H5帧数不一致的情况，系统会**自动将问题文件移动到error/子目录**：

```bash
# 原始位置
/dataset/task_name/episode_5.hdf5

# 移动后
/dataset/task_name/error/episode_5.hdf5
```

**优点**:
1. 问题文件被隔离，不影响后续episode的转换
2. 问题文件仍保留，便于调试和修复
3. 自动化处理，无需手动干预

**失败时的fallback**:
- 如果自动移动失败（权限、磁盘空间等），会在日志中提供手动移动命令
- 抛出详细的 `ValueError`，包含完整的错误信息和建议操作

---

## 实际案例

### 案例1: Agilex Masterpuppet Episode 4
```
文件: agilex_cobot_decoupled_magic:masterpuppet_version/episode_4.hdf5
错误: OSError: Unable to synchronously open file (bad object header version number)
处理: 
  1. _get_episode_h5_data 捕获 OSError
  2. 检测到 "bad object header version number"
  3. 抛出 ValueError("H5 File Corruption Error...")
  4. 上层捕获为 CriticalDataError
  5. 跳过episode 4，继续转换episode 5+
  6. 记录到 skip_details
```

### 案例2: H5帧数不一致
```
文件: /data/task_name/episode_10.hdf5
问题: 
  observations/qpos: 500 frames
  observations/qvel: 498 frames
处理:
  1. _get_episode_frames_num 检测到不一致
  2. 创建 /data/task_name/error/ 目录
  3. 移动文件到 error/episode_10.hdf5
  4. 返回 -1
  5. 主循环检测到 frames_num == -1
  6. 跳过episode 10
  7. 日志记录完整错误信息
```

### 案例3: 严格模式失败率过高
```
场景: 前3个episode中有2个失败
计算: 失败率 = 2/3 = 66.7% < 80%
结果: 继续转换（未超过阈值）

场景: 前3个episode中有3个失败
计算: 失败率 = 3/3 = 100% > 80%
结果: 抛出 ConfigError，停止整个转换
建议: 
  1. 检查配置文件字段路径
  2. 使用 diagnose_converter_config.py 诊断
  3. 检查数据集格式是否匹配
```

---

## 性能优化相关的容错

### H5FileCache
- **场景**: H5文件句柄缓存，避免重复打开
- **容错**: 打开失败时会清理缓存，重试一次
- **错误传播**: 如果仍失败，向上抛出 `ValueError`

### LazyVideoReader
- **场景**: 延迟加载视频帧，减少内存占用
- **容错**: 帧读取失败时抛出 `RuntimeError`
- **错误传播**: 转换为 `CriticalDataError`

### BsonFileCache
- **场景**: 缓存解析后的BSON数据
- **容错**: 解析失败时不缓存，直接抛出异常

---

## 建议与最佳实践

### 1. 预验证（Prevalidation）
在正式转换前：
- 检查所有必需文件是否存在
- 验证关键文件的完整性（H5可打开、视频可读取）
- 检查帧数一致性（部分抽样）

### 2. 严格模式配置
```python
converter = Converter(
    strict_episodes=5,      # 前5个episode严格检查
    failure_threshold=0.7   # 失败率阈值70%
)
```
- **严格episodes数**：建议3-10，取决于数据集大小
- **失败率阈值**：建议0.6-0.8

### 3. 日志监控
- 定期检查 `skip_details` 中的跳过原因
- 关注是否有某一类错误频繁出现
- 分析成功率 < 90% 的任务

### 4. 数据质量检查
- 使用 `schema_analyzer.py` 预分析数据集
- 使用 `config_comparator.py` 验证配置完整性
- 对于大数据集，先在小样本上测试

---

## 总结

系统的容错机制设计围绕以下核心思想：

1. **快速失败与智能恢复**: 配置错误快速停止，数据错误智能跳过
2. **时序完整性优先**: 宁可跳过整个episode，也不破坏时间对齐
3. **详细日志与诊断**: 每个错误都有完整的上下文和建议
4. **自动化处理**: 如自动移动问题文件，减少手动干预
5. **统计与反馈**: 完整的转换统计，便于评估数据集质量

通过这套机制，即使面对包含损坏文件的大规模数据集，转换系统也能：
- **高鲁棒性**: 自动跳过问题episodes
- **高可诊断性**: 详细日志和错误报告
- **高效率**: 不因个别问题停止整个转换

