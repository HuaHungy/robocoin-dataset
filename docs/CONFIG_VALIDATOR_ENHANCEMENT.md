# 配置验证工具增强（2025-10-22）

## 🎯 用户需求

用户指出关键问题：
> "配置验证工具不能只扫我们config文件有的字段，因为我们字段不一定是多，也有可能是少，这样我们就检测不出问题了。"

**核心问题**:
- 原工具：只检查config定义的字段是否在数据中存在
- **缺陷**：无法发现数据中有但config遗漏的字段
- **风险**：可能遗漏重要的传感器数据

---

## ✅ 已完成的增强

### 1. `config_comparator.py` 增强

#### 新增功能：发现遗漏字段

**修改位置1**: `_compare_state()` 方法

```python
# 🆕 检查数据中有哪些字段未在config中配置（发现遗漏字段）
configured_paths = set()
for sub_state in sub_states:
    args = sub_state.get('args', {})
    h5_path = args.get('h5_path', '')
    bson_path = args.get('bson_file', '') + '/' + args.get('data_path', '')
    
    if h5_path:
        configured_paths.add(h5_path)
    if bson_path:
        configured_paths.add(bson_path)

# 遍历schema中的所有字段
unconfigured_fields = []
for category in ['qpos', 'qvel', 'state', 'eef_pos', 'eef_quat', 'other']:
    if category in schema_obs:
        for field_name, field_info in schema_obs[category].items():
            field_path = field_info.get('h5_path', '') or field_info.get('bson_path', '')
            
            # 检查这个路径是否被配置了
            is_configured = False
            for conf_path in configured_paths:
                if conf_path in field_path or field_path in conf_path:
                    is_configured = True
                    break
            
            if not is_configured and field_path:
                unconfigured_fields.append({
                    'category': category,
                    'field_name': field_name,
                    'path': field_path,
                    'shape': field_info.get('shape'),
                    'dtype': field_info.get('dtype'),
                    'data_quality': field_info.get('data_quality', 'ok')
                })
```

**修改位置2**: `_compare_actions()` 方法

```python
# 🆕 检查数据中有哪些action字段未在config中配置
unconfigured_actions = []
if isinstance(schema_actions, dict):
    for action_name, action_info in schema_actions.items():
        action_path = action_info.get('h5_path', '') or action_info.get('bson_path', '')
        
        is_configured = False
        for conf_path in configured_paths:
            if conf_path in action_path or action_path in conf_path:
                is_configured = True
                break
        
        if not is_configured and action_path:
            unconfigured_actions.append({
                'action_name': action_name,
                'path': action_path,
                'shape': action_info.get('shape'),
                'dtype': action_info.get('dtype')
            })
```

**修改位置3**: `generate_readable_report()` 方法

```python
# 🆕 遗漏的字段（数据中有但config中没配置）
if unconfigured_fields or unconfigured_actions:
    lines.append("\n" + "=" * 70)
    lines.append("⚠️  遗漏的字段（数据中有但config中未配置）")
    lines.append("=" * 70)
    
    if unconfigured_fields:
        lines.append("\n[Observations - 未配置的字段]")
        lines.append(f"发现 {len(unconfigured_fields)} 个未配置的observation字段:")
        for field in unconfigured_fields:
            quality_icon = "⚠️" if field.get('data_quality') == 'suspicious' else "ℹ️"
            lines.append(f"  {quality_icon} {field['category']}/{field['field_name']}")
            lines.append(f"      路径: {field['path']}")
            lines.append(f"      Shape: {field.get('shape')}, Dtype: {field.get('dtype')}")
```

---

## 📊 新增的报告内容

### 报告示例

```
======================================================================
⚠️  遗漏的字段（数据中有但config中未配置）
======================================================================

[Observations - 未配置的字段]
发现 3 个未配置的observation字段:
  ℹ️  qvel/joint_velocity
      路径: observations/qvel
      Shape: (500, 12), Dtype: float32
  
  ⚠️  other/imu_data
      路径: observations/imu
      Shape: (500, 6), Dtype: float32
      ⚠️  数据质量可疑
  
  ℹ️  eef_pos/end_effector_position
      路径: observations/eef_pos
      Shape: (500, 6), Dtype: float32

[Actions - 未配置的字段]
发现 1 个未配置的action字段:
  ℹ️  gripper_force
      路径: action/gripper_force
      Shape: (500,), Dtype: float32
```

