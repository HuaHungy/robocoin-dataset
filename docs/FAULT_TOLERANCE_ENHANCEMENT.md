# 容错机制增强总结

**日期**: 2025-10-24  
**修改内容**: 增强MP4+JSON转换器的容错能力，修复Episode 322 PosixPath错误

---

## 🐛 修复的Bug

### Bug 1: `_get_task_episodes_num` 逻辑错误

**文件**: `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter.py`

**问题**: 
```python
# ❌ 错误的逻辑（第235-237行）
def _get_task_episodes_num(self, task_path: Path) -> int:
    if task_path not in self.task_episodes_num:  # 如果不在
        return self.task_episodes_num[task_path]  # 却尝试访问它
    raise ValueError(f"Dataset task_path {task_path} not found")  # 如果在，反而抛异常
```

**影响**: 
- 当`task_path`在字典中时（正常情况），会抛出异常并显示PosixPath对象
- 这导致验证器显示：`PosixPath('/mnt/nas/...')`而不是正常的错误信息

**修复**:
```python
# ✅ 正确的逻辑
def _get_task_episodes_num(self, task_path: Path) -> int:
    if task_path in self.task_episodes_num:  # 如果在
        return self.task_episodes_num[task_path]  # 返回值
    raise ValueError(f"Dataset task_path {task_path} not found")  # 如果不在，抛异常
```

**验证**: Episode 322的错误应该会显示正常的错误信息而不是PosixPath对象。

---

## 🛡️ 增强容错机制

### 背景
MP4+JSON转换器原本将JSON解析失败和所有相机加载失败视为"结构性错误"，会立即停止转换。
用户希望这些情况也能跳过episode而不是停止整个转换，提高容错能力。

### 修改文件
`src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_mp4_json.py`

### 修改内容

#### 1. JSON解析失败时跳过Episode

**位置**: `_load_json_data()` 方法（第348-365行）

**修改前**:
```python
except json.JSONDecodeError as e:
    raise ValueError(...)  # 停止转换
except Exception as e:
    raise RuntimeError(...)  # 停止转换
```

**修改后**:
```python
except json.JSONDecodeError as e:
    from .exceptions import CriticalDataError
    raise CriticalDataError(...)  # 跳过该episode
except Exception as e:
    from .exceptions import CriticalDataError
    raise CriticalDataError(...)  # 跳过该episode
```

#### 2. 所有相机加载失败时跳过Episode

**位置**: `_prepare_episode_buffers()` 方法（第656-667行）

**修改前**:
```python
if not images:
    raise RuntimeError(
        "❌ No valid camera images loaded..."
    )  # 停止转换
```

**修改后**:
```python
if not images:
    from .exceptions import CriticalDataError
    raise CriticalDataError(
        "❌ No valid camera images loaded...\n"
        "⚠️  Skipping this episode due to all cameras failing to load."
    )  # 跳过该episode
```

#### 3. 其他Episode级错误改为CriticalDataError

修改了以下场景，使其跳过episode而不是停止转换：

| 错误场景 | 位置 | 方法 |
|---------|------|------|
| 无法从JSON确定帧数 | 410行 | `_get_episode_frames_num()` |
| 没有有效的视频帧 | 452行 | `_get_episode_frames_num()` |
| Episode有0帧 | 507行 | `_get_episode_frames_num()` |
| JSON缺少'data'键 | 708行 | `_prepare_episode_states_buffer()` |

---

## 📊 容错机制对比

### 修改前

| 错误类型 | 处理方式 | 结果 |
|---------|---------|------|
| H5文件损坏 | ✅ 跳过 | 继续转换 |
| 帧数不匹配 | ✅ 跳过 | 继续转换 |
| JSON解析失败 | ❌ 停止 | 转换失败 |
| 所有相机失败 | ❌ 停止 | 转换失败 |
| 无效帧数 | ❌ 停止 | 转换失败 |

### 修改后

| 错误类型 | 处理方式 | 结果 |
|---------|---------|------|
| H5文件损坏 | ✅ 跳过 | 继续转换 |
| 帧数不匹配 | ✅ 跳过 | 继续转换 |
| JSON解析失败 | ✅ 跳过 | 继续转换 |
| 所有相机失败 | ✅ 跳过 | 继续转换 |
| 无效帧数 | ✅ 跳过 | 继续转换 |

**注意**: 30%失败率阈值仍然存在，如果超过30%的episode失败，会停止转换并报告配置错误。

---

## 🔒 安全机制

### 1. 失败率阈值保护
- 如果episode失败率超过30%，会立即停止转换
- 这能防止配置错误或系统性数据问题时继续转换大量无效数据

### 2. 严格模式保护
- 前5个episode仍然是严格模式
- 在严格模式下，任何数据问题都会升级为ConfigError并停止转换
- 确保配置正确后才进入容错模式

### 3. 转换记录
- 所有跳过的episode都会记录到日志
- 损坏文件列表保存到`corrupted_episodes.txt`
- Episode映射保存到`episode_source_mapping.json`

---

## 📝 使用建议

### 1. 验证器报告
运行验证器后，关注以下指标：
```
- 成功率: 应该 > 70%（否则说明有系统性问题）
- 失败原因: 查看是否有集中的错误类型
- 失败分布: 是否某个任务全部失败（配置可能不匹配）
```

### 2. 正式转换
- 第一次转换建议先测试小批量数据
- 查看`corrupted_episodes.txt`了解哪些数据被跳过
- 如果失败率接近30%，停止并调查原因

### 3. 数据清洗
对于损坏的数据：
- H5文件损坏：检查存储介质是否有问题
- JSON解析失败：检查文件编码、格式
- 所有相机失败：检查视频文件完整性

---

## 🧪 测试建议

### 1. 单元测试
```bash
# 测试JSON解析失败时的容错
# 创建一个损坏的JSON文件，验证是否跳过该episode

# 测试所有相机失败时的容错
# 提供损坏的视频文件，验证是否跳过该episode
```

### 2. 集成测试
```bash
# 运行验证器，检查是否正确识别问题
python scripts/config_validation/db_validator_fixed.py

# 运行小批量转换，检查是否正确跳过问题episode
```

---

## 📌 注意事项

1. **配置问题仍会立即停止**
   - 配置文件路径错误
   - 数据类型与配置不匹配
   - 这些是严重的结构性问题，不应该跳过

2. **部分相机失败不会跳过**
   - 如果只是部分相机失败，转换会继续使用其他有效相机
   - 只有所有相机都失败时才跳过episode

3. **数据质量问题不会跳过**
   - 数据值异常（NaN、Inf等）
   - 这些会在基类的容错机制中处理

---

## 🎯 预期效果

### 成功场景
```
✅ 转换100个episodes
   - 90个成功
   - 8个跳过（JSON损坏、视频损坏等）
   - 2个跳过（帧数不匹配）
   
📊 成功率：90%
📄 corrupted_episodes.txt: 10个文件
✅ 转换完成
```

### 失败场景
```
❌ 转换100个episodes
   - 65个成功
   - 35个跳过
   
📊 失败率：35% > 30%阈值
❌ 停止转换：检测到系统性问题
💡 建议：检查配置文件和数据集
```

---

## 📚 相关文档

- [容错机制总览](./FAULT_TOLERANCE_OVERVIEW.md) (待创建)
- [异常类型说明](../src/robocoin_dataset/format_converter/tolerobot/exceptions.py)
- [转换器基类](../src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter.py)

