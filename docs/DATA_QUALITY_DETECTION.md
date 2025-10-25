# 数据质量检测功能

## 🎯 问题描述

在实际数据集中，常见以下数据质量问题：

### 1. 全0数据（ALL_ZERO）
- **现象**: 字段存在，shape正确，但所有值都是0
- **可能原因**:
  - 传感器未连接
  - 数据采集失败
  - 某些状态确实为0（如夹爪关闭、机械臂在原点）

### 2. 常量数据（CONSTANT）
- **现象**: 所有值都是同一个常数（标准差<1e-10）
- **可能原因**:
  - 传感器故障
  - 数据未更新
  - 某些状态确实保持不变（如固定的夹爪宽度）

### 3. 极小变化范围（VERY_SMALL_RANGE）
- **现象**: 数据变化范围<1e-6，可能只是噪声
- **可能原因**:
  - 传感器精度问题
  - 数据量化误差
  - 实际变化确实很小

---

## ✨ 检测机制

### 自动检测

Schema分析器会自动检测这些问题：

```python
# 在 schema_analyzer.py 的 _describe_h5_dataset() 中

# 检测全0数据
is_all_zero = np.all(data == 0)
if is_all_zero:
    desc['warning'] = 'ALL_ZERO'
    desc['data_quality'] = 'suspicious'

# 检测常量数据
elif desc['std'] < 1e-10:
    desc['warning'] = 'CONSTANT'
    desc['data_quality'] = 'suspicious'
    desc['constant_value'] = float(np.mean(data))

# 检测极小变化范围
elif desc['max'] - desc['min'] < 1e-6:
    desc['warning'] = 'VERY_SMALL_RANGE'
    desc['data_quality'] = 'suspicious'
```

### 报告显示

配置对比报告会显示这些警告：

```
[State]
  ⚠️ observations/qpos [7:8]
      Names: left_gripper_open
      - ⚠️ 数据质量问题: 所有值都为0（可能是传感器未连接或数据采集失败）

  ⚠️ observations/qpos [20:23]
      Names: left_eef_pos_x_m, left_eef_pos_y_m, left_eef_pos_z_m
      - ⚠️ 数据质量问题: 所有值都是常量 0.5（可能是传感器故障）
```

---

## 🔍 如何判断

### 情况1: 合理的全0数据 ✅

**示例1**: 夹爪关闭状态
```yaml
# 如果这是一个"抓取"任务，episode开始时夹爪是关闭的
names:
  - right_gripper_open
# 值: 0.0 → 合理，表示夹爪关闭
```

**示例2**: 机械臂在原点
```yaml
# 如果机械臂初始位置在原点
names:
  - right_eef_pos_x_m
  - right_eef_pos_y_m
  - right_eef_pos_z_m
# 值: [0, 0, 0] → 可能合理（但需要确认坐标系）
```

**判断方法**:
- 查看其他episodes，是否也是全0
- 查看视频，确认实际状态
- 检查任务描述，确认是否合理

### 情况2: 异常的全0数据 ❌

**示例1**: 末端执行器位置全0
```yaml
# 采集了100个episodes，所有episode的末端位置都是[0,0,0]
names:
  - right_eef_pos_x_m
  - right_eef_pos_y_m
  - right_eef_pos_z_m
# 值: [0, 0, 0] → 异常！不可能所有episode都在原点
```

**示例2**: 关节角度全0
```yaml
# 采集了"摆放物品"任务，机械臂需要移动
names:
  - right_arm_joint_1_rad
  - right_arm_joint_2_rad
  - ...
# 值: 全0 → 异常！传感器可能未连接
```

**判断方法**:
- 对比多个episodes
- 查看视频确认机械臂确实在移动
- 如果视频中有运动，但数据全0 → 明确异常

---

## 🛠️ 处理建议

### 对于合理的全0数据

**保留配置，添加注释**:
```yaml
- names:
  - right_gripper_open
  args:
    h5_path: observations/qpos
    range_from: 10
    range_to: 11
  # 注释: 部分episodes开始时夹爪为关闭状态(0)，这是正常的
```

### 对于异常的全0数据

**选项A: 从配置中移除**（推荐）
```yaml
# 删除或注释掉无效字段
# - names:
#   - left_eef_pos_x_m  # 数据全0，传感器未连接
#   - left_eef_pos_y_m
#   - left_eef_pos_z_m
#   args:
#     h5_path: observations/qpos
#     range_from: 80
#     range_to: 83
```