---

## 🎯 使用场景

### 场景1: 发现遗漏的传感器数据

**问题**: MMK2的BSON文件可能包含speed、vel等数据，但config中只配置了pos

**解决**: 工具会报告：
```
⚠️  遗漏的字段:
  ℹ️  left_arm/speed
      路径: observation/left_arm/joint_state/speed
      Shape: (500, 6), Dtype: float32
```

**后续操作**: 
1. 决定是否需要这个字段
2. 如需要，添加到config中
3. 如不需要，在文档中注明原因

---

### 场景2: 发现末端执行器姿态

**问题**: H5文件中有`eef_quat`（末端四元数），但config只配置了`eef_pos`

**解决**: 工具会报告：
```
⚠️  遗漏的字段:
  ℹ️  eef_quat/end_effector_orientation
      路径: observations/eef_quat
      Shape: (500, 4), Dtype: float32
```

---

### 场景3: 发现额外的相机

**问题**: 数据中有第4个相机，但config只配置了3个

**解决**: 已有的images对比会发现：
```
⚠️  相机发现问题:
  数据中存在摄像头 'camera_extra'，但配置中未定义
```

---

## 🔄 工作流程

### 1. 运行验证工具

```bash
cd scripts/config_validation
./run_validation.sh \
  --device-model discover_robotics_aitbot_mmk2 \
  --config converter_config_discover_robotics_aitbot_mmk2_third_view.yaml \
  --num-samples 2
```

### 2. 查看报告

报告会包含：
- ✅ 配置正确的字段
- ❌ 配置错误的字段（维度不匹配等）
- ⚠️ 数据质量问题的字段（全0、常量等）
- 🆕 **遗漏的字段**（数据有但config没有）

### 3. 决策

对于每个遗漏的字段：
1. **需要**: 添加到config
2. **不需要**: 在文档中注明原因
3. **不确定**: 咨询数据采集方

### 4. 修正配置

根据报告修正config文件，重新验证。

---

## 📈 预期效果

### Before（增强前）
```
配置验证报告
======================================================================
总错误数: 2
总警告数: 1

Observations
======================================================================
[State]
  ✓ qpos [0:12]
      Names: joint_1, joint_2, joint_3...
  ✗ qvel [0:12]
      - h5_path 'qvel' 未在数据中找到
```

**问题**: 只能发现config定义但数据中没有的字段

---

### After（增强后）
```
配置验证报告
======================================================================
总错误数: 2
总警告数: 1

Observations
======================================================================
[State]
  ✓ qpos [0:12]
      Names: joint_1, joint_2, joint_3...
  ✗ qvel [0:12]
      - h5_path 'qvel' 未在数据中找到

======================================================================
⚠️  遗漏的字段（数据中有但config中未配置）
======================================================================

[Observations - 未配置的字段]
发现 2 个未配置的observation字段:
  ℹ️  other/imu_data
      路径: observations/imu
      Shape: (500, 6), Dtype: float32
  
  ℹ️  eef_pos/end_effector
      路径: observations/eef_pos
      Shape: (500, 3), Dtype: float32
```

**优势**: 同时发现config多余和缺失的字段

---

## ✅ 测试验证

### 测试用例1: MMK2数据集

**预期**:
- 发现`speed`、`vel`等未配置的字段（如果存在）
- 报告所有BSON文件中的字段

### 测试用例2: H5数据集

**预期**:
- 发现`eef_quat`等未配置的姿态数据
- 报告所有H5 group中的字段

---

## 🔗 相关文件

- 修改的文件: `scripts/config_validation/config_comparator.py`
- 新增功能: 3个方法增强
- 新增报告: "遗漏的字段"部分

---

## 📝 下一步

1. ✅ 工具增强完成
2. 🔄 运行MMK2数据验证
3. 📋 分析报告，发现遗漏字段
4. ✏️ 修正MMK2配置文件
5. 🚀 应用到其他device

---

**状态**: ✅ 增强完成，准备测试MMK2数据

