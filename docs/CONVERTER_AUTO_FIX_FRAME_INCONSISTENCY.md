# 智平方帧数不一致问题 - 自动修复方案（Converter 层）

## 🎯 修复内容

修改了 H5 converter 使其在检测到帧数不一致时**自动移动文件到 error/ 目录并跳过**，而不是让整个转换任务失败。

## ✅ 修改的文件

### 1. `lerobot_format_converter_h5.py`
**位置**: 第815-870行

**修改内容**:
- 检测到帧数不一致时，不再抛出 `ValueError`
- 自动创建 `error/` 目录
- 使用 `shutil.move()` 移动问题文件
- 返回 `-1` 作为"跳过此episode"的标记
- 记录详细的 warning 日志

**行为**:
```python
# 检测到帧数不一致
if frame_count_issues:
    # 尝试自动移动
    error_dir = h5_file_path.parent / "error"
    error_dir.mkdir(exist_ok=True)
    shutil.move(str(h5_file_path), str(error_dir / h5_file_path.name))
    
    # 记录日志
    logger.warning("📦 自动移动问题文件到 error/: ...")
    
    # 返回 -1 表示跳过
    return -1
```

### 2. `lerobot_format_converter.py`
**位置**: 第626-643行 + 第690-740行

**修改内容**:

#### A. `_gen_episode_frames()` 方法
检查 `total_frames == -1`，如果是则返回空迭代器：
```python
total_frames = self._get_episode_frames_num(...)
if total_frames == -1:
    logger.info("⏭️  Skipping episode (auto-moved to error/)")
    return  # 返回空迭代器
```

#### B. `convert()` 方法
跟踪 frame_count，如果为 0 则跳过该 episode：
```python
frame_count = 0
for frame_data in self._gen_episode_frames(...):
    # 处理帧...
    frame_count += 1

if frame_count == 0:
    logger.info("⏭️  Episode was skipped")
    continue  # 不 yield，不增加 ep_idx
```

## 📊 修复效果

### 修复前：
```
❌ ValueError: H5数据集帧数不一致
❌ RuntimeError: Failed to process episode 495
❌ RuntimeError: convert dataset /mnt/.../公共服务 failed
→ 整个任务失败，停止转换
```

### 修复后：
```
⚠️  检测到帧数不一致: converted_0501.h5
📦 自动移动到 error/: converted_0501.h5 -> error/
⏭️  跳过 episode 495
✅ 继续处理下一个 episode
→ 任务继续执行，只跳过问题文件
```

## 🔍 工作流程

1. **检测阶段** (`_get_episode_frames_num`):
   ```
   检查所有 sub_state 的帧数
   → 发现不一致
   → 创建 error/ 目录
   → 移动文件
   → 返回 -1
   ```

2. **生成阶段** (`_gen_episode_frames`):
   ```
   接收到 total_frames = -1
   → 记录日志
   → 返回空迭代器
   ```

3. **转换阶段** (`convert`):
   ```
   for frame_data in _gen_episode_frames():  # 空迭代器
       # 不执行
   
   frame_count == 0  # True
   → 记录日志
   → continue (跳过 save_episode 和 yield)
   ```

## 🛡️ 错误处理

### 移动成功：
- ✅ 文件移动到 `error/`
- ✅ 记录 warning 日志
- ✅ 返回 -1
- ✅ Episode 被跳过
- ✅ 继续处理其他 episodes

### 移动失败：
- ❌ 捕获移动异常
- ❌ 记录 error 日志（包含手动移动命令）
- ❌ 抛出 `ValueError`（保持原有行为）
- ❌ 任务失败（需要手动干预）

### 文件已存在于 error/：
- ⚠️  检测到目标已存在
- ⚠️  记录 warning 日志
- ⚠️  返回 -1（跳过）
- ✅ 继续处理

## 📝 日志示例

### 成功移动：
```
WARNING - 📦 自动移动问题文件到 error/:
   converted_0501.h5 -> /mnt/.../task_27.../error/
   原因: 帧数不一致
   ❌ H5数据集帧数不一致（数据质量问题）
      🗂️  文件: converted_0501.h5
      📊 参考帧数: observations/arm/right/joints: 164 帧
      ❌ 以下数据集帧数不一致:
          sub_state[2] observations/arm/right/wrench: 165 帧
          sub_state[3] observations/effector/right/position: 165 帧

INFO - ⏭️  Skipping episode 495 at task_27_补采-公共服务1-药盒-医药框-Bot2-0029 
       (auto-moved to error/ due to data quality issues)

INFO - ⏭️  Episode 495 at task_27_补采-公共服务1-药盒-医药框-Bot2-0029 was skipped 
       (likely due to data quality issues)
```

### 移动失败：
```
ERROR - ❌ 自动移动文件失败: [Errno 13] Permission denied
        ❌ H5数据集帧数不一致（数据质量问题）
        ...
        💡 请手动移动文件:
           mkdir -p '/mnt/.../error'
           mv '/mnt/.../converted_0501.h5' '/mnt/.../error/'

ERROR - Failed to process episode: ...
RuntimeError: Failed to process episode 495
```

## 🎁 优势

### 对比预检查脚本 (`zhipingfang_preconversion_validator_v2.py`):
1. ✅ **实时处理**: 转换时发现问题立即处理，不需要预检查
2. ✅ **自动恢复**: 遇到问题自动跳过，继续转换其他数据
3. ✅ **减少停机**: 不需要人工干预，任务可以持续运行
4. ✅ **简化流程**: 不需要先运行预检查再运行转换

### 对比手动移动:
1. ✅ **零人工**: 完全自动化，无需手动执行 mv 命令
2. ✅ **零停机**: 不需要重启或重新提交任务
3. ✅ **详细日志**: 自动记录所有移动操作
4. ✅ **批量处理**: 可以一次性处理多个问题文件

## ⚠️ 注意事项

1. **文件权限**: 确保 converter 有权限创建 error/ 目录和移动文件
2. **磁盘空间**: 移动操作在同一文件系统内，不占用额外空间
3. **日志监控**: 注意监控 warning 日志，了解有多少文件被自动移动
4. **数据质量**: 被移动的文件需要后续分析，确定是否需要重新采集

## 🔧 配合使用

### 1. 预防性检查（可选）:
在转换前使用预检查工具：
```bash
python scripts/dataset_statistics/zhipingfang_preconversion_validator_v2.py \
  --dataset-path "/mnt/.../公共服务" \
  --move-errors
```

### 2. 自动转换（推荐）:
直接运行转换，让 converter 自动处理问题：
```bash
python scripts/format_converters/tolerobot/client.py \
  --dataset-path "/mnt/.../公共服务"
```

### 3. 事后检查:
查看移动了多少文件：
```bash
find "/mnt/.../公共服务" -name "error" -type d -exec sh -c '
  error_dir="$1"
  count=$(ls -1 "$error_dir" 2>/dev/null | wc -l)
  if [ "$count" -gt 0 ]; then
    echo "$error_dir: $count 个文件"
  fi
' sh {} \;
```

## 🎉 总结

这个修复让智平方数据集转换任务**具有容错能力**：
- ✅ 自动检测数据质量问题
- ✅ 自动隔离问题文件
- ✅ 自动继续处理正常数据
- ✅ 详细记录所有操作

**结果**: 转换任务可以持续运行，不会因为个别问题文件而失败！
