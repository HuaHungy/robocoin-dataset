# CRITICAL BUG - 失败任务被无限重试

## 🐛 问题描述

**现象**：任务在FAILED和PROCESSING之间来回切换

**流程**：
1. 任务失败 → 状态变为 `FAILED`
2. Server查询可用任务 → FAILED任务被选中（因为没有排除FAILED）
3. 任务被重新分配 → 状态变为 `PROCESSING`
4. Client处理失败 → 状态变为 `FAILED`
5. **无限循环** 🔄

## 🔍 根本原因

### Server.py 的任务查询逻辑

#### Test模式（第171-174行）
```python
LeFormatConvertTestDB.convert_status.in_([
    TaskStatus.PROCESSING,  # 正在处理
    TaskStatus.COMPLETED,   # 已完成也排除
])
```

❌ **没有排除 `FAILED` 状态！**

#### 正式模式（第218-221行）
```python
LeFormatConvertDB.convert_status.in_([
    TaskStatus.PROCESSING,   # 正在处理
    TaskStatus.COMPLETED,    # 已完成也排除
])
```

❌ **也没有排除 `FAILED` 状态！**

## 🔧 修复方案

### 修改 server.py

```python
# Test模式
LeFormatConvertTestDB.convert_status.in_([
    TaskStatus.PROCESSING,  # 正在处理
    TaskStatus.COMPLETED,   # 已完成
    TaskStatus.FAILED,      # 🆕 失败的任务不再重试
])

# 正式模式
LeFormatConvertDB.convert_status.in_([
    TaskStatus.PROCESSING,  # 正在处理
    TaskStatus.COMPLETED,   # 已完成
    TaskStatus.FAILED,      # 🆕 失败的任务不再重试
])
```

## 📊 影响范围

### 受影响的任务

所有失败的任务都会被无限重试：
- leju_waibu（H5路径不存在）
- yinhe（cmd_body_joint为空）
- galaxea（视频文件读取失败）
- mmk2（FileExistsError）

### 副作用

1. **浪费计算资源** - 相同的失败任务被反复执行
2. **日志混乱** - 同一个错误被记录多次
3. **状态不稳定** - 数据库状态在FAILED/PROCESSING间跳动
4. **Client负载** - Client一直在处理注定失败的任务

## 💡 关于容错机制

### 用户的问题：leju数据不匹配，容错会跳过吗？

**答案**：❌ 不会！

#### 当前行为

```python
# lerobot_format_converter_leju_waibu.py 第559行
raise KeyError(error_msg)  # H5路径不存在时抛异常
```

这个异常会：
1. 传播到 `_prepare_episode_buffers`
2. 传播到 `_convert_episode_with_fault_tolerance`
3. 传播到 `convert`
4. 传播到 `client._sync_process_task`
5. **整个任务失败** → `TASK_FAILED`

#### 为什么不会跳过？

因为异常发生在**初始化阶段**（加载H5数据），不是在**帧处理阶段**。

```python
# convert() 方法流程
1. 遍历tasks
2. 遍历episodes
3. _prepare_episode_buffers()  ← KeyError在这里！
4. _gen_episode_frames()       ← 容错机制在这里
5. _convert_episode_with_fault_tolerance()
```

容错机制只能处理**帧级别**的错误，不能处理**episode初始化**的错误。

### Test模式会跳过吗？

Test模式：
- ✅ 只处理2个tasks
- ✅ 每个task只处理1个episode
- ❌ **但遇到H5路径错误还是会失败**

### 正式模式会跳过吗？

正式模式：
- ✅ 处理所有tasks和episodes
- ❌ **遇到H5路径错误会失败**
- ❌ **然后被无限重试**

## ✅ 完整修复方案

### 1. 修复任务重试BUG（立即）

防止FAILED任务被重新分配。

### 2. 改进容错机制（可选）

让H5路径不存在的episode可以被跳过，而不是整个任务失败。

```python
def _prepare_episode_buffers(...):
    try:
        states_buffer = self._prepare_episode_states_buffer(...)
    except KeyError as e:
        # H5路径不存在
        if self.logger:
            self.logger.warning(f"⚠️  Episode {ep_idx} 数据不完整，跳过: {e}")
        # 返回空buffer，让上层决定如何处理
        return {}, {}, {}
```

但这需要修改很多地方的逻辑。

### 3. 更好的解决方案

**修复配置文件或标记数据集为不可用**，而不是依赖运行时容错。

## 🎯 立即执行的修复

修改 `server.py` 的两个位置。

