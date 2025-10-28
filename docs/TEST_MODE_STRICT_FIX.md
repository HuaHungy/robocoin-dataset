# 测试模式严格检查修复

## 📌 问题描述

**错误信息**:
```
ConfigError: 严格模式下检测到字段缺失（可能是配置错误）:
  Episode: 1 (task episode: 0)
  Task: pass the card to the sensor for recognition and then transmit it.
  Error: '❌ H5 路径不存在
     📁 H5 文件: proprio_stats.hdf5
     🔍 期望路径: state/leg/position
     📊 文件中实际存在的数据集路径:
        - action/effector/index
        - action/effector/position(dexhand)
        ...
```

**数据集**: leju (乐聚2)  
**模式**: 测试模式 (Test mode)  
**根本问题**: 配置文件期望 `state/*` 路径，但H5文件中只有 `action/*` 路径

---

## 🔍 根本原因

### 1. 数据质量问题

leju数据集的H5文件中：
- ❌ **没有** `state/leg/position` 等state数据
- ✅ **只有** `action/*` 数据

这是**数据缺失**，不是代码bug。

### 2. 测试模式的严格检查问题

**原代码逻辑** (第1067行):
```python
is_strict = global_ep_idx < self.strict_episodes
```

这意味着：
- **正式模式**前N个episode：使用严格模式 ✓（检测配置错误）
- **测试模式**前N个episode：也使用严格模式 ❌（阻止测试完成）

**问题**：
- 测试模式遇到字段缺失 → 抛出`ConfigError` → 任务失败
- 无法完成测试，也无法让用户知道有多少episode是缺失数据的

### 3. 用户期望

用户明确表示：
> "leju这个情况需要跳过，因为他属于字段缺失"

即：
- 测试模式应该**跳过**缺失字段的episode，记录warning
- 正式模式也应该**跳过**缺失字段的episode（已有容错机制）

---

## ✅ 解决方案

### 修改逻辑

**文件**: `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter.py`

**修改前**:
```python
is_strict = global_ep_idx < self.strict_episodes
```

**修改后**:
```python
# 🧪 测试模式不使用严格模式（允许跳过字段缺失的episode）
# 正式模式：前N个episode使用严格模式（检测配置错误）
is_strict = global_ep_idx < self.strict_episodes and not is_test
```

### 行为对比

| 模式 | 前N个episode | 后续episode | 遇到字段缺失 |
|------|-------------|------------|-------------|
| **测试模式** (Before) | 严格 ❌ | 容错 | 抛出ConfigError → 失败 |
| **测试模式** (After) | 容错 ✅ | 容错 | 跳过episode + warning |
| **正式模式** (Before) | 严格 | 容错 | 前N个抛出ConfigError |
| **正式模式** (After) | 严格 ✅ | 容错 | 前N个抛出ConfigError |

**关键改进**：
- ✅ 测试模式不再使用严格模式
- ✅ 允许测试完成，即使有数据缺失
- ✅ 正式模式保持不变（仍能检测配置错误）

---

## 🎯 修复效果

### Before (测试模式)
```
Episode 0: 尝试转换
Episode 1: 检测到字段缺失
→ is_strict = True (因为 global_ep_idx=1 < strict_episodes=3)
→ 抛出 ConfigError
→ 任务失败 ❌
```

### After (测试模式)
```
Episode 0: 尝试转换
Episode 1: 检测到字段缺失
→ is_strict = False (因为 is_test=True)
→ 跳过episode，记录warning
Episode 2: 继续转换
→ 测试完成 ✅
```

### 日志示例 (测试模式)

**跳过缺失字段的episode**:
```
⚠️  Skipping episode due to missing fields (non-strict mode)
   Episode: 1 (task episode: 0)
   Task: pass the card to the sensor...
   Reason: H5 path 'state/leg/position' not found
   📊 Available paths: action/effector/index, action/head/position, ...
```

**测试完成统计**:
```
✅ Test completed
   Attempted: 2 episodes
   Successful: 1 episodes
   Skipped: 1 episodes (missing fields)
```

---

## 📊 影响范围

### 受益数据集

所有可能存在字段缺失的数据集：
- ✅ **leju** (乐聚) - 当前报错数据集
- ✅ **leju2** (乐聚2) - hotel_services等
- ✅ 任何有部分episode缺失字段的数据集

### 不受影响

- 配置正确且数据完整的数据集（行为不变）
- 正式模式的严格检查机制（仍然有效）

---

## 🔧 技术细节

### 严格模式的作用

**目的**：早期检测配置错误

