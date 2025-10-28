# 字段缺失容错机制

## 问题描述

用户反馈：像leju这种字段缺失的情况需要跳过，而不是让整个任务失败。

```
KeyError: '❌ H5 路径不存在
   📁 H5 文件: proprio_stats.hdf5
   🔍 期望路径: state/leg/position
   📊 文件中实际存在的数据集路径:
      - action/effector/index
      - action/head/position
      ...
```

## 已实现的解决方案

### 1. Episode级别容错（`_convert_episode_with_fault_tolerance`）

在episode buffer准备阶段（`_prepare_episode_buffers`）捕获KeyError：

```python
try:
    images_buffer, states_buffer, actions_buffer = self._prepare_episode_buffers(
        task_path, task_ep_idx, is_test=is_test
    )
except KeyError as e:
    if is_strict:
        # 严格模式：视为配置错误，停止转换
        raise ConfigError(...) from e
    else:
        # 非严格模式：跳过这个episode
        logger.warning(f"Episode {global_ep_idx} 字段缺失，跳过")
        return 0, 0
```

### 2. 严格模式vs非严格模式

**严格模式（前3个episode）：**
- 目的：快速检测配置错误
- 行为：遇到字段缺失立即失败（ConfigError）
- 适用于：Test模式、正式模式的前3个episode

**非严格模式（第4个及以后的episode）：**
- 目的：容忍个别episode的数据质量问题
- 行为：遇到字段缺失跳过该episode，继续处理
- 适用于：正式模式的第4个及以后的episode

### 3. 参数说明

```python
strict_episodes: int = 3  # 前N个episode使用严格模式
```

## 不同模式下的行为

### Test模式

- 处理范围：2个tasks × 1个episode = 最多2个episodes
- 所有episode都处于严格模式
- 字段缺失 → ConfigError → 任务标记为FAILED
- **目的：快速检测配置问题，避免浪费资源**

```
leju_waibu Test:
Episode 0 → 字段缺失 → ConfigError → FAILED ❌
```

### 正式模式

- 处理范围：所有tasks × 所有episodes
- 前3个episode：严格模式
- 第4个及以后：非严格模式

```
leju_waibu 正式:
Episode 0 → 字段缺失 → ConfigError → FAILED ❌
（不会执行，因为Test没通过）
```

## 对于leju_waibu的影响

### 数据特征
- **所有episode**的H5文件都缺少`state/*`路径
- 配置期望：`state/leg/position`, `state/head/position`, ...
- 实际存在：`action/effector/*`, `action/head/*`, ...

### 处理结果

1. **Test模式：**
   - Episode 0（严格模式）→ 字段缺失 → ConfigError
   - 任务状态：FAILED
   - Server不会再重新分配（已修复）

2. **正式模式：**
   - 不会执行（因为Test没通过）
   - 如果强制执行：
     - Episode 0-2（严格模式）→ 字段缺失 → ConfigError → FAILED

### 建议处理方式

1. **短期：** 暂时不处理leju_waibu数据集
2. **长期：** 获取正确的H5文件或更新配置文件
3. **手动重试：** 修复配置后，手动将数据库中的状态从FAILED改为PENDING

## 容错机制的层次

```
┌─────────────────────────────────────────────────────────┐
│ Level 1: Buffer准备阶段                                 │
│ - KeyError (字段缺失)                                   │
│ - 严格模式 → ConfigError（停止转换）                   │
│ - 非严格模式 → 跳过episode                              │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ Level 2: Frame生成阶段                                  │
│ - IndexError, IOError等                                 │
│ - 严格模式 → ConfigError（停止转换）                   │
│ - 非严格模式 → CriticalDataError（跳过episode）        │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ Level 3: 失败率检查                                     │
│ - 在strict_episodes结束时检查                           │
│ - 失败率 > threshold → ConfigError（停止转换）          │
└─────────────────────────────────────────────────────────┘
```

## 与Server任务重试的关系

### 修复前
```
Episode失败 → FAILED → Server重新分配 → PROCESSING → 再次失败 → 无限循环 ❌
```

### 修复后（server.py已修复）
```
Episode失败 → FAILED → Server不再分配 → 状态稳定 ✅
```

## 配置建议

### 调整严格模式范围

如果需要更宽松或更严格的容错策略：

```python
converter = LerobotFormatConverter(
    ...,
    strict_episodes=5,      # 增加严格模式的范围
    failure_threshold=0.6,  # 降低失败率阈值（更宽松）
)
```

### 何时调整

- `strict_episodes` 增大：希望更早检测配置错误
- `strict_episodes` 减小：希望更宽松的容错（不推荐 < 3）
- `failure_threshold` 降低：允许更多episode失败
- `failure_threshold` 提高：对数据质量要求更严格

## 总结

| 场景 | 行为 | 结果 |
|------|------|------|
| Test模式 + 字段缺失 | 立即失败（ConfigError） | FAILED（不再重试） |
| 正式模式前3集 + 字段缺失 | 立即失败（ConfigError） | FAILED（不再重试） |
| 正式模式第4集+ + 字段缺失 | 跳过episode | 继续处理其他episode |
| 所有episode都缺字段 | Test阶段就失败 | 不会进入正式转换 |

**核心理念：**
- 快速失败（Test模式和严格模式）
- 局部容错（非严格模式）
- 避免无限重试（Server端修复）
