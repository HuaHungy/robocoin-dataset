# 相机缺失场景 - 容错修复示例

**日期**: 2025-10-30  
**问题**: Episode 766 缺少 `camera_right_wrist`，导致整个任务失败  
**数据集**: 银河通用 `/use_dryer/open_the_dryer`

---

## 🐛 问题现象

### **错误信息**

```
CriticalDataError: Camera not found in images buffer
   📹 Requested camera: 'camera_right_wrist'
   📋 Available cameras: ['camera_front_head_rgb', 'camera_left_wrist']
   📊 Camera frame counts: {'camera_front_head_rgb': 316, 'camera_left_wrist': 316}
```

### **数据情况**

```
Episode 0-765:   ✅ 3个相机都存在
Episode 766:     ❌ 只有2个相机 (缺少 camera_right_wrist)
Episode 767-999: ✅ 3个相机都存在
```

### **期望行为**

- ✅ 跳过 Episode 766 (数据不完整)
- ✅ 继续转换其他999个episode
- ✅ 任务成功完成，统计: `converted=999, skipped=1`

### **实际行为（修复前）**

- ❌ Episode 766 导致整个任务失败
- ❌ Episode 767-999 未被处理
- ❌ 任务失败，转换中断

---

## 🔍 根本原因

**异常被包装，破坏了容错机制**

### **错误链路**

```
1. _get_frame_image (line 748 in mp4_json.py)
   ↓
   抛出 CriticalDataError("Camera not found") ✅
   
2. _get_frame_images (line 569 in lerobot_format_converter.py)
   ↓
   捕获 Exception (包括 CriticalDataError)
   包装成 Exception("Failed to get frame images...") ❌
   
3. _gen_episode_frames
   ↓
   捕获 Exception
   包装成 RuntimeError ❌
   
4. _convert_episode_with_fault_tolerance
   ↓
   只捕获 CriticalDataError
   收到 RuntimeError，无法识别 ❌
   继续传播
   
5. convert()
   ↓
   任务失败 ❌❌❌
```

---

## ✅ 修复方案

### **修复点: `_get_frame_images` (line 568-571)**

让 `CriticalDataError` 和 `DataQualityError` 直接传播，不包装。

```python
# ❌ 修复前
def _get_frame_images(...):
    images = {}
    for image_config in ...:
        try:
            image = self._get_frame_image(...)
            images[lerobot_feature] = image
        except Exception as e:  # 捕获所有异常
            # 包装成普通 Exception，破坏语义
            raise Exception(f"Failed to get frame images for {lerobot_feature}") from e
    return images

# ✅ 修复后
def _get_frame_images(...):
    images = {}
    for image_config in ...:
        try:
            image = self._get_frame_image(...)
            images[lerobot_feature] = image
        except (CriticalDataError, DataQualityError):
            # 🔧 容错机制：让容错异常直接传播
            raise  # ✅ 保留异常类型
        except Exception as e:
            # 其他异常才包装
            raise Exception(f"Failed to get frame images for {lerobot_feature}") from e
    return images
```

---

## 📊 修复效果

### **修复后的异常链路**

```
1. _get_frame_image
   ↓
   抛出 CriticalDataError("Camera not found") ✅
   
2. _get_frame_images
   ↓
   捕获 CriticalDataError
   直接 raise（不包装）✅✅✅
   
3. _gen_episode_frames
   ↓
   捕获 CriticalDataError
   直接 raise（不包装）✅
   
4. _convert_episode_with_fault_tolerance
   ↓
   捕获 CriticalDataError ✅
   记录: "Episode 766 跳过（相机缺失）"
   return 0, 0 ✅
   
5. convert()
   ↓
   继续处理 Episode 767-999 ✅
   任务成功完成 ✅✅✅
```

### **转换结果对比**

| 场景 | 修复前 | 修复后 |
|------|--------|--------|
| Episode 0-765 | 未处理（任务失败） | ✅ 转换成功 |
| Episode 766 | ❌ 导致任务失败 | ⚠️  跳过（相机缺失） |
| Episode 767-999 | 未处理（任务失败） | ✅ 转换成功 |
| 任务状态 | ❌ FAILED | ✅ COMPLETED |
| 转换统计 | 0 converted | 999 converted, 1 skipped |

---

## 🎯 类似场景

这个修复也适用于其他相机相关的问题：

### **场景1: 相机视频损坏**

```
Episode 100: camera_front_head_rgb.mp4 损坏
→ 抛出 CriticalDataError
→ 跳过 Episode 100
→ 继续转换其他episode ✅
```

### **场景2: 相机帧数不足**

```
Episode 50: camera_left_wrist 只有50帧，其他相机100帧
→ 抛出 CriticalDataError (IndexError)
→ 跳过 Episode 50
→ 继续转换其他episode ✅
```

### **场景3: 多相机数量不一致**

```
Task A: 3个相机
Task B: 同一数据集内，突然变成2个相机
→ 抛出 CriticalDataError
→ 跳过 Task B 的episodes
→ 继续转换其他task ✅
```

---

## 🔗 相关修复

本修复是 **银河数据集容错修复** 的一部分：

### **Part 1: 抛出正确的异常类型** ✅
- 文件: `lerobot_format_converter_mp4_json.py`
- 位置: 5处 (包括 line 748 相机缺失检查)

### **Part 2: 保留异常类型传播** ✅
- 文件: `lerobot_format_converter.py`
- 位置: 
  - `_gen_episode_frames` (line 854-857)
  - `_get_frame_images` (line 568-571) ← **本次修复**

---

## 💡 核心原则

**异常语义必须保持一致**

```python
# ✅ 正确：保留异常类型
except (CriticalDataError, DataQualityError):
    raise  # 让上层容错机制处理

# ❌ 错误：改变异常类型
except CriticalDataError as e:
    raise Exception("...") from e  # 破坏了语义
```

**分层处理，各司其职**

```
数据层: 检测问题，抛出 CriticalDataError
  ↓
传播层: 识别容错异常，直接传播
  ↓
容错层: 捕获容错异常，应用策略（跳过）
  ↓
聚合层: 统计结果，检查失败率
```

---

**修复完成！现在相机缺失等问题会被正确处理，不会导致整个任务失败。** 🎉

