# 帧数容忍度修改说明

**日期**: 2025-10-24  
**修改内容**: 将H5+MP4转换器的帧数容忍度从±1帧增加到±30帧

---

## 修改原因

用户反馈在验证过程中发现视频与H5数据有3帧差异的episode被标记为失败，但这种小差异应该通过自动裁剪处理，而不是跳过整个episode。

### 典型案例
```
Episode 7956:
- 视频帧数: 394
- H5数据帧数: 397
- 差异: 3帧
- 原行为: ❌ 验证失败
- 新行为: ✅ 自动裁剪到394帧，继续转换
```

---

## 修改详情

### 文件
`src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_h5_mp4.py`

### 修改1: 预验证容忍度（第210行）
```python
# 修改前
tolerance=1  # 允许±1帧误差

# 修改后
tolerance=30  # 允许±30帧误差，自动裁剪到最小帧数
```

### 修改2: 转换时差异处理（第303-327行）
增加了分级处理逻辑：

- **差异 > 30帧**: 抛出`CriticalDataError`，跳过episode
- **差异 2-30帧**: 自动裁剪到最小帧数，记录INFO日志
- **差异 ≤1帧**: 静默处理，无额外日志

---

## 处理逻辑

### 自动裁剪机制
```python
min_frames = min(count for _, count in frame_counts)
```

从所有数据源（H5数据、各相机视频）中选择最小帧数，所有数据都裁剪到这个长度。

### 示例
```
原始数据:
- H5 action: 397帧
- H5 qpos: 397帧  
- cam_left_wrist: 394帧

裁剪后:
- H5 action: 394帧 (裁掉最后3帧)
- H5 qpos: 394帧 (裁掉最后3帧)
- cam_left_wrist: 394帧 (保持不变)

结果: ✅ 所有数据对齐，394个完整的(observation, action)对
```

---

## 日志输出示例

### 2-30帧差异（INFO级别）
```
📊 Frame count difference in episode 7956 (within tolerance):
   - H5 data: 397 frames
   - cam_left_wrist: 394 frames
   ✅ Auto-trimming to minimum: 394 frames (difference: 3 frames)
```

### >30帧差异（WARNING级别）
```
❌ Frame count mismatch exceeds tolerance in episode XXX:
   - H5 data: 400 frames
   - cam_left_wrist: 350 frames
   ⚠️  Difference: 50 frames (tolerance: ±30 frames)
   ⚠️  Skipping this episode to maintain data integrity.
```

---

## 预期效果

### 成功率提升
- 原本因2-30帧差异失败的episodes现在会自动处理
- 只有严重不匹配（>30帧）的才会被跳过
- 预期验证成功率会显著提高

### Episode 7956等类似问题
- **修改前**: ❌ 验证失败
- **修改后**: ✅ 验证通过，自动裁剪

---

## 容忍度合理性

### 30帧的含义
- 30Hz采集频率下 = 1秒的数据
- 对于典型episode（10-60秒）影响很小（<10%）
- 足够容忍录制结束时的同步误差

### 为什么不是更大？
- 超过30帧说明是系统性问题，不是录制误差
- 过大的容忍度可能掩盖数据采集问题
- 30帧是误差容忍和质量保证的平衡点

---

## 数据完整性保证

### ✅ 保证
- 所有数据源帧数一致
- observation-action时间对齐
- 不会出现索引越界

### ⚠️ 注意
- 裁剪会丢失多余帧（通常是末尾）
- 对机器人学习影响很小
- 丢失的帧不会破坏episode的连续性

---

## 相关文档

- [容错机制增强总结](./FAULT_TOLERANCE_ENHANCEMENT.md)
- [转换器配置指南](../src/robocoin_dataset/format_converter/tolerobot/README.md)