**选项B: 标记为可选**
```yaml
- names:
  - left_eef_pos_x_m
  - left_eef_pos_y_m
  - left_eef_pos_z_m
  args:
    h5_path: observations/qpos
    range_from: 80
    range_to: 83
  optional: true  # 标记为可选，某些数据集中可能为0
```

**选项C: 联系数据采集方**

如果发现大量异常全0数据，应联系数据采集方确认：
- 是否传感器配置有问题
- 是否需要重新采集数据
- 是否有其他数据源

---

## 📊 验证报告示例

### 示例1: 发现全0数据

```
======================================================================
配置对比报告
======================================================================

总错误数: 0
总警告数: 3

======================================================================
Observations
======================================================================

[State]
  ✓ observations/qpos [0:7]
      Names: right_arm_joint_1_rad, ...
  
  ⚠️ observations/qpos [10:11]
      Names: right_gripper_open
      - ⚠️ 数据质量问题: 所有值都为0
      → 建议: 查看视频确认夹爪状态，如果确实应该关闭则正常
  
  ⚠️ observations/qpos [80:83]
      Names: left_eef_pos_x_m, left_eef_pos_y_m, left_eef_pos_z_m
      - ⚠️ 数据质量问题: 所有值都为0
      → 建议: 可能是左臂传感器未连接，考虑从配置中移除

======================================================================
Actions
======================================================================

  ⚠️ observations/qpos [10:11]
      Names: right_gripper_open
      - ⚠️ 数据质量问题: 所有action值都为0
      → 建议: 如果任务不涉及夹爪操作，这是正常的
```

---

## 🔄 工作流程

### 1. 运行验证

```bash
bash scripts/config_validation/run_validation.sh
```

### 2. 查看警告

```bash
grep "数据质量问题" outputs/config_validation/*_comparison.txt
```

### 3. 逐个检查

对于每个警告：
1. 查看对应的视频
2. 确认是否合理
3. 决定保留还是移除

### 4. 更新配置

```bash
# 编辑配置文件
vim scripts/format_converters/tolerobot/configs/converter_config_{device_model}.yaml

# 重新验证
bash scripts/config_validation/run_validation.sh
```

### 5. 记录决策

在配置文件中添加注释：
```yaml
# 2025-10-22: 确认right_gripper_open在部分episodes中为0是合理的（夹爪关闭状态）
- names:
  - right_gripper_open
  ...

# 2025-10-22: 移除left_eef_pos字段，数据全0，传感器未连接
# - names:
#   - left_eef_pos_x_m
#   ...
```

---

## 📈 统计分析

### 批量检查全0字段

```python
import json

with open('outputs/config_validation/validation_report.json') as f:
    report = json.load(f)

all_zero_fields = []
for device_model, model_data in report['device_models'].items():
    for dataset in model_data.get('datasets', []):
        comparison = dataset.get('config_comparison', {})
        
        # 检查observations
        for detail in comparison.get('observations', {}).get('state', []):
            if any('所有值都为0' in issue for issue in detail.get('issues', [])):
                all_zero_fields.append({
                    'device_model': device_model,
                    'dataset': dataset['dataset_name'],
                    'field': detail['h5_path'],
                    'names': detail['names']
                })

print(f"发现 {len(all_zero_fields)} 个全0字段")
for field in all_zero_fields:
    print(f"  - {field['device_model']}/{field['dataset']}: {field['field']} ({', '.join(field['names'][:2])}...)")
```

---

## 💡 最佳实践

### 1. 采样验证足够

- 验证至少2个episodes
- 如果发现全0，增加采样数量确认
- 对比不同任务、不同时间采集的数据

### 2. 视频确认

- 始终对照视频确认
- 全0的关节角度 vs 视频中的运动
- 全0的夹爪 vs 视频中的抓取动作

### 3. 文档记录

- 在配置文件中注释决策
- 记录验证时间和结论
- 便于后续维护

### 4. 与采集方沟通

- 发现异常及时反馈
- 确认传感器配置
- 必要时重新采集数据

---

## 🎯 预期效果

使用这个功能后：

✅ **快速发现问题** - 30分钟内发现所有全0字段  
✅ **减少无效数据** - 避免转换无用的全0字段  
✅ **提高数据质量** - 确保训练数据有意义  
✅ **节省存储空间** - 移除无效字段可节省10-20%空间

---

**更新时间**: 2025-10-22  
**功能状态**: ✅ 已实现  
**集成状态**: ✅ 已集成到配置验证工具

开始使用这个功能，发现并处理数据质量问题吧！ 🚀

