# Agilex Masterpuppet Gripper量纲分析

## 数据来源
- **文件**: episode_171.hdf5 (2114帧)
- **分析对象**: 关节数据第7维（索引6和13）= Gripper

---

## 📊 Gripper数据统计（全部2114帧）

### 1. **master/joint - Gripper位置**

| 位置 | 索引 | Min | Max | Mean | Std | 范围 |
|------|------|-----|-----|------|-----|------|
| 左臂 | [6] | -0.000280 | 0.074130 | 0.007074 | 0.018568 | **0.0744 rad** |
| 右臂 | [13] | 0.000000 | 0.072450 | 0.005220 | 0.014357 | **0.0725 rad** |

### 2. **puppet/joint - Gripper位置**

| 位置 | 索引 | Min | Max | Mean | Std | 范围 |
|------|------|-----|-----|------|-----|------|
| 左臂 | [6] | -0.000280 | 0.069300 | 0.008290 | 0.018067 | **0.0696 rad** |
| 右臂 | [13] | 0.000000 | 0.068390 | 0.009117 | 0.012833 | **0.0684 rad** |

### 3. **puppet/effort - Gripper力矩**

| 位置 | 索引 | Min | Max | Mean | Std | 范围 |
|------|------|-----|-----|------|-----|------|
| 左臂 | [6] | -1.314 | 0.310 | -0.105 | 0.344 | **1.624 N·m** |
| 右臂 | [13] | -1.833 | 0.345 | -0.755 | 0.702 | **2.178 N·m** |

### 4. **puppet/velocity - Gripper速度**

| 位置 | 索引 | Min | Max | Mean | 状态 |
|------|------|-----|-----|------|------|
| 左臂 | [6] | 0.0 | 0.0 | 0.0 | ⚠️ **全零** |
| 右臂 | [13] | 0.0 | 0.0 | 0.0 | ⚠️ **全零** |

---

## 🔍 量纲判断

### 方法1: 数值范围分析

Gripper位置范围: **[-0.0003, 0.074] rad**

**可能的量纲：**

| 假设量纲 | 转换值 | 合理性判断 |
|----------|--------|-----------|
| **弧度 (rad)** | 0.074 rad ≈ **4.24°** | ✅ **合理** - Gripper开合4度符合实际 |
| 度 (degree) | 0.074° | ❌ 太小 - Gripper不可能只开0.074度 |
| 米 (m) | 0.074 m = 7.4 cm | ❌ 不合理 - 关节角度不用米表示 |

### 方法2: 数据一致性分析

**其他关节的范围（弧度）：**
```
joint_1: [-0.47, 0.39]  rad
joint_2: [-0.02, 2.32]  rad
joint_3: [-2.26, 0.04]  rad
joint_4: [-0.16, 1.81]  rad
joint_5: [0.09, 1.31]   rad
joint_6: [-2.14, 0.18]  rad
joint_7: [-0.0003, 0.074] rad  ← Gripper
```

**一致性原则**: 同一个 `joint` 数组中，前6个关节是 `rad`，第7个（gripper）也应该是 `rad`。

### 方法3: 力矩数据验证

Gripper力矩范围: **[-1.83, 0.35] N·m**

- ✅ 这个范围对于gripper的夹持力矩是合理的
- ✅ 与位置数据的单位（rad）配合，符合物理意义

---

## ✅ 最终结论

### **Gripper量纲: 弧度 (rad)**

**证据：**
1. ✅ 数值范围 0.074 rad ≈ 4.24度，符合gripper实际开合角度
2. ✅ 与其他6个关节的量纲一致（都是rad）
3. ✅ 力矩数据范围合理（-1.83 ~ 0.35 N·m）
4. ✅ 数据结构一致性（同一个joint数组应使用相同单位）

---

## 📝 配置建议

### 字段命名

**当前命名（通用）：**
```yaml
master_left_arm_joint_7_rad     # ✅ 正确
puppet_left_arm_joint_7_rad     # ✅ 正确
```

**或使用语义化命名（推荐）：**
```yaml
master_left_gripper_rad         # 更清晰
puppet_left_gripper_rad         # 更清晰
```

### 单位后缀确认

| 数据类型 | 单位后缀 | 示例 |
|----------|----------|------|
| Gripper位置 | `_rad` | `puppet_left_gripper_rad` |
| Gripper力矩 | `_eff_nm` | `puppet_left_gripper_eff_nm` |
| Gripper速度 | `_vel_rad_s` | `puppet_left_gripper_vel_rad_s` (但全零) |

---

## 📌 特殊说明

### 1. **Gripper速度全零**
- puppet/velocity 的第7维（gripper）在所有2114帧中都是0
- **建议**: 从配置中排除gripper速度字段

### 2. **Gripper力矩有效**
- puppet/effort 的第7维有丰富的数据（309-481个unique值）
- **建议**: 保留gripper力矩字段

### 3. **Master vs Puppet**
- Master: 操作员手柄的gripper状态
- Puppet: 机器人gripper的实际状态
- 两者数据范围相似，表明遥操作映射良好

---

## 🎯 配置更新建议

### 需要更新的字段（保持 `_rad` 后缀）：

```yaml
# Observation.State
master_left_arm_joint_7_rad       # 或 master_left_gripper_rad
master_right_arm_joint_7_rad      # 或 master_right_gripper_rad
puppet_left_arm_joint_7_rad       # 或 puppet_left_gripper_rad
puppet_right_arm_joint_7_rad      # 或 puppet_right_gripper_rad
puppet_left_arm_joint_7_eff_nm    # 或 puppet_left_gripper_eff_nm
puppet_right_arm_joint_7_eff_nm   # 或 puppet_right_gripper_eff_nm

# Action (同上)
```

### 需要排除的字段：

```yaml
# puppet/velocity [6, 13] - Gripper速度全零
puppet_left_arm_joint_7_vel_rad_s   # ❌ 排除
puppet_right_arm_joint_7_vel_rad_s  # ❌ 排除
```

---

## 总结

| 项目 | 结论 |
|------|------|
| **Gripper量纲** | ✅ **弧度 (rad)** |
| **范围** | [-0.0003, 0.074] rad ≈ [-0.02°, 4.24°] |
| **配置命名** | `*_gripper_rad` 或 `*_joint_7_rad` |
| **力矩数据** | ✅ 有效，保留 (`*_eff_nm`) |
| **速度数据** | ❌ 全零，排除 (`*_vel_rad_s`) |
| **配置质量** | 🟢 **优秀** - 量纲确认无误 |

