# 配置验证工具完整逻辑（2025-10-22）

## 🎯 工具目标

**快速验证**converter配置文件是否与实际数据匹配，**不需要正式转换**

---

## 📊 验证工具的完整流程

### Step 1: Episode定位 (`episode_locator.py`)

**作用**：找到每个task的episodes

**支持的格式**:
- ✅ H5格式：`*.hdf5`, `*.h5`
- ✅ JSON格式：`*.json`
- ✅ MCAP格式：`*.mcap`
- ✅ BSON格式：`*.bson`
- ✅ Video格式：`*.mp4`, `*.avi`
- ⚠️ **ROS Bag格式：`*.bag`** (定位支持，分析不支持)

**输出**：Episode列表

---

### Step 2: Schema分析 (`schema_analyzer.py`)

**作用**：深度分析采样episodes的**实际数据**

**检测内容**:
1. **字段结构**：所有存在的字段路径
2. **数据维度**：每个字段的shape
3. **数据类型**：dtype
4. **数值范围**：min/max/mean/std
5. **数据质量**：
   - ✅ 是否全零 (`ALL_ZERO`)
   - ✅ 是否常量 (`CONSTANT`)
   - ✅ 变化范围极小 (`VERY_SMALL_RANGE`)

**支持的格式**:
- ✅ H5格式
- ✅ JSON格式
- ✅ BSON格式
- ⏸️ **MCAP格式** (部分支持)
- ❌ **ROS Bag格式** (未实现)

**输出**：Schema字典

---

### Step 3: 配置对比 (`config_comparator.py`)

**作用**：对比实际schema与配置文件

#### 🔍 检查1: 字段匹配

**检查项**:
1. ✅ **配置中的字段是否存在于数据中**
   - 如果不存在 → ❌ `missing_field` 错误
   
2. ✅ **数据中的字段是否都被配置了**（**重要！用户新需求**）
   - 如果数据中有字段但配置中没有 → ⚠️ `unconfigured_fields` 警告
   - 需要检查这个字段是否有意义（非零、非常量）

#### 🔍 检查2: 维度匹配（**用户强调的重点**）

**检查项**:
1. ✅ **Shape是否匹配**
   - 配置：`range_from: 0, range_to: 6` → 期望6维
   - 实际：数据shape是`(6,)` → ✅ 匹配
   - 实际：数据shape是`(5,)` → ❌ `dimension_mismatch`

2. ✅ **检查实际数据的每一维**
   ```python
   配置要求: joint_1, joint_2, joint_3 (3维)
   实际数据: 有4维
   → ❌ 维度不匹配：配置3维，实际4维
   ```

#### 🔍 检查3: 数据质量

**检查项**:
1. ✅ **配置的字段数据是否有意义**
   - 如果是全零 → ⚠️ 警告：数据可能无效
   - 如果是常量 → ⚠️ 警告：传感器可能故障

2. ✅ **未配置的字段数据是否有意义**（**新增需求**）
   - 如果未配置字段有意义的数据 → ⚠️ 警告：可能遗漏重要数据
   - 如果未配置字段全零/常量 → ✅ 正常忽略

---

## 🚨 当前缺失的功能

### 1. ❌ ROS Bag格式支持

**问题**：
- `episode_locator.py`可以定位`.bag`文件 ✅
- `schema_analyzer.py`不能分析`.bag`文件 ❌
- 运行时报错：`ValueError: 不支持的格式: rosbag`

**解决方案**：
需要在`schema_analyzer.py`中实现`_analyze_rosbag()`方法

**是否需要？** 
- Galaxea R1 Lite使用ROS bag格式
- 如果要验证`converter_config_galaxea_r1_lite.yaml`，**必须支持**

---

### 2. ⚠️ 未配置字段的智能检测（**用户新需求**）

**需求**：
检测数据中存在但配置中未使用的字段，并判断是否有意义

