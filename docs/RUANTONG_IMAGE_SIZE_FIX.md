# ruantong图像尺寸不一致问题修复

## 📋 问题描述

### 错误现象
```
ValueError: The feature 'observation.images.cam_left_wrist_rgb' of shape '(720, 1280, 3)' does not have the expected shape '(480, 848, 3)'
ValueError: The feature 'observation.images.cam_back_right_fisheye_rgb' of shape '(480, 848, 3)' does not have the expected shape '(1536, 1920, 3)'
ValueError: The feature 'observation.images.cam_back_left_fisheye_rgb' of shape '(480, 848, 3)' does not have the expected shape '(1536, 1920, 3)'
```

### 发生场景
- **数据集**: 软通天擎 (ruantong) gt01
- **Episode**: 转换到第103帧时失败
- **原因**: 数据采集过程中设备配置发生变化（更换相机/调整分辨率）

### 根本原因
1. 初始化时用第一个episode确定图像shape
2. 转换时某些episode的图像尺寸与初始化时不同
3. LeRobot库要求所有episode的图像尺寸必须一致

---

## ✅ 解决方案

### 策略：跳过尺寸不一致的episode

**理由**：
- ruantong数据集有完整的mapping文件可以追溯
- 即使全部跳过也能通过mapping找到原始数据
- 避免因部分数据问题导致整个转换失败

### 代码修改

在 `_convert_episode_with_fault_tolerance` 中添加 `ValueError` 专门处理：

```python
except ValueError as e:
    # ValueError: 图像尺寸不匹配等格式验证错误
    # 跳过整个episode（数据采集过程中设备配置可能发生变化）
    if self.logger:
        self.logger.warning(
            f"⚠️  Episode {original_ep_idx} (frame {frame_idx}) ValueError (likely image size mismatch):\n"
            f"   {e}\n"
            f"   Skipping entire episode. Can be traced via episode_source_mapping.json"
        )
    
    # 记录到统计信息
    self._conversion_stats['skipped_episodes'] += 1
    skip_reason = f"ValueError (image size mismatch): {str(e)}"
    
    # 记录到mapping
    self.episode_source_mapping[original_ep_idx] = {
        "task": task,
        "original_ep_idx": original_ep_idx,
        "status": "skipped",
        "skip_reason": skip_reason,
        "source_files": source_files,
    }
    
    original_ep_idx += 1
    continue  # 跳过此episode，继续下一个
```

### 关键特性

1. **自动跳过**: ValueError不再导致转换失败
2. **完整记录**: 跳过的episode记录在`episode_source_mapping.json`
3. **数据溯源**: 通过mapping可以追溯到原始数据位置
4. **友好日志**: 清晰说明跳过原因

---

## 📊 修复效果

### Before
```
❌ ValueError → 转换失败 → 整个数据集无法转换
⚠️  无法定位问题episode
⚠️  需要手动修复数据或配置
```

### After
```
✅ ValueError → 自动跳过episode → 转换继续
✅ mapping记录跳过的episode详细信息
✅ 转换完成，可用的episode成功转换
✅ 日志清晰显示：⏭️ Skipped episode X (image size mismatch)
```

---

## 🗂️ Mapping文件支持

### 同时生成两个mapping文件

**修改位置**: `client.py` line 151-153

```python
if not is_test:
    converter.save_episode_source_mapping()      # 已有
    converter.save_original_data_paths()  # 🆕 新增
```

### 文件1: episode_source_mapping.json

记录转换状态和统计信息：

```json
{
  "dataset_info": {
    "total_original_episodes": 100,
    "total_converted_episodes": 95,
    "total_skipped_episodes": 5,
    "skipped_episode_indices": [3, 7, 15, 22, 45]
  },
  "converted_episodes": [...],
  "skipped_episodes": [
    {
      "original_episode_index": 3,
      "task": "pick_object",
      "skip_reason": "ValueError (image size mismatch): ...",
      "source_files": {...}
    }
  ]
}
```

### 文件2: original_data_paths.json

记录原始数据绝对路径：

```json
{
  "dataset_info": {...},
  "episode_paths": [
    {
      "original_episode_index": 0,
      "task": "pick_object",
      "status": "converted",
      "global_episode_index": 0,
      "absolute_paths": {
        "primary": "/mnt/nas/.../episode_0001",
        "h5_file": "/mnt/nas/.../aligned_joints.h5",
        "videos": [...]
      }
    },
    {
      "original_episode_index": 3,
      "task": "pick_object",
      "status": "skipped",
      "absolute_paths": {...}
    }
  ]
}
```

### 追溯流程

1. 查看 `episode_source_mapping.json` → 找到跳过的episode
2. 查看 `skip_reason` → 了解跳过原因
3. 查看 `original_data_paths.json` → 获取原始数据绝对路径
4. 根据路径检查原始数据 → 确认数据问题或手动修复

---

## 🎯 影响范围

### 受益数据集
- ✅ ruantong (软通天擎) - 当前报错数据集
- ✅ 所有可能存在设备配置变化的数据集
- ✅ 所有多相机数据集

### 通用性
- ✅ 所有11个转换器都支持mapping文件
- ✅ 所有数据集都会在正式转换后生成两个mapping文件
- ✅ ValueError处理适用于所有转换器

---

## 🔍 验证日志

**正常日志应显示**：

```
⚠️  Episode 0 (frame 103) ValueError (likely image size mismatch):
   The feature 'observation.images.cam_left_wrist_rgb' of shape '(720, 1280, 3)' does not have the expected shape '(480, 848, 3)'
   Skipping entire episode. Can be traced via episode_source_mapping.json

⏭️  Skipped episode 0 (task: pick_object, task_ep: 0): ValueError (image size mismatch): ...

✅ Conversion completed successfully: 95/100 episodes
   Skipped (data quality issues): 5

✅ Episode 源文件映射已保存: .../episode_source_mapping.json
   - 总 episodes: 100
   - 成功转换: 95
   - 跳过: 5

✅ 原始数据绝对路径映射已保存: .../original_data_paths.json
   - 总 episodes: 100
```

---

## 📁 修改文件

- ✏️ `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter.py`
  - 添加ValueError处理 (line 975-1017)
  
- ✏️ `src/robocoin_dataset/format_converter/tolerobot/client.py`
  - 调用save_original_data_paths() (line 153)

- 📄 `docs/RUANTONG_IMAGE_SIZE_FIX.md` (本文档)

---

## 📅 修复日期

2025-10-28

