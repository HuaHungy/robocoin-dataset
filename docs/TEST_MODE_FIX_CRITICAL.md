# 🔥 CRITICAL: 修复Test模式处理所有Episodes的严重Bug

**日期**: 2025-10-27  
**严重程度**: 🔴 **CRITICAL**  
**问题**: Test模式仍然处理所有tasks，导致内存耗尽和大量semaphore泄漏  
**影响**: 所有converters的test模式

---

## 🐛 问题描述

### 症状

```
Converting Dataset:  15%|██▏           | 1151/7506 [08:16<49:02,  2.16episode/s]
已杀死
UserWarning: There appear to be 27 leaked semaphore objects to clean up at shutdown
```

**观察**：
- leju_robot在test模式下处理了**1151个episodes**（应该只有2个！）
- 进程被系统杀死（可能是OOM - 内存耗尽）
- **27个semaphore泄漏**

### 根本原因

Test模式的实现逻辑错误：

```python
for task_path, task in self.path_task_dict.items():  # ← 遍历所有tasks！
    episodes_num = self._get_task_episodes_num(task_path)
    if is_test:
        episodes_num = 1  # ← 只限制每个task的episodes数量
```

**问题**：
1. 循环遍历了**所有的tasks**（7506个）
2. 只限制了**每个task**的episodes数量为1
3. 对于leju这种每个task只有1个episode的数据集，相当于**完全没有限制**！

**结果**：
- 处理了7506个episodes而不是2个
- 每个episode都加载视频和H5文件
- 内存累积，最终OOM
- 每个episode可能泄漏semaphore

---

## ✅ 修复方案

### 限制处理的Tasks数量

**修改文件**: `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter.py`

**修改位置**: `convert()` 方法

**修改后**：

```python
global_ep_idx = 0
original_ep_idx = 0
task_stats = {}

# 🆕 Test模式：限制处理的tasks数量
tasks_to_process = list(self.path_task_dict.items())
if is_test:
    max_test_tasks = 2  # Test模式只处理前2个tasks
    tasks_to_process = tasks_to_process[:max_test_tasks]
    if self.logger:
        self.logger.info(
            f"🧪 Test mode: processing only {len(tasks_to_process)} tasks "
            f"out of {len(self.path_task_dict)} total tasks"
        )

for task_path, task in tasks_to_process:  # ← 使用受限的列表
    episodes_num = self._get_task_episodes_num(task_path)
    if is_test:
        episodes_num = 1  # Test模式每个task只处理1个episode
```

---

## 📊 修复效果对比

### 修复前

```
Test模式处理逻辑:
┌────────────────────────────────────────────────┐
│ 遍历 7506 个 tasks                             │
│   每个 task 处理 1 个 episode                  │
│                                                │
│ 总共处理: 7506 episodes ❌                     │
│ 内存使用: 持续增长 → OOM                       │
│ Semaphore泄漏: 27+ 个                          │
│ 结果: 进程被杀死                               │
└────────────────────────────────────────────────┘
```

### 修复后

```
Test模式处理逻辑:
┌────────────────────────────────────────────────┐
│ 只处理前 2 个 tasks                            │
│   每个 task 处理 1 个 episode                  │
│                                                │
│ 总共处理: 2 episodes ✅                        │
│ 内存使用: 可控                                 │
│ Semaphore泄漏: 最多2个（如果有leak）           │
│ 结果: 正常完成                                 │
└────────────────────────────────────────────────┘
```

---

## 🔢 对不同数据集的影响

### leju_robot (每个task 1个episode)

| 模式 | 修复前 | 修复后 |
|------|--------|--------|
| Tasks处理 | 7506 | 2 |
| Episodes处理 | 7506 | 2 |
| 预期时间 | 数小时 | 数秒 |
| 内存占用 | OOM | 正常 |

### 其他数据集 (多episodes per task)

| 模式 | 修复前 | 修复后 |
|------|--------|--------|
| Tasks处理 | 全部 | 2 |
| Episodes处理 | 所有tasks × 1 | 2 |
| 预期行为 | 不符合预期 | 符合预期 |

---

## ⚠️ 其他相关问题

### Semaphore泄漏（27个）

虽然test模式修复后泄漏会减少，但仍然说明有资源清理问题。

**可能的泄漏来源**：
1. 每个episode处理时创建的dataset对象
2. 视频解码器
3. H5文件句柄
4. 其他多进程资源

**已有的清理机制**：
- ✅ `lerobot_format_converter.py` 的 `__del__` 方法
- ✅ `client.py` 的 `finally` 块
- ✅ `convert()` 方法中的 `self.lerobot_dataset` 赋值

**需要进一步调查**：
- 为什么27个泄漏（1151个episodes，但只有27个泄漏？）
- 是否有其他资源需要清理？

---

## 🚀 部署

### 同步代码到所有Client机器

```bash
# 在每台Client机器上
cd ~/robocoin-dataset
git pull origin feat/test

# 重启clients
Ctrl+C
python scripts/format_converters/tolerobot/multi_client.py \
    --host 172.16.13.140 --port 8769 --num-clients 4
```

### 验证

重新运行test模式后，应该看到：

```
🧪 Test mode: processing only 2 tasks out of 7506 total tasks
Converting Dataset: 100%|██████████| 2/2 [00:05<00:00,  2.50s/episode]
✅ Conversion completed successfully: 2/2 episodes
```

而不是：

```
Converting Dataset:  15%|██▏  | 1151/7506 [08:16<49:02,  2.16episode/s]
已杀死
```

---

## 📋 总结

### 问题根源

Test模式的逻辑bug，导致处理所有tasks而不是限制数量。

### 修复内容

1. 添加 `max_test_tasks = 2` 限制
2. 只遍历前2个tasks
3. 记录test模式的处理数量

### 影响

- 🔴 **Critical**: 所有converter的test模式
- 🔴 **Critical**: 内存管理和OOM问题
- 🟡 **Important**: Semaphore泄漏（部分缓解）

### 下一步

1. ✅ 同步代码到所有Client
2. ⏳ 重新测试以验证修复
3. ⏳ 进一步调查semaphore泄漏的根本原因

---

**修复状态**: ✅ 已完成  
**验证状态**: ⏳ 待部署后验证