**逻辑**：
- 前N个episode（默认3个）使用严格模式
- 如果这些episode中有字段缺失 → 很可能是**配置错误**
- 抛出`ConfigError`让用户尽早发现问题

**为什么测试模式不需要严格模式？**
1. **测试目的不同**：测试是为了快速验证能否转换，不是检测配置
2. **数据可能不完整**：测试数据集可能本身就有缺失
3. **允许快速迭代**：跳过问题episode，看能转换多少

### 容错机制回顾

**字段缺失容错** (已有):
```python
try:
    images_buffer, states_buffer, actions_buffer = self._prepare_episode_buffers(...)
except KeyError as e:
    if is_strict:
        raise ConfigError(...)  # 严格模式：配置错误
    else:
        logger.warning(...)     # 容错模式：跳过episode
        return 0, 0
```

**修复后**：
- 测试模式：`is_strict = False` → 进入容错分支 → 跳过episode
- 正式模式（前N个）：`is_strict = True` → 抛出ConfigError
- 正式模式（后续）：`is_strict = False` → 跳过episode

---

## 🚀 部署步骤

### 1. 更新代码

**所有节点**:
```bash
cd ~/robocoin-dataset
git pull origin feat/test
```

### 2. 重启服务

**Server**:
```bash
# 停止Server进程
# 重新启动Server
```

**Client** (所有节点):
```bash
# 停止Client进程
cd ~/robocoin-dataset
git pull origin feat/test
# 重新启动Client
```

### 3. 验证修复

**leju测试模式**:
```
# 应该能完成，不再抛出ConfigError
# 日志中会有 warning 信息
⚠️  Skipping episode due to missing fields (non-strict mode)
```

**leju正式模式**:
```
# 前3个episode仍然会检测配置
# 如果都缺失字段 → 抛出ConfigError（提示配置问题）
# 如果只是部分缺失 → 跳过缺失的episode
```

---

## ⚠️ 注意事项

### 1. 配置vs数据问题的区分

**如何判断是配置错误还是数据缺失？**

| 情况 | 判断 | 行为 |
|------|------|------|
| 前3个episode都缺失同一字段 | 可能是配置错误 | 正式模式抛出ConfigError |
| 只有部分episode缺失字段 | 数据质量问题 | 正式模式跳过这些episode |
| 测试模式 | 不判断 | 始终跳过缺失episode |

### 2. leju的长期解决方案

**当前方案**：跳过缺失字段的episode

**更好的方案**：
1. 创建leju的`_lite.yaml`配置，只包含`action/*`字段
2. 不包含`state/*`字段
3. 这样就不会有字段缺失的问题

**配置对比**:
```yaml
# converter_config_leju_waibu_full.yaml (期望state+action)
observation:
  state:
    - h5_path: state/leg/position  # ❌ 数据中没有

# converter_config_leju_waibu_lite.yaml (只用action)
observation:
  state:
    - h5_path: action/joint/position  # ✅ 数据中有
```

### 3. 性能影响

- 测试模式可能需要尝试更多episode（因为跳过了一些）
- 但总体测试时间仍然很短（只处理前2个task，每个最多2个episode）

---

## 📝 相关修复

本次修复是字段缺失容错机制的**补充**：

| 修复 | 时间 | 文档 | 作用 |
|------|------|------|------|
| 字段缺失容错 | 2025-10-27 | FIELD_MISSING_FAULT_TOLERANCE.md | 非严格模式跳过缺失字段的episode |
| 测试模式严格检查 | 2025-10-28 | TEST_MODE_STRICT_FIX.md | 测试模式不使用严格检查 |

**组合效果**：
- 测试模式：容错 + 非严格 = 能完成测试 ✅
- 正式模式：容错 + 前N个严格 = 检测配置 + 跳过数据问题 ✅

---

## 🔍 排查建议

如果问题仍然存在：

### 1. 确认代码版本

```bash
cd ~/robocoin-dataset
git log --oneline -3 | grep "测试模式"
# 应该看到包含 "测试模式不使用严格模式" 的提交
```

### 2. 检查日志中的is_strict值

在日志中搜索：
```
is_strict = True   # ❌ 测试模式不应该看到这个
is_strict = False  # ✅ 测试模式应该是这个
```

### 3. 手动测试

```bash
# 运行leju测试
# 应该能完成，不抛出ConfigError
# 日志中应该有跳过episode的warning
```

---

**修复时间**: 2025-10-28  
**影响版本**: feat/test分支  
**状态**: ✅ 已修复，待部署  
**优先级**: 🔥 高（影响测试模式的正常运行）

