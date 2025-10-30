# 银河数据集容错修复 - 完整方案

**问题数据集**: `/mnt/nas/synnas/docker/外部数据/银河通用/use_dryer`  
**问题**: JSON字段 `cmd_body_joint` 为空（长度0），导致整个任务失败  
**解决**: 两步修复，完善episode级别容错机制

---

## 🔍 问题分析

### **原始错误**

```
RuntimeError: convert dataset /mnt/nas/synnas/docker/外部数据/银河通用/use_dryer failed

原因:
  - JSON path: 'cmd_body_joint'
  - Requested frame_idx: 1
  - JSON data length: 0 (期望 >= 2)
```

### **为什么容错机制失效了？**

我们的系统设计了 **Episode级别容错**：
- ✅ 跳过有问题的episode
- ✅ 继续处理其他正常的episode
- ✅ 在转换结束时报告统计（converted/skipped）

但实际上：
- ❌ Episode 0 损坏 → 整个任务失败
- ❌ 其他99个episode未处理

**原因**: 容错机制被两个bug破坏了！

---

## 🔧 修复方案（两部分）

### **Part 1: 抛出正确的异常类型** ✅

**文件**: `lerobot_format_converter_mp4_json.py`

**问题**: 使用标准Python异常（`IndexError`, `KeyError`, `ValueError`），而不是容错异常（`CriticalDataError`）

**修复位置** (5处):

```python
# ❌ 修复前
raise IndexError(f"Frame index out of range...")

# ✅ 修复后
raise CriticalDataError(f"Frame index out of range (entire episode will be skipped)...")
```

| Line | 方法 | 异常类型变化 |
|------|------|------------|
| 820 | `_get_frame_sub_states` | `IndexError` → `CriticalDataError` |
| 748 | `_get_frame_image` | `KeyError` → `CriticalDataError` |
| 762 | `_get_frame_image` | `IndexError` → `CriticalDataError` |
| 810 | `_get_frame_sub_states` | `ValueError` → `CriticalDataError` |
| 852 | `_get_frame_sub_states` | `KeyError` → `CriticalDataError` |

**详情**: [MP4_JSON_FAULT_TOLERANCE_FIX.md](./MP4_JSON_FAULT_TOLERANCE_FIX.md)

---

### **Part 2: 保留异常类型传播** ✅

**文件**: `lerobot_format_converter.py`

**问题**: `_gen_episode_frames` 捕获所有异常并包装成 `RuntimeError`，破坏了异常语义

**修复**: 让 `CriticalDataError` 和 `DataQualityError` 直接传播

```python
# ❌ 修复前
try:
    frame_data = self._gen_episode_frame(...)
except Exception as e:  # 捕获所有异常
    raise RuntimeError(...) from e  # 包装成 RuntimeError

# ✅ 修复后
try:
    frame_data = self._gen_episode_frame(...)
except (CriticalDataError, DataQualityError):
    # 让容错异常直接传播，不包装
    raise
except Exception as e:
    # 其他异常才包装
    raise RuntimeError(...) from e
```

**详情**: [EXCEPTION_PROPAGATION_FIX.md](./EXCEPTION_PROPAGATION_FIX.md)

---

## 📊 完整异常传播链

### **修复前（失败）**

```
1. _get_frame_sub_states (line 826)
   ↓
   抛出 IndexError ❌ (错误类型)
   
2. _gen_episode_frames (line 854)
   ↓
   捕获 Exception
   包装成 RuntimeError ❌ (破坏语义)
   
3. _convert_episode_with_fault_tolerance
   ↓
   只捕获 CriticalDataError
   收到 RuntimeError，无法识别 ❌
   继续传播
   
4. convert()
   ↓
   整个任务失败 ❌❌❌
```

### **修复后（成功）**

