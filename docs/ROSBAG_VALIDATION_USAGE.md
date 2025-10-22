# ROS Bag配置验证使用指南

## 🎯 快速开始

### 1. 验证单个bag文件

```python
from pathlib import Path
from scripts.config_validation.schema_analyzer import SchemaAnalyzer
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)

# 创建分析器
analyzer = SchemaAnalyzer()

# 分析bag文件
bag_file = Path("/path/to/your/data.bag")
schema = analyzer.analyze_episode(bag_file, format_type="rosbag")

# 打印topics
print(f"\n发现 {len(schema['topics'])} 个topics:")
for topic_name, topic_info in schema['topics'].items():
    print(f"  - {topic_name}: {topic_info['msg_count']}条消息")

# 打印observations
print(f"\nObservations State字段:")
for field_path, field_info in schema['observations']['state'].items():
    shape = field_info.get('shape', 'N/A')
    is_zero = field_info.get('is_all_zero', False)
    status = "⚠️ 全零" if is_zero else "✅ 有数据"
    print(f"  - {field_path} {shape} {status}")
```

---

## 📋 完整验证流程

### Step 1: 运行批量验证

```bash
# 验证Galaxea R1 Lite
python scripts/config_validation/batch_validation.py \
    --database /mnt/db/datasets.db \
    --config-dir ./scripts/format_converters/tolerobot/configs/ \
    --output-dir ./outputs/validation \
    --device-model galaxea_r1_lite \
    --num-datasets 2
```

### Step 2: 查看验证报告

```bash
# 报告位置
ls ./outputs/validation/galaxea_r1_lite_*.txt
ls ./outputs/validation/galaxea_r1_lite_*.json

# 查看文本报告
cat ./outputs/validation/galaxea_r1_lite_latest.txt
```

### Step 3: 分析结果

验证报告会包含：

#### A. Topics列表
```
==================================================
📊 ROS Bag Topics分析
==================================================

发现 10 个topics:
  ✅ /hdas/feedback_left_arm (186条消息)
  ✅ /hdas/feedback_right_arm (186条消息)
  ✅ /hdas/feedback_torso (186条消息)
  ✅ /hdas/feedback_gripper_left (186条消息)
  ⚠️  /hdas/feedback_chassis (186条消息) - 全零数据
  ...
```

#### B. 配置对比
```
==================================================
📊 配置验证结果
==================================================

[Topic存在性检查]
  ✅ /hdas/feedback_left_arm - 存在
  ✅ /hdas/feedback_right_arm - 存在
  ❌ /hdas/feedback_unknown - 配置中有但数据中不存在

[维度检查]
  ✅ /hdas/feedback_left_arm: 配置6维，实际6维
  ❌ /hdas/feedback_torso: 配置3维，实际4维
     建议: 修改range_to为4

[数据质量]
  ⚠️  /hdas/feedback_chassis: 全零数据
     建议: 检查传感器是否正常工作
```

#### C. 遗漏字段
```
==================================================
⚠️  遗漏的有意义字段
==================================================

以下字段在数据中存在但配置中未使用：

1. /hdas/feedback_left_arm/velocity (6维)
   - 数值范围: -1.79 ~ 1.72 rad/s
   - 非零值: 186/186 (100%)
   - ⚠️ 建议添加到配置

2. /hdas/feedback_left_arm/effort (6维)
   - 数值范围: -6.70 ~ 6.88 Nm
   - 非零值: 186/186 (100%)
   - ⚠️ 建议添加到配置
```

---

## 🔍 针对Galaxea R1 Lite的检查清单

### 已知问题检查

根据之前的分析文档，重点检查：

#### 1. ✅ Gripper单位
```yaml
# 检查gripper是否有degree2rad转换
- names:
  - left_gripper_open_rad
  args:
    topic_name: /hdas/feedback_gripper_left
    range_from: 0
    range_to: 1
  convert_func: degree2rad  # ✅ 必须有这个
```

#### 2. ✅ Torso维度
```yaml
# 检查torso是否是4维（不是3维）
- names:
  - torso_joint_1_rad
  - torso_joint_2_rad
  - torso_joint_3_rad
  - torso_joint_4_rad  # ✅ 必须有第4个
  args:
    range_to: 4  # ✅ 必须是4
```

#### 3. ⚠️ Chassis全零
```yaml
# chassis数据全零，可能不工作
- names:
  - chassis_pos_x_m
  - chassis_pos_y_m
  - chassis_pos_theta_rad
  # ⚠️ 数据全零，可能需要删除或注释
```

#### 4. ⚠️ Torso第4维全零
```yaml
# torso第4个关节全零
- torso_joint_4_rad  # ⚠️ 虽然维度存在，但数据全零
```

