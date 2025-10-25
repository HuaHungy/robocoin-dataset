# 验证器断点续传功能说明

## 📋 概述

为数据库集成配置验证器 (`db_validator_fixed.py`) 添加了**断点续传**功能，允许在验证过程被中断（如 Ctrl+C）后，从上次停止的地方继续运行，避免重新验证已完成的任务。

## ✨ 功能特性

### 1. 自动检查点保存
- ✅ 每完成一个任务后自动保存进度
- ✅ 保存已完成的任务列表和验证结果
- ✅ 检查点文件位于输出目录：`.validation_checkpoint.json`

### 2. 中断保护
- ✅ Ctrl+C 中断时自动保存当前进度
- ✅ 生成中间验证报告（前缀为 `partial_`）
- ✅ 显示已完成任务数量和检查点位置

### 3. 智能恢复
- ✅ 启动时自动检测未完成的检查点
- ✅ 交互式选择：继续/重新开始/退出
- ✅ 跳过已完成的任务，直接从下一个任务开始

### 4. 完成清理
- ✅ 验证全部完成后自动清除检查点
- ✅ 生成最终完整报告

## 🚀 使用方法

### 场景1：首次运行
```bash
python scripts/config_validation/db_validator_fixed.py \
    --db-path /path/to/database.db \
    --data-root data/ \
    --num-samples 2
```

### 场景2：验证过程中卡住或需要中断
1. **按 Ctrl+C 中断**
2. 验证器会：
   - 保存当前进度到检查点文件
   - 生成中间报告（`partial_db_validation_report_*.json`）
   - 显示已完成任务数量

```
⚠️  用户中断验证！
📊 进度: 150/447 个任务已完成
💾 检查点已保存到: outputs/db_validation_fixed/.validation_checkpoint.json
💡 重新运行脚本可从此处继续验证

✅ 中间报告已保存: outputs/db_validation_fixed/partial_db_validation_report_20251024_182030.json
```

### 场景3：从中断处恢复
重新运行**完全相同的命令**：
```bash
python scripts/config_validation/db_validator_fixed.py \
    --db-path /path/to/database.db \
    --data-root data/ \
    --num-samples 2
```

验证器会检测到检查点并提示：
```
======================================================================
⚠️  检测到未完成的验证任务!
   • 上次中断时间: 2025-10-24T18:17:55.123456
   • 已完成任务: 150/447
======================================================================

选项:
  [1] 从上次中断处继续 (推荐)
  [2] 重新开始验证
  [3] 退出

请选择 (1/2/3): 
```

- **选择 1**：从第 151 个任务继续（跳过前 150 个已完成任务）
- **选择 2**：清除检查点，从头开始
- **选择 3**：退出脚本

### 场景4：验证全部完成
- 自动清除检查点文件
- 生成最终完整报告（`db_validation_report_*.json`）

## 📂 检查点文件结构

检查点文件 (`.validation_checkpoint.json`) 包含：
```json
{
  "timestamp": "2025-10-24T18:17:55.123456",
  "completed_tasks": [
    "agilex_cobot_decoupled_magic:base_task",
    "agilex_cobot_decoupled_magic:another_task",
    ...
  ],
  "validation_results": [
    {
      "task_name": "agilex_cobot_decoupled_magic:base_task",
      "validation_status": "success",
      ...
    },
    ...
  ],
  "total_completed": 150
}
```

## 📊 报告类型

### 1. 中间报告 (Partial Report)
- **文件名**：`partial_db_validation_report_YYYYMMDD_HHMMSS.json`
- **触发**：Ctrl+C 中断时生成
- **内容**：已完成任务的验证结果
- **标记**：`"is_partial_report": true`

### 2. 最终报告 (Final Report)
- **文件名**：`db_validation_report_YYYYMMDD_HHMMSS.json`
- **触发**：全部任务完成后生成
- **内容**：所有任务的验证结果
- **标记**：`"is_partial_report": false`

## 🔧 技术实现

### 核心方法

#### `_save_checkpoint(completed_tasks, validation_results)`
每完成一个任务后调用，保存：
- 已完成任务名列表
- 已完成的验证结果
- 时间戳和统计信息

