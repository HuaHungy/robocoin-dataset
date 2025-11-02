# 容错机制 vs 配置错误 - 完整指南

**日期**: 2025-10-30  
**目的**: 区分应该容错的数据质量问题和应该修正的配置错误

---

## 📊 两个案例对比

### 案例1️⃣: 银河数据集 - JSON字段为空 ✅ 应该容错

| 维度 | 详情 |
|------|------|
| **错误类型** | `IndexError` |
| **错误信息** | JSON字段 `cmd_body_joint` 为空（0条记录） |
| **失败率** | 个别episode（<20%） |
| **失败模式** | 随机、偶发 |
| **根本原因** | 数据采集过程中字段记录失败 |
| **正确处理** | ✅ 跳过问题episode，继续转换其他 |

### 案例2️⃣: MMK2数据集 - Action维度不匹配 ❌ 配置错误

| 维度 | 详情 |
|------|------|
| **错误类型** | `ValueError` (维度不匹配) |
| **错误信息** | Action维度期望37D，实际35D |
| **失败率** | **91.2%** (31/34 episodes) |
| **失败模式** | 系统性、一致 |
| **根本原因** | 配置文件与数据格式不匹配 |
| **正确处理** | ❌ 停止转换，修正配置 |

---

## 🎯 判断标准

### ✅ 应该容错（跳过episode）

符合以下**任一条件**：

1. **失败率 < 20%**
   - 大部分episode转换成功
   - 只有少数episode有问题

2. **失败原因多样**
   - 不同episode失败原因不同
   - 例如：episode 1缺JSON字段，episode 5视频损坏，episode 10图像尺寸异常

3. **数据质量问题**
   - 文件损坏（H5损坏、视频无法解码）
   - 字段缺失（个别帧/episode）
   - 帧数轻微不匹配（<5%差异）

4. **随机性问题**
   - 不可预测
   - 不影响数据集的整体可用性

**处理方式**: 
```python
raise CriticalDataError("跳过episode")
→ 记录到 error/corrupted_episodes.txt
→ 继续转换下一个episode
→ 任务状态: COMPLETED (部分episode跳过)
```

---

### ❌ 应该报错（配置错误）

符合以下**任一条件**：

1. **失败率 > 80%**
   - 绝大多数episode都失败
   - 只有极少数成功

2. **失败原因一致**
   - 所有episode相同错误
   - 例如：全都是 "action维度不匹配"

3. **配置问题**
   - 字段路径错误（H5路径不存在）
   - 维度定义错误（配置37D但数据35D）
   - 相机名称错误（配置要求cam_high但文件是camera_head）

4. **系统性问题**
   - 可预测、一致
   - 影响整个数据集

**处理方式**:
```python
raise ConfigError("配置错误")
→ 立即停止转换
→ 任务状态: FAILED
→ 用户必须修正配置后重试
```

---

## 🔧 实际案例分析

### 案例1: 银河数据集修复 ✅

**问题现象**:
```
IndexError: Frame index out of range in JSON data
   JSON path: 'cmd_body_joint'
   JSON data length: 0 (valid range: 0--1)
```

**判断依据**:
- ✅ 只有个别episode有这个问题（假设<20%）
- ✅ 其他episode转换正常
- ✅ 典型的数据采集故障

**修复方案**:
将 `IndexError` 改为 `CriticalDataError`
```python
if frame_idx >= len(frame_data):
    raise CriticalDataError(
        f"Frame index out of range (episode will be skipped)..."
    )
```

**修复后效果**:
```
✅ 任务成功完成
📊 Total: 10, Converted: 9, Skipped: 1
📝 error/corrupted_episodes.txt 记录了跳过的episode
```

---

### 案例2: MMK2数据集诊断 ❌

**问题现象**:
```
ConfigError: 前3个episode失败率过高
  尝试转换: 34 episodes
  跳过: 31 episodes
  失败率: 91.2%

错误: The feature 'action' of shape '(35,)' does not have the expected shape '(37,)'.
```

**判断依据**:
- ❌ 失败率91.2%（远超80%阈值）
- ❌ 所有episode相同错误（维度不匹配）
- ❌ 明显的配置问题

**正确处理**:
**不应该修改容错机制**，而应该：

1. **诊断数据实际结构**
   ```bash
   python scripts/diagnostics/diagnose_mmk2_dimensions.py \
       --episode-dir /path/to/episode
   ```

2. **创建匹配的配置**
   - 如果数据是35D，创建 `converter_config_mmk2_35d.yaml`
   - 或者修正数据集的 `device_model_version`

3. **更新数据库**
   ```sql
   UPDATE dmv_annotation 
   SET device_model_version = '35d_version'
   WHERE dataset_uuid = 'xxx';
   ```

4. **重新转换**
   使用正确的配置

---

## 📐 决策流程图