---

## 🛠️ 修复配置的步骤

### 1. 自动生成修复建议

```python
from scripts.config_validation.config_comparator import ConfigComparator

comparator = ConfigComparator()

# 对比schema和config
comparison = comparator.compare(schema, config)

# 生成修复建议
fixes = comparator.generate_fix_suggestions(comparison)

# 打印建议
for fix in fixes:
    print(f"{fix['severity']}: {fix['message']}")
    print(f"  建议: {fix['suggestion']}")
```

### 2. 手动修改配置文件

根据报告，修改`converter_config_galaxea_r1_lite.yaml`：

```yaml
# 修改torso维度
- names:
  - torso_joint_1_rad
  - torso_joint_2_rad
  - torso_joint_3_rad
  - torso_joint_4_rad  # 🆕 添加第4维
  args:
    topic_name: /hdas/feedback_torso
    range_from: 0
    range_to: 4  # ✅ 修改为4

# 添加gripper转换
- names:
  - left_gripper_open_rad
  args:
    topic_name: /hdas/feedback_gripper_left
    range_from: 0
    range_to: 1
  convert_func: degree2rad  # 🆕 添加转换函数
```

### 3. 重新验证

```bash
# 再次运行验证确认修复
python scripts/config_validation/batch_validation.py \
    --device-model galaxea_r1_lite \
    --num-datasets 1
```

---

## 📊 验证报告解读

### 严重级别

- ❌ **ERROR**: 必须修复（配置与数据不匹配）
- ⚠️ **WARNING**: 建议检查（可能有问题）
- ℹ️ **INFO**: 仅供参考（不影响功能）

### 常见问题类型

#### 类型1: Topic不存在
```
❌ ERROR: Topic '/hdas/unknown' not found in bag file
建议: 从配置中删除此topic，或检查topic名称拼写
```

#### 类型2: 维度不匹配
```
❌ ERROR: Dimension mismatch for '/hdas/feedback_torso'
配置期望: 3维 (range_from:0, range_to:3)
实际数据: 4维
建议: 修改range_to为4，并添加第4个字段名
```

#### 类型3: 全零数据
```
⚠️ WARNING: All-zero data in '/hdas/feedback_chassis'
建议: 检查传感器是否工作，或从配置中删除
```

#### 类型4: 遗漏字段
```
⚠️ WARNING: Unconfigured field with meaningful data
字段: /hdas/feedback_left_arm/velocity
建议: 添加此字段到配置（数据有意义）
```

---

## 🔧 高级用法

### 自定义验证规则

```python
class CustomValidator:
    def validate_schema(self, schema, config):
        errors = []
        
        # 自定义规则1: 检查gripper单位转换
        for obs in config['features']['observation']['state']['sub_state']:
            if 'gripper' in str(obs.get('names', [])).lower():
                if obs.get('convert_func') != 'degree2rad':
                    errors.append({
                        'type': 'missing_conversion',
                        'message': 'Gripper需要degree2rad转换'
                    })
        
        # 自定义规则2: 检查是否有vel/eff字段
        state_topics = set()
        for field_path in schema['observations']['state'].keys():
            topic = field_path.split('/')[0] + '/' + field_path.split('/')[1]
            state_topics.add(topic)
        
        for topic in state_topics:
            # 检查是否配置了velocity和effort
            has_vel = any('velocity' in str(sub) for sub in config['features']['observation']['state']['sub_state'])
            has_eff = any('effort' in str(sub) for sub in config['features']['observation']['state']['sub_state'])
            
            if not has_vel:
                errors.append({
                    'type': 'missing_field',
                    'message': f'{topic}缺少velocity配置'
                })
        
        return errors
```

---

## 📋 完整工作流程示例

```bash
# 1. 分析数据
python scripts/config_validation/batch_validation.py \
    --device-model galaxea_r1_lite \
    --num-datasets 2 \
    --output-dir ./validation_output

# 2. 查看报告
cat ./validation_output/galaxea_r1_lite_*.txt

# 3. 根据报告修改配置文件
vim scripts/format_converters/tolerobot/configs/converter_config_galaxea_r1_lite.yaml

# 4. 重新验证
python scripts/config_validation/batch_validation.py \
    --device-model galaxea_r1_lite \
    --num-datasets 1

# 5. 确认全部通过后，提交修改
git add scripts/format_converters/tolerobot/configs/converter_config_galaxea_r1_lite.yaml
git commit -m "fix: update galaxea_r1_lite config based on validation"
```

---

**文档创建时间**: 2025-10-22  
**下一步**: 运行实际验证并修复Galaxea配置