**实现逻辑**：
```python
# 1. 获取数据中所有字段
all_data_fields = schema['observations']['qpos'] + schema['observations']['qvel'] + ...

# 2. 获取配置中的字段
configured_fields = [从config中提取所有h5_path/bson_path/topic_name]

# 3. 找出未配置的字段
unconfigured_fields = all_data_fields - configured_fields

# 4. 检查这些字段是否有意义
for field in unconfigured_fields:
    if is_all_zero(field.data):
        status = "OK - 全零数据，正确忽略"
    elif is_constant(field.data):
        status = "OK - 常量数据，正确忽略"
    else:
        status = "⚠️ WARNING - 有意义的数据被遗漏！"
```

**当前状态**：
- ✅ 已部分实现（`unconfigured_fields`）
- ⏸️ 未完全实现数据质量判断

---

### 3. ⚠️ 维度检查增强（**用户强调**）

**需求**：
不只是报告维度不匹配，还要显示：
- 配置期望的维度
- 实际数据的维度
- 具体哪几维不匹配

**当前状态**：
- ✅ 已实现基本维度检查
- ⏸️ 错误信息不够详细

**增强方案**：
```python
{
    'type': 'dimension_mismatch',
    'field': 'left_arm/joint_state/pos',
    'configured_dim': 6,
    'actual_dim': 5,
    'detail': 'Config expects 6 joints, but data only has 5'
}
```

---

## 📋 完整验证流程示例

```bash
# 1. 运行验证工具
python scripts/config_validation/batch_validation.py \
    --database /mnt/db/datasets.db \
    --config-dir ./scripts/format_converters/tolerobot/configs/ \
    --output-dir ./outputs/validation \
    --device-model galaxea_r1_lite \
    --num-datasets 2

# 2. 输出验证报告
outputs/validation/
├── galaxea_r1_lite_default_version_YYYY-MM-DD_HH-MM-SS.txt
└── galaxea_r1_lite_default_version_YYYY-MM-DD_HH-MM-SS.json
```

**报告内容**：
```
==================================================
📊 Observations验证结果
==================================================

[State字段]
  ✅ left_arm/joint_state/pos (6维) - 匹配
  ❌ torso/joint_state/pos (4维) - 维度不匹配
     配置期望：3维 (range_from:0, range_to:3)
     实际数据：4维
     建议：修改range_to为4

  ⚠️  chassis/position/x - 全零数据
     建议：检查传感器是否工作

==================================================
⚠️  遗漏的字段（数据中有但config中未配置）
==================================================

[Observations]
  ⚠️  left_arm/joint_state/vel (6维)
      数值范围：-1.79 ~ 1.72 rad/s
      非零值：1116/1116
      ⚠️  这是有意义的数据！建议添加到配置

  ⚠️  left_arm/joint_state/eff (6维)
      数值范围：-6.70 ~ 6.88 Nm
      非零值：1116/1116
      ⚠️  这是有意义的数据！建议添加到配置

  ✅ left_arm_eef/data (未找到)
      状态：OK - 数据不存在，正确未配置
```

---

## 🔧 需要修复的问题

### Priority 1 - Critical
1. ❌ 实现`_analyze_rosbag()`方法（支持Galaxea验证）
2. ✅ 增强未配置字段检测（已部分实现）
3. ✅ 增强维度检查错误信息（已部分实现）

### Priority 2 - High
4. ⏸️ 优化MCAP格式支持
5. ⏸️ 添加配置建议生成（自动生成修正后的YAML）

---

## 🎯 总结

**配置验证工具的核心逻辑**：
1. **定位episodes** → 找到数据
2. **分析schema** → 深入了解数据结构和内容
3. **对比配置** → 找出不匹配和遗漏
4. **生成报告** → 提供详细的修复建议

**关键特性**：
- ✅ 不需要正式转换，快速验证
- ✅ 检查字段、维度、数据质量
- ✅ 检测遗漏的有意义数据
- ⚠️ ROS Bag支持缺失（需要实现）

---

**文档创建时间**: 2025-10-22  
**下一步**: 根据用户指示实现缺失功能

