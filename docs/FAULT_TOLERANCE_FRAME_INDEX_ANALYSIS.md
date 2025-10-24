# 容错机制与LeRobot帧索引兼容性分析

## ⚠️ 重要设计决策（2025-10-21更新）

**结论：我们不支持跳过单帧，只支持跳过整个episode。**

### 原因

如果跳过单帧会导致：
1. **时序对齐破坏**：observation[i] 和 action[i+offset] 的对应关系错位
2. **数据不可用**：机器学习模型依赖连续的时序数据，帧索引不连续会导致训练问题
3. **难以追溯**：跳帧后的轨迹无法映射回原始演示数据

### 实现策略

- **严格模式**（前N个episode）：任何DataQualityError都升级为ConfigError，立即停止转换
- **非严格模式**：任何DataQualityError都升级为CriticalDataError，跳过整个episode
- **结果**：要么episode的所有帧都转换成功，要么整个episode被跳过

## 历史问题描述（已解决）

~~当容错机制跳过某些坏帧时，是否会导致LeRobot数据集的帧索引混乱？~~

**答案：不会，因为我们根本不跳过单帧。**

## 当前实现分析

### 转换流程

```python
# 1. 生成所有帧索引 (0 到 total_frames-1)
for frame_data in self._gen_episode_frames(...):
    frame_idx = frame_data[FRAME_IDX_KEY]  # 原始帧索引: 0, 1, 2, 3, ...
    
    try:
        # 2. 从buffer中读取该帧的数据
        lerobot_datas = self._get_lerobot_datas(
            frame_idx=frame_idx,  # 使用原始索引访问buffer
            ...
        )
        
        # 3. 写入LeRobot数据集
        if not is_test:
            dataset.add_frame(frame=lerobot_datas, task=task)
        
    except DataQualityError:
        # 跳过此帧，不写入
        skipped_frames += 1
```

### 关键问题

**场景**：假设原始数据有10帧（0-9），第2帧和第5帧损坏

| 原始frame_idx | Buffer中的数据 | LeRobot写入 | LeRobot中的索引 |
|--------------|--------------|------------|----------------|
| 0 | ✓ 正常 | ✓ 写入 | 0 |
| 1 | ✓ 正常 | ✓ 写入 | 1 |
| 2 | ✗ 损坏 | ✗ 跳过 | - |
| 3 | ✓ 正常 | ✓ 写入 | 2 |
| 4 | ✓ 正常 | ✓ 写入 | 3 |
| 5 | ✗ 损坏 | ✗ 跳过 | - |
| 6 | ✓ 正常 | ✓ 写入 | 4 |
| 7 | ✓ 正常 | ✓ 写入 | 5 |
| 8 | ✓ 正常 | ✓ 写入 | 6 |
| 9 | ✓ 正常 | ✓ 写入 | 7 |

**结果**：
- 原始数据：10帧
- 跳过：2帧
- LeRobot数据集：8帧（索引0-7）

## 潜在问题分析

### ✅ 没有问题的情况

LeRobot的 `dataset.add_frame()` **不需要**我们传递帧索引。它按照调用顺序自动管理索引：

- 第1次调用 `add_frame()` → LeRobot索引0
- 第2次调用 `add_frame()` → LeRobot索引1
- ...

所以跳过帧不会影响LeRobot的索引连续性。

### ⚠️ 可能有问题的情况

#### 问题1：Action的Timeline Offset

```python
# 在 _gen_episode_frame 中
def _gen_episode_frame(self, task_path, ep_idx, frame_idx, ...):
    # ...
    # 获取action时可能使用 frame_idx + timeline_offset
    action_frame_idx = frame_idx + timeline_offset
    action_data = actions_buffer[action_frame_idx]  # 访问未来的action
```

**风险**：
- 如果跳过了某些帧，但action的timeline_offset依赖于原始的连续索引
- 可能导致访问错误的action数据

**当前缓解措施**：
```python
# 在 _gen_episode_frames 中
max_frame_idx = total_frames - timeline_offset
```
这确保我们不会访问超出范围的action，但**没有考虑跳过的帧**。

#### 问题2：Buffer索引假设

某些buffer（如视频、JSON数组）是基于原始帧数构建的：

```python
# 视频buffer
video_buffer = {
    'camera': [frame0, frame1, frame2, ...]  # 列表形式
}

# 访问时
frame_image = video_buffer['camera'][frame_idx]
```

**风险**：
- 如果frame 2损坏，我们跳过它
- 但后续访问 frame_idx=3 时，仍然会从 buffer[3] 读取
- 这是正确的！因为buffer是原始数据的完整副本

**结论**：这种情况下没有问题，因为我们：
1. 从原始buffer读取数据（使用原始索引）
2. 如果读取失败，抛出DataQualityError
3. 捕获异常，跳过该帧，不写入LeRobot
4. 继续处理下一个原始索引

## 当前实现是否安全？

### ✅ 安全的部分

