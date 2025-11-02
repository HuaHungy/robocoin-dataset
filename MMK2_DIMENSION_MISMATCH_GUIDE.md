# MMK2 数据集维度不匹配问题诊断指南

**日期**: 2025-10-30  
**问题**: action维度不匹配 - 期望37维，实际35维  
**数据集**: discover_robotics_aitbot_mmk2 / storage_peaches_and_pears

---

## 🔍 问题症状

```
ConfigError: 前3个episode失败率过高，可能存在配置错误:
  尝试转换: 34 episodes
  跳过: 31 episodes
  失败率: 91.2%

错误详情:
  The feature 'action' of shape '(35,)' does not have the expected shape '(37,)'.
```

---

## 📊 配置版本对比

### MMK2有三个配置版本：

#### 1. **full** (39D) - converter_config_discover_robotics_aitbot_mmk2_third_view_full.yaml
```
action维度 = 39D:
  - 左臂: 6维
  - 右臂: 6维
  - 头部: 2维  ← 包含head
  - 脊柱: 1维
  - 双手: 24维 (每只手12维)
```

#### 2. **lite** (37D) - converter_config_discover_robotics_aitbot_mmk2_third_view_lite.yaml
```
action维度 = 37D:
  - 左臂: 6维
  - 右臂: 6维
  - 脊柱: 1维
  - 双手: 24维 (每只手12维)
  
⚠️ 不包含head action（某些数据版本中head字段缺失）
```

#### 3. **实际数据** (35D) ❌
```
action维度 = 35D:
  - ❓ 比lite版本少2维
  - 可能原因：
    1. xhand数据不完整（每只手少1维）
    2. 缺少某些arm关节
    3. 数据格式变化
```

---

## 🔧 诊断步骤

### Step 1: 检查数据集实际结构

使用schema discovery工具：

```bash
cd /home/liu/program/robocoin-dataset

# 分析具体episode的BSON数据
python scripts/dataset_schema_discovery/discover_dataset_schema.py \
    --dataset-path /mnt/nas/synnas/docker/6discover_robotics_aitbot_mmk2/storage_peaches_and_pears \
    --output-dir outputs/schema_discovery/mmk2_peaches_pears
```

### Step 2: 手动检查BSON文件

```python
import bson
from pathlib import Path

# 选择一个episode
episode_dir = Path("/mnt/nas/synnas/docker/6discover_robotics_aitbot_mmk2/storage_peaches_and_pears/the left hand throws the peach into the left compartment, the right hand throws the pear into the right compartment./0")

# 检查episode_0.bson
with open(episode_dir / "episode_0.bson", "rb") as f:
    data = bson.decode_all(f.read())
    
    # 打印action结构
    for frame in data:
        if 'action' in frame:
            action = frame['action']
            print(f"Action keys: {action.keys()}")
            
            # 检查各部分维度
            if 'left_arm' in action:
                print(f"  left_arm/joint_state/pos: {len(action['left_arm']['joint_state']['pos'])}")
            if 'right_arm' in action:
                print(f"  right_arm/joint_state/pos: {len(action['right_arm']['joint_state']['pos'])}")
            if 'head' in action:
                print(f"  head/joint_state/pos: {len(action['head']['joint_state']['pos'])}")
            if 'spine' in action:
                print(f"  spine/joint_state/pos: {len(action['spine']['joint_state']['pos'])}")
            break

# 检查xhand_control_data.bson
with open(episode_dir / "xhand_control_data.bson", "rb") as f:
    data = bson.decode_all(f.read())
    
    for frame in data:
        if 'action' in frame:
            action = frame['action']
            print(f"\nXHand action keys: {action.keys()}")
            
            if 'left_hand' in action:
                print(f"  left_hand: {len(action['left_hand'])} dimensions")
            if 'right_hand' in action:
                print(f"  right_hand: {len(action['right_hand'])} dimensions")
            break
```

### Step 3: 统计所有维度

```python
# 汇总实际维度
total_dims = 0
components = {}

# 基于Step 2的输出填写：
components['left_arm'] = 6  # 或实际值
components['right_arm'] = 6  # 或实际值
components['head'] = 0  # 如果没有head
components['spine'] = 1  # 或实际值
components['left_hand'] = 12  # 或实际值
components['right_hand'] = 12  # 或实际值

total_dims = sum(components.values())
print(f"Total dimensions: {total_dims}")
print(f"Components: {components}")
```

---

## 🎯 可能的原因和解决方案

### 场景1: 双手数据不完整（每只手10维 instead of 12维）

**诊断结果**:
```
left_hand: 10 dimensions  ← 缺少2维
right_hand: 10 dimensions  ← 缺少2维
```

**总维度**: 6+6+1+10+10 = **33D** ❌ (不是35D，排除)

---

### 场景2: 只有一只手的数据（另一只手缺失）

**诊断结果**:
```
left_hand: 12 dimensions
right_hand: 缺失  ← 完全缺失
```

**总维度**: 6+6+1+12 = **25D** ❌ (不是35D，排除)

---

### 场景3: 双手各缺1维（每只手11维）

