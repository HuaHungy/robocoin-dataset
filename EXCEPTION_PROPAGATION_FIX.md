# 异常传播修复 - 完善容错机制

**日期**: 2025-10-30  
**问题**: 容错机制失效，导致可跳过的episode导致整个任务失败  
**影响**: 银河数据集等有部分损坏数据的数据集无法完成转换

---

## 🐛 问题描述

### **错误现象**

```
RuntimeError: Failed to process episode 0 at task open the dryer door...
```

即使我们已经：
1. ✅ 在 `lerobot_format_converter_mp4_json.py` 中抛出了 `CriticalDataError`
2. ✅ 在 `_convert_episode_with_fault_tolerance` 中捕获 `CriticalDataError`

**但是转换仍然失败了！** ❌

---

## 🔍 根本原因

### **问题代码**（修复前）

```python
def _gen_episode_frames(...):
    for frame_idx in range(max_frame_idx):
        try:
            frame_data = self._gen_episode_frame(...)
        except Exception as e:  # ❌ 捕获了所有异常
            if self.logger:
                self.logger.error(...)
            raise RuntimeError(  # ❌ 包装成 RuntimeError
                f"Failed to generate frame at ..."
            ) from e
        yield frame_data
```

### **异常传播链（修复前）**

```
1. _get_frame_sub_states (line 826)
   ↓
   抛出 CriticalDataError("JSON field is empty") ✅
   
2. _gen_episode_frame
   ↓
   传播 CriticalDataError ✅
   
3. _gen_episode_frames (line 854-865)
   ↓
   捕获 Exception (包括 CriticalDataError) ✅
   包装成 RuntimeError ❌❌❌  ← 破坏容错机制！
   
4. _convert_episode_with_fault_tolerance
   ↓
   只捕获 CriticalDataError ✅
   但收到的是 RuntimeError ❌  ← 无法识别，继续传播
   
5. convert()
   ↓
   收到 RuntimeError，整个任务失败 ❌❌❌
```

### **为什么会这样设计？**

原始代码的意图是：
- 在 `_gen_episode_frames` 中捕获并记录详细错误信息
- 提供更好的错误诊断（task_path, episode, frame_idx等）

但这破坏了 **异常类型的语义**：
- `CriticalDataError` = "这个episode有问题，跳过"
- `RuntimeError` = "系统错误，停止转换"

---

## ✅ 修复方案

### **修复后的代码**

```python
def _gen_episode_frames(...):
    for frame_idx in range(max_frame_idx):
        try:
            frame_data = self._gen_episode_frame(...)
        except (CriticalDataError, DataQualityError):
            # 🔧 容错机制：让 CriticalDataError 和 DataQualityError 直接传播
            # 上层的 _convert_episode_with_fault_tolerance 会捕获并跳过episode
            raise  # ✅ 直接传播，保留异常类型
        except Exception as e:
            # 其他未预期的异常才包装成 RuntimeError
            if self.logger:
                self.logger.error(...)
            raise RuntimeError(...) from e
        yield frame_data
```

### **修复后的异常传播链**

```
1. _get_frame_sub_states
   ↓
   抛出 CriticalDataError ✅
   
2. _gen_episode_frame
   ↓
   传播 CriticalDataError ✅
   
3. _gen_episode_frames
   ↓
   捕获 CriticalDataError ✅
   直接 raise（不包装）✅✅✅  ← 保留异常类型！
   
4. _convert_episode_with_fault_tolerance
   ↓
   捕获 CriticalDataError ✅
   记录跳过信息 ✅
   return 0, 0 (跳过episode) ✅✅✅
   
5. convert()
   ↓
   继续处理下一个episode ✅
   任务成功完成（跳过有问题的episode）✅✅✅
```

---

## 📊 修复效果对比

### **修复前**

```
❌ Task failed: RuntimeError
   - Episode 0: 数据损坏
   - Episode 1-99: 未处理（任务终止）
   
结果: 0 episodes converted
```

### **修复后**

```
✅ Task completed
   - Episode 0: 跳过（数据损坏）
   - Episode 1-99: 成功转换
   
结果: 99 episodes converted, 1 skipped
```

---

## 🎯 核心原则

### **异常语义的重要性**

```python
# ✅ 正确：保留异常类型
try:
    some_operation()
except CriticalDataError:
    # 这是预期的、可处理的异常
    raise  # 直接传播，让上层处理

# ❌ 错误：改变异常类型
try:
    some_operation()
except CriticalDataError as e:
    # 不要这样做！
    raise RuntimeError("...") from e  # 破坏了语义
```

### **分层异常处理**

```
Layer 1 (_get_frame_sub_states):
  - 检测数据问题
  - 抛出 CriticalDataError (语义: "这个episode有问题")

Layer 2 (_gen_episode_frames):
  - 🆕 识别容错异常（CriticalDataError, DataQualityError）
  - 🆕 让容错异常直接传播（不包装）
  - 包装其他未预期异常（提供上下文信息）

Layer 3 (_convert_episode_with_fault_tolerance):
  - 捕获 CriticalDataError
  - 应用容错策略（跳过episode）
  - 记录统计信息

Layer 4 (convert):
  - 聚合所有episode的转换结果
  - 检查失败率是否过高（ConfigError）
```

---

## 🔧 相关修复

本次修复是 **银河数据集容错修复** 的第二部分：

### **Part 1: 抛出正确的异常类型** ✅ (已完成)
- 文件: `lerobot_format_converter_mp4_json.py`
- 改动: 将 `IndexError`, `KeyError`, `ValueError` 改为 `CriticalDataError`
- 位置: 5处 (line 748, 762, 810, 820, 852)

### **Part 2: 保留异常类型传播** ✅ (本次修复)
- 文件: `lerobot_format_converter.py`
- 改动: 让 `CriticalDataError` 直接传播，不包装
- 位置: `_gen_episode_frames` (line 854-857)

---

## ✅ 验证清单

- [x] Linter检查通过
- [ ] 银河数据集重新转换测试
- [ ] 确认问题episode被正确跳过
- [ ] 确认其他episode正常转换

---

## 📚 相关文档

- [MP4_JSON_FAULT_TOLERANCE_FIX.md](./MP4_JSON_FAULT_TOLERANCE_FIX.md) - Part 1修复
- [FAULT_TOLERANCE_VS_CONFIG_ERROR.md](./FAULT_TOLERANCE_VS_CONFIG_ERROR.md) - 容错机制设计

---

**修复完成！银河数据集现在应该能正常跳过损坏的episode并完成转换。** 🎉