1. **帧数据读取**：使用原始frame_idx从buffer读取，正确
2. **LeRobot写入**：只在数据有效时才调用add_frame()，索引由LeRobot自动管理，正确
3. **Episode级容错**：如果跳过帧数过多，整个episode被跳过，避免产生质量差的数据

### ⚠️ 需要验证的部分

1. **Timeline Offset处理**

   当前代码（`_gen_episode_frame` -> `_get_frame_actions`）中：
   
   ```python
   def _get_frame_actions(self, task_path, ep_idx, frame_idx, actions_buffer):
       # 这里可能会访问 frame_idx + timeline_offset
       # 需要确认是否处理了跳过帧的情况
   ```

2. **跨帧依赖**

   某些特征可能依赖于前一帧或后一帧的数据。如果跳过了帧，这些依赖关系可能会被打断。

## 实际测试验证

### 测试场景1：正常数据（无跳过）

```bash
python scripts/test_fault_tolerance.py \
    --dataset-path /path/to/good/dataset \
    --device-model zhipingfang \
    --test-mode
```

**预期**：100%成功，0跳过

**结果**：✅ 已通过（智平方测试）

### 测试场景2：模拟坏帧

需要创建一个测试数据集，其中某些帧的数据损坏或缺失。

```python
# 修改转换器，强制某些帧抛出DataQualityError
def _get_frame_image(self, ...):
    if frame_idx in [2, 5, 8]:  # 模拟损坏
        raise DataQualityError(f"Simulated corruption at frame {frame_idx}")
    return super()._get_frame_image(...)
```

**预期**：
- 跳过3帧
- 成功转换其他7帧
- LeRobot数据集有7帧，索引0-6
- 数据内容正确（无错位）

### 测试场景3：Timeline Offset + 跳过帧

使用有timeline_offset的配置（如action在observation之后1帧）：

```yaml
features:
  action:
    timeline_offset: 1  # action比observation晚1帧
```

**潜在风险**：
- 如果跳过了某帧，timeline_offset的计算可能错误

## 建议的改进

### 短期（立即实施）

1. **添加更详细的日志**

   ```python
   if not is_test:
       self.logger.debug(
           f"Writing frame to LeRobot: "
           f"original_idx={frame_idx}, "
           f"lerobot_idx={dataset.current_frame_count()}, "
           f"skipped_so_far={skipped_frames}"
       )
       dataset.add_frame(frame=lerobot_datas, task=task)
   ```

2. **验证action索引**

   在 `_get_frame_actions` 中添加边界检查：
   
   ```python
   def _get_frame_actions(self, ...):
       timeline_offset = self.converter_config[...].get(TIMELINE_OFFSET_KEY, 0)
       action_frame_idx = frame_idx + timeline_offset
       
       # 检查索引是否有效
       if action_frame_idx >= len(actions_buffer):
           raise DataQualityError(
               f"Action frame index {action_frame_idx} out of range "
               f"(buffer size: {len(actions_buffer)})"
           )
   ```

### 中期（测试后实施）

3. **创建帧映射表**

   如果跳过了帧，记录原始索引到LeRobot索引的映射：
   
   ```python
   frame_mapping = {
       'original_idx': [0, 1, 3, 4, 6, 7, 8, 9],  # 跳过了2和5
       'lerobot_idx': [0, 1, 2, 3, 4, 5, 6, 7],
   }
   ```
   
   保存到metadata中，用于debug和追溯。

### 长期（重构）

4. **重新设计buffer机制**

   考虑将buffer设计为"已清洗"的数据，而不是原始数据的完整副本：
   
   ```python
   # 当前：buffer = 所有原始帧（包括坏帧）
   # 改进：buffer = 只包含有效帧（预先过滤）
   
   def _prepare_episode_buffers_with_validation(self, ...):
       raw_buffer = self._prepare_episode_buffers(...)
       
       # 预先验证并过滤
       valid_frames = []
       for idx in range(len(raw_buffer)):
           try:
               self._validate_frame(raw_buffer, idx)
               valid_frames.append(idx)
           except DataQualityError:
               pass
       
       return ValidatedBuffer(raw_buffer, valid_frames)
   ```

## 结论

**当前实现在大多数情况下是安全的**，因为：

1. ✅ LeRobot的add_frame()按调用顺序管理索引，跳过帧不影响连续性
2. ✅ Buffer访问使用原始索引，数据读取正确
3. ✅ Episode级容错确保不会产生质量太差的数据

**需要注意的边界情况**：

1. ⚠️ Timeline offset与跳过帧的交互（需要测试验证）
2. ⚠️ 跨帧依赖的特征处理（如差分、滤波等）

**建议**：

1. 立即添加更详细的日志，用于追踪帧索引
2. 创建测试用例验证跳过帧+timeline offset的场景
3. 在文档中明确说明容错机制的行为和限制

---

**维护者**: Refactoring Team  
**最后更新**: 2025-10-21  
**状态**: 待验证