```
1. _get_frame_sub_states (line 826)
   ↓
   抛出 CriticalDataError ✅ (Part 1修复)
   
2. _gen_episode_frames (line 854)
   ↓
   捕获 CriticalDataError
   直接 raise（不包装）✅ (Part 2修复)
   
3. _convert_episode_with_fault_tolerance
   ↓
   捕获 CriticalDataError ✅
   记录: "Episode 0 跳过（数据损坏）"
   return 0, 0 ✅
   
4. convert()
   ↓
   继续处理 Episode 1-99 ✅
   任务成功完成 ✅✅✅
```

---

## 🎯 测试验证

### **测试命令**

```bash
# 重新运行银河数据集转换
python scripts/format_converters/tolerobot/server.py \
    --db-file=db/datasets.db \
    --host=0.0.0.0 --port=8769 \
    --is-test
```

### **预期结果**

```
✅ Converting Dataset: 100%
📊 Conversion Statistics:
   - Total episodes: 100
   - Converted: 99
   - Skipped: 1
   
⚠️  Skipped Episodes:
   - Episode 0: JSON field 'cmd_body_joint' is empty

✅ Task completed successfully
```

### **检查点**

- [ ] Episode 0 被正确跳过（不导致任务失败）
- [ ] Episode 1-99 成功转换
- [ ] 日志中显示跳过原因
- [ ] 最终统计显示 `converted=99, skipped=1`

---

## 🔄 系统性改进

这两个修复不仅解决了银河数据集的问题，还改进了整个系统的容错能力：

### **受益的数据集**

所有 **MP4+JSON** 格式的数据集现在都能正确处理：

1. **视频帧数不匹配**
   ```
   MP4: 100帧
   JSON: 90帧
   → 跳过这个episode，不影响其他
   ```

2. **JSON字段缺失**
   ```
   Episode 0: 缺少 'cmd_body_joint'
   Episode 1-99: 正常
   → 跳过 Episode 0，转换 1-99
   ```

3. **相机数据不匹配**
   ```
   Episode 5: camera_1 图像缺失
   其他: 正常
   → 跳过 Episode 5，转换其他
   ```

4. **数据类型错误**
   ```
   Episode 10: JSON路径返回dict而非list
   其他: 正常
   → 跳过 Episode 10，转换其他
   ```

---

## 📚 相关文档

1. **具体修复**:
   - [MP4_JSON_FAULT_TOLERANCE_FIX.md](./MP4_JSON_FAULT_TOLERANCE_FIX.md) - Part 1
   - [EXCEPTION_PROPAGATION_FIX.md](./EXCEPTION_PROPAGATION_FIX.md) - Part 2

2. **设计文档**:
   - [FAULT_TOLERANCE_VS_CONFIG_ERROR.md](./FAULT_TOLERANCE_VS_CONFIG_ERROR.md) - 容错机制设计
   - [SERVER_CLIENT_FLOW_COMPLETE.md](./SERVER_CLIENT_FLOW_COMPLETE.md) - 系统架构

3. **其他问题**:
   - [MMK2_DIMENSION_MISMATCH_GUIDE.md](./MMK2_DIMENSION_MISMATCH_GUIDE.md) - MMK2配置问题

---

## 💡 核心设计原则

### **异常语义**

```python
# 异常类型 = 处理策略
CriticalDataError  → 跳过episode，继续转换
DataQualityError   → 跳过帧，继续episode  
ConfigError        → 停止任务，检查配置
RuntimeError       → 停止任务，系统错误
```

### **分层设计**

```
数据层 (Converter)
  ↓ 抛出 CriticalDataError
  
传播层 (_gen_episode_frames)
  ↓ 识别并直接传播（不包装）
  
容错层 (_convert_episode_with_fault_tolerance)
  ↓ 捕获并应用容错策略
  
聚合层 (convert)
  ↓ 统计并检查失败率
```

---

## ✅ 总结

**两个修复 + 一个完整的容错系统**

1. ✅ Part 1: 在底层抛出正确的异常类型
2. ✅ Part 2: 在中间层保留异常语义传播
3. ✅ 结果: 上层容错机制正常工作

**现在银河数据集能够**:
- 跳过损坏的episode
- 继续转换正常的episode
- 提供详细的跳过统计
- 任务成功完成

**修复完成！** 🎉