```
转换失败
    ↓
检查失败率
    ↓
   / \
  <20%  >80%
   ↓      ↓
检查失败原因
   ↓      ↓
多样性  一致性
   ↓      ↓
【容错处理】  【配置错误】
   ↓           ↓
使用CriticalDataError   使用ConfigError
   ↓           ↓
跳过episode  停止转换
   ↓           ↓
继续转换    修正配置
   ↓           ↓
COMPLETED   FAILED
```

---

## 🎓 设计哲学

### 容错机制的目的

**目标**: 最大化数据利用率
- 坏数据不影响好数据
- 1个episode有问题不影响99个
- 提供详细的跳过原因追溯

**不是**: 掩盖配置错误
- 如果大量失败，说明配置有问题
- 应该修正配置而不是跳过所有数据
- 浪费计算资源

### 失败率阈值的意义

**80%阈值**的设计考量：

| 失败率 | 判断 | 处理 |
|--------|------|------|
| 0-20% | 数据质量问题 | 容错，跳过 |
| 20-80% | 模糊区域 | 需人工判断 |
| 80-100% | 配置错误 | 立即停止 |

**为什么是80%？**
- 给予一定的灵活性（数据集可能部分损坏）
- 但又足够高，确保能捕获配置错误
- 可根据实际情况调整（`failure_threshold`参数）

---

## 🛠️ 工具箱

### 1. 诊断工具

```bash
# MMK2维度诊断
python scripts/diagnostics/diagnose_mmk2_dimensions.py \
    --episode-dir /path/to/episode

# 通用schema发现
python scripts/dataset_schema_discovery/discover_dataset_schema.py \
    --dataset-path /path/to/dataset \
    --output-dir outputs/schema_discovery

# 配置验证
python scripts/config_validation/validate_single_config.py \
    --config-path config.yaml \
    --dataset-path /path/to/dataset
```

### 2. 数据库查询

```sql
-- 查看失败的转换
SELECT dataset_name, convert_status, err_message 
FROM lerobot_format_convert 
WHERE convert_status = 'failed';

-- 查看跳过的episodes统计
SELECT dataset_name, total_episodes, converted_episodes, skipped_episodes
FROM lerobot_format_convert 
WHERE skipped_episodes > 0;

-- 查询设备型号版本
SELECT dataset_name, device_model, device_model_version
FROM dmv_annotation;
```

### 3. 修正脚本

```bash
# 重置失败的转换（清除FAILED状态）
python scripts/db/reset_failed_conversions.py \
    --dataset-uuid xxx-xxx-xxx

# 批量更新device_model_version
python scripts/db/update_device_model_versions.py \
    --device-model discover_robotics_aitbot_mmk2 \
    --old-version third_view_lite \
    --new-version 35d_version
```

---

## 📚 相关文档

### 已创建的文档
1. **MP4_JSON_FAULT_TOLERANCE_FIX.md** - 银河数据集修复
2. **MMK2_DIMENSION_MISMATCH_GUIDE.md** - MMK2诊断指南
3. **SERVER_CLIENT_FLOW_COMPLETE.md** - 完整流程说明

### 相关代码
1. **exceptions.py** - 异常类定义
2. **lerobot_format_converter.py** - 容错机制实现
3. **lerobot_format_converter_mp4_json.py** - MP4+JSON转换器

---

## 💡 最佳实践

### 1. 首次转换新数据集

```bash
# Step 1: Test模式验证
python scripts/format_converters/tolerobot/server.py \
    --is-test \
    --specific-device-model your_device_model

# Step 2: 检查结果
# - 如果成功 → 进入正式转换
# - 如果大量失败 → 诊断配置问题
```

### 2. 遇到大量失败

```bash
# Step 1: 不要急于修改容错机制！
# Step 2: 运行诊断工具
python scripts/diagnostics/diagnose_mmk2_dimensions.py \
    --episode-dir /path/to/first/episode

# Step 3: 根据诊断结果修正配置
# Step 4: 重新测试
```

### 3. 监控转换质量

定期检查：
```bash
# 查看跳过率
SELECT 
    dataset_name,
    skipped_episodes * 100.0 / total_episodes as skip_rate
FROM lerobot_format_convert
WHERE total_episodes > 0
ORDER BY skip_rate DESC;

# 警报阈值：
# - skip_rate > 50%: 🔴 需要检查配置
# - skip_rate 20-50%: 🟡 需要关注
# - skip_rate < 20%: 🟢 正常范围
```

---

## 🎯 总结

### ✅ 容错场景（修改为CriticalDataError）

- 个别episode失败（<20%）
- 数据损坏、字段缺失
- 随机、偶发问题
- **目标**: 最大化数据利用

### ❌ 配置错误（保持ConfigError）

- 大量episode失败（>80%）
- 系统性、一致的错误
- 维度不匹配、路径错误
- **目标**: 快速发现和修正配置

### 🔑 关键原则

> **容错机制是为了处理数据质量问题，不是为了掩盖配置错误。**

如果80%的数据都"有问题"，那真正有问题的是配置，不是数据。

---

**创建时间**: 2025-10-30  
**维护者**: AI Assistant  
**版本**: v1.0