**诊断结果**:
```
left_hand: 11 dimensions  ← 缺少1维
right_hand: 11 dimensions  ← 缺少1维
```

**总维度**: 6+6+1+11+11 = **35D** ✅ **匹配！**

**解决方案**: 创建新配置文件 `converter_config_mmk2_35d.yaml`

---

### 场景4: spine缺失 + 某个arm缺失1维

**诊断结果**:
```
left_arm: 5 dimensions  ← 缺少1维
right_arm: 6 dimensions
spine: 缺失
left_hand: 12 dimensions
right_hand: 12 dimensions
```

**总维度**: 5+6+12+12 = **35D** ✅ **可能！**

---

## 📝 创建新配置文件

如果确认数据集是35D，创建新配置：

```bash
cd /home/liu/program/robocoin-dataset/scripts/format_converters/tolerobot/configs

# 复制lite版本作为起点
cp converter_config_discover_robotics_aitbot_mmk2_third_view_lite.yaml \
   converter_config_discover_robotics_aitbot_mmk2_35d.yaml
```

然后根据实际数据结构修改 action 部分（删除缺失的字段或调整range_to）。

---

## 🔄 更新配置工厂

在 `converter_factory_config.yaml` 添加新版本：

```yaml
discover_robotics_aitbot_mmk2:
- version: third_view_full
  # ... 现有配置 ...

- version: third_view_lite
  # ... 现有配置 ...

- version: 35d_version
  verison_description: mmk2 with 35D action (某些字段缺失的特殊版本)
  module: robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_mmk2
  class: LerobotFormatConverterMmk2
  converter_config_path: converter_config_discover_robotics_aitbot_mmk2_35d.yaml
```

---

## 🗄️ 更新数据库

将这个数据集的 `device_model_version` 修改为 `35d_version`：

```sql
-- 查询当前版本
SELECT dataset_uuid, device_model, device_model_version 
FROM dmv_annotation 
WHERE dataset_name LIKE '%storage_peaches_and_pears%';

-- 更新版本
UPDATE dmv_annotation 
SET device_model_version = '35d_version'
WHERE dataset_uuid = 'xxx-xxx-xxx';  -- 替换为实际UUID
```

---

## 🚀 重新转换

更新配置后：

```bash
# 1. 清除失败记录（可选）
python scripts/db/reset_failed_conversions.py \
    --dataset-uuid xxx-xxx-xxx

# 2. 重新启动转换
python scripts/format_converters/tolerobot/server.py \
    --db-file=db/datasets.db \
    --host=172.16.13.140 --port=8769
```

---

## 💡 预防措施

### 1. 使用配置验证工具

```bash
python scripts/config_validation/validate_single_config.py \
    --config-path converter_config_discover_robotics_aitbot_mmk2_35d.yaml \
    --dataset-path /mnt/nas/.../storage_peaches_and_pears
```

### 2. Test模式验证

先用test模式验证：

```bash
python scripts/format_converters/tolerobot/server.py \
    --is-test \
    --specific-device-model discover_robotics_aitbot_mmk2
```

### 3. 文档化特殊版本

在配置文件中添加详细注释：

```yaml
# 🔧 35D 特殊版本
# 
# ⚠️ 使用场景：
#    - storage_peaches_and_pears 数据集及类似数据
#    - 双手数据各缺失1维（每只手11维 instead of 12维）
# 
# 📊 维度构成：
#    - 左臂: 6维
#    - 右臂: 6维
#    - 脊柱: 1维
#    - 左手: 11维 (缺失1维)
#    - 右手: 11维 (缺失1维)
#    - 总计: 35维
```

---

## 📋 诊断检查清单

- [ ] Step 1: 运行 schema discovery 工具
- [ ] Step 2: 手动检查 BSON 文件结构
- [ ] Step 3: 确认实际维度组成（35D = ?）
- [ ] Step 4: 确定缺失的字段
- [ ] Step 5: 创建新配置文件
- [ ] Step 6: 更新 converter_factory_config.yaml
- [ ] Step 7: 更新数据库 device_model_version
- [ ] Step 8: Test模式验证
- [ ] Step 9: 正式转换

---

## 🎓 经验总结

### 何时应该触发ConfigError？

✅ **应该触发**（当前情况）：
- 失败率 > 80%
- 所有失败原因相同
- 明显是配置问题而非数据质量问题

❌ **不应触发**（之前的银河案例）：
- 失败率 < 20%
- 个别episode数据缺失
- 数据采集过程中的随机错误

### 配置错误 vs 数据质量问题

| 类型 | 特征 | 失败率 | 处理方式 |
|------|------|--------|---------|
| **配置错误** | 所有episode相同错误 | >80% | 停止，修正配置 |
| **数据质量** | 个别episode问题 | <20% | 跳过，继续转换 |

---

## 📞 需要帮助？

如果诊断后仍不清楚：

1. 提供 schema discovery 输出
2. 提供具体的BSON数据结构
3. 查看其他同类数据集的配置

---

**创建时间**: 2025-10-30  
**适用范围**: discover_robotics_aitbot_mmk2 数据集  
**优先级**: 🔥 高（阻塞转换）