#### `_load_checkpoint()`
启动时调用，检查是否存在未完成的检查点：
- 如果存在，显示信息并等待用户选择
- 如果不存在，正常启动

#### `_clear_checkpoint()`
全部完成后调用，删除检查点文件

### 任务跳过逻辑
```python
for i, task in enumerate(available_tasks, 1):
    task_name = task['task_name']
    
    # 如果任务已完成，跳过
    if task_name in completed_task_names:
        logger.info(f"⏭️  跳过任务 {i}/{len(available_tasks)} (已完成): {task_name}")
        continue
    
    # 验证新任务
    result = self.validate_task(task)
    validation_results.append(result)
    completed_task_names.add(task_name)
    
    # 保存检查点
    self._save_checkpoint(list(completed_task_names), validation_results)
```

### 中断处理
```python
try:
    # 验证循环
    for task in available_tasks:
        ...
except KeyboardInterrupt:
    # 保存进度
    logger.warning("⚠️  用户中断验证！")
    # 生成中间报告
    report_path = self.generate_report(..., is_partial=True)
    sys.exit(130)
```

## ⚠️ 注意事项

### 1. 检查点有效性
检查点仅在**参数不变**的情况下有效：
- ✅ 相同的数据库路径
- ✅ 相同的数据根目录
- ✅ 相同的配置文件
- ❌ 如果修改了参数，建议选择"重新开始"

### 2. 数据一致性
- 检查点依赖任务名 (`device_model:device_model_version`) 进行匹配
- 如果数据库内容发生变化（如添加/删除任务），可能需要重新开始

### 3. 手动清除检查点
如果需要手动清除：
```bash
rm outputs/db_validation_fixed/.validation_checkpoint.json
```

### 4. 检查点位置
- 默认：`outputs/db_validation_fixed/.validation_checkpoint.json`
- 如果修改了 `--output-dir`，检查点也会在对应目录

## 📈 性能影响

- **保存开销**：每个任务 ~1-5ms（JSON序列化）
- **加载开销**：启动时 ~5-10ms（读取和解析JSON）
- **存储开销**：约 1-10MB（取决于已完成任务数量）

**结论**：开销极小，对整体验证性能影响可忽略不计。

## 🎯 典型使用场景

### 场景A：大型数据集验证（447个任务）
1. 启动验证
2. 运行到第 150 个任务时卡住（如 mult_sensor 任务）
3. Ctrl+C 中断
4. 调查卡住的任务（可能需要手动处理）
5. 重新运行，选择"从上次中断处继续"
6. 跳过前 150 个，直接从 151 开始
7. 完成剩余 297 个任务

**节省时间**：避免重新验证 150 个任务（可能节省数小时）

### 场景B：网络或NAS中断
1. 验证过程中NAS网络临时中断
2. 验证器因网络错误中断
3. 恢复网络连接
4. 重新运行，从检查点继续
5. 只重新验证失败的任务

### 场景C：系统维护
1. 验证过程中需要重启机器
2. Ctrl+C 保存进度
3. 重启后重新运行
4. 从检查点恢复，继续验证

## 🔍 调试和日志

### 检查点保存日志
```
💾 检查点已保存: 150 个任务已完成
```

### 检查点加载日志
```
📂 发现未完成的验证检查点:
   • 时间: 2025-10-24T18:17:55.123456
   • 已完成任务: 150
```

### 任务跳过日志
```
======================================================================
⏭️  跳过任务 1/447 (已完成): agilex_cobot_decoupled_magic:base_task
```

### 检查点清除日志
```
🗑️  检查点已清除
```

## 🆕 版本历史

- **2025-10-24**：初始实现
  - 添加自动检查点保存
  - 添加交互式恢复选择
  - 添加中间报告生成
  - 添加 Ctrl+C 优雅中断

## 📝 总结

断点续传功能解决了长时间验证任务的关键痛点：
- ✅ **防止意外中断导致的重复工作**
- ✅ **允许灵活处理卡住或异常的任务**
- ✅ **提供清晰的进度跟踪和恢复机制**
- ✅ **零配置自动启用（无需额外参数）**

现在你可以放心地 Ctrl+C 中断验证器，然后从上次停止的地方继续！🎉

