# 乐聚外部数据集配置修复

**日期**: 2025-10-30  
**问题**: lite版本配置文件使用了不存在的H5路径  
**数据集**: 乐聚2 `/hotel_services`  
**状态**: ✅ 已修复

---

## 🐛 问题描述

### **错误信息**

```
ConfigError: 严格模式下检测到字段缺失（可能是配置错误）

KeyError: Unable to synchronously open object (object 'velocity' doesn't exist)

🔍 期望路径: action/joint/velocity  ❌
📊 文件中实际存在: action/joint/position ✅
```

### **根本原因**

**lite版本和full版本配置不一致**：

| 版本 | observation | action | 状态 |
|------|-------------|--------|------|
| **full** | `state/joint/velocity` | `state/joint/velocity` | ✅ 正确 |
| **lite** | `state/joint/velocity` | `action/joint/velocity` | ❌ 错误 |

**H5文件中的实际数据**：
- ✅ `state/joint/velocity` - 存在
- ❌ `action/joint/velocity` - **不存在**

---

## 🔧 修复方案

### **修复内容**

**文件**: `converter_config_leju_waibu_lite.yaml`

**修改**: 2处 (observation section + action section)

| Section | Line | 修改前 | 修改后 |
|---------|------|--------|--------|
| observation.state.sub_state | 190, 206 | `action/joint/velocity` | `state/joint/velocity` |
| action.sub_action | 348, 363 | `action/joint/velocity` | `state/joint/velocity` |

### **修复代码**

#### **修复点1: observation section (lines 190, 206)**

```yaml
# ❌ 修复前
h5_path: action/joint/velocity  # 不存在！

# ✅ 修复后
h5_path: state/joint/velocity   # 与full版本一致
```

#### **修复点2: action section (lines 348, 363)**

```yaml
# ❌ 修复前
h5_path: action/joint/velocity  # 不存在！

# ✅ 修复后
h5_path: state/joint/velocity   # 与full版本一致
```

---

## 📊 完整对比

### **修复前**

```yaml
# Observation section
- names: [left_arm_joint_1_vel_rad_s, ...]
  args:
    h5_path: action/joint/velocity  ❌
    range_from: 0
    range_to: 7

# Action section
- names: [left_arm_joint_1_vel_rad_s, ...]
  args:
    h5_path: action/joint/velocity  ❌
    range_from: 0
    range_to: 7
```

### **修复后**

```yaml
# Observation section
- names: [left_arm_joint_1_vel_rad_s, ...]
  args:
    h5_path: state/joint/velocity  ✅
    range_from: 0
    range_to: 7

# Action section (using state velocity as action)
- names: [left_arm_joint_1_vel_rad_s, ...]
  args:
    h5_path: state/joint/velocity  ✅
    range_from: 0
    range_to: 7
```

---

## 🎯 为什么action使用state/velocity？

### **设计说明**

在机器人控制中，**velocity action**通常来源于**当前状态的velocity**：

```
当前状态速度 → 作为下一步的action速度指令
state/joint/velocity → action velocity
```

这是一个常见的模式，特别是在：
1. **模仿学习**: 从演示中学习速度控制
2. **位置+速度控制**: position来自action，velocity来自state
3. **数据采集限制**: action空间中没有单独记录velocity

**full版本**已经正确实现了这个模式，lite版本的错误配置只是一个**拼写错误**。

---

## 🔍 H5文件结构

### **实际存在的路径**

```
✅ 可用路径:
   - action/joint/position       (位置)
   - state/joint/velocity        (速度)
   - state/joint/position        (位置)
   - action/head/position
   - action/leg/position
   ... 等

❌ 不存在的路径:
   - action/joint/velocity       ← 配置错误使用了这个
```

---

## ✅ 验证修复

### **重新运行转换**

```bash
# 重新启动转换
python scripts/format_converters/tolerobot/server.py \
    --db-file=db/datasets.db \
    --host=0.0.0.0 --port=8769 \
    --is-test
```

### **预期结果**

```
✅ No KeyError about velocity
✅ 配置文件路径全部匹配
✅ 转换成功完成
```

---

## 💡 经验教训

### **配置一致性的重要性**

1. **同一数据集的不同版本(full/lite)应该使用相同的H5路径**
   - full版本: `state/joint/velocity` ✅
   - lite版本: 应该一致 ✅

2. **在修改配置时要检查所有引用**
   - observation section
   - action section
   - 确保两处都修改

3. **ConfigError是好事**
   - 系统正确地识别了配置问题
   - 严格模式在前3个episode就发现问题
   - 避免了大量无效转换

---

## 🔗 相关问题

### **如何检查H5文件结构？**

```python
import h5py

h5_file = h5py.File('proprio_stats.hdf5', 'r')

# 递归打印所有路径
def print_structure(name, obj):
    if isinstance(obj, h5py.Dataset):
        print(f"  - {name}: shape={obj.shape}, dtype={obj.dtype}")

h5_file.visititems(print_structure)
```

### **如何快速定位配置错误？**

错误信息已经很详细：

```
❌ H5 路径不存在
   📁 H5 文件: proprio_stats.hdf5
   🔍 期望路径: action/joint/velocity
   📊 文件中实际存在的数据集路径:
      - action/joint/position      ← 用这个
      - state/joint/velocity       ← 或用这个
```

---

## 📋 修复清单

- [x] 修复 observation section 的 left arm velocity路径
- [x] 修复 observation section 的 right arm velocity路径
- [x] 修复 action section 的 left arm velocity路径
- [x] 修复 action section 的 right arm velocity路径
- [ ] 重新测试乐聚数据集转换
- [ ] 确认full版本和lite版本都能正常工作

---

## 🎉 总结

**配置错误修复完成！**

- ✅ lite版本现在与full版本一致
- ✅ 所有velocity路径都指向 `state/joint/velocity`
- ✅ ConfigError机制正常工作，及时发现问题
- ✅ 修复简单，影响范围明确

**系统容错机制表现优秀**：
- ✅ 正确识别为ConfigError（不是数据错误）
- ✅ 在前3个episode就发现问题（严格模式）
- ✅ 提供详细的诊断信息和修复建议
- ✅ 避免了大量无效转换

**现在乐聚数据集应该能正常转换了！** 🚀

