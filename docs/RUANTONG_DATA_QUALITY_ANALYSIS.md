# Ruantong A2D 数据质量分析报告

## 📊 数据质量问题汇总

### 1. default_version & gt01_no_depth

#### ✅ 有效字段

| 字段 | 维度 | 范围 | 单位 | 状态 |
|------|------|------|------|------|
| state/joint/position | 14 | 各维度变化范围大 | **_rad** | ✅ 有效 |
| state/end/position | 2×3 | 各维度有变化 | **_m** | ✅ 有效 |
| state/end/orientation | 2×4 | quaternion | 无单位 | ✅ 有效 |
| state/waist/position | 2 | 有微小变化 | **_rad** | ✅ 有效 |
| state/head/position | 2 | 有微小变化 | **_rad** | ✅ 有效 |
| state/effector/position | 2 | 34-119 | **❓ 待确认** | ⚠️ 需确认单位 |

#### ❌ 无效字段 (建议移除)

| 字段 | 原因 | unique值 |
|------|------|----------|
| state/robot/position[0] (x) | 几乎全零 | 1-2 |
| state/robot/position[1] (y) | **全零** | 1 |
| state/robot/position[2] (z) | **全零** | 1 |
| state/robot/orientation[0] (x) | **全零** | 1 |
| state/robot/orientation[1] (y) | **全零** | 1 |
| state/robot/orientation[2] (z) | 几乎常量 | 20-21 |
| state/robot/orientation[3] (w) | 几乎常量 | 20-21 |

**建议**: 完全移除 `robot/position` 和 `robot/orientation` 字段（7维）

---

### 2. gt02_new_version

#### ✅ 有效字段

| 字段 | 范围 | std | unique | 单位 | 状态 |
|------|------|-----|--------|------|------|
| robot_joint_5 | -0.04 ~ 1.48 | 0.56 | 382 | **_rad** | ✅ 有效 |
| robot_joint_6 | 0.15 ~ 1.12 | 0.22 | 374 | **_rad** | ✅ 有效 |
| robot_joint_7 | -2.57 ~ -1.50 | 0.29 | 385 | **_rad** | ✅ 有效 |
| robot_joint_8 | 0.34 ~ 1.72 | 0.37 | 387 | **_rad** | ✅ 有效 |
| robot_joint_9 | 1.07 ~ 1.91 | 0.27 | 373 | **_rad** | ✅ 有效 |
| robot_joint_10 | -1.25 ~ 0.03 | 0.45 | 373 | **_rad** | ✅ 有效 |
| gripper/positions[0] (left) | 0 ~ 115 | 54.53 | 16 | **❓ 待确认** | ⚠️ 需确认单位 |
| gripper/positions[1] (right) | 0 ~ 118 | 45.76 | 20 | **❓ 待确认** | ⚠️ 需确认单位 |

#### ❌ 无效字段 (建议移除)

| 字段 | 原因 | unique值 | 详情 |
|------|------|----------|------|
| robot_joint_1 | **常量** | 1 | 0.1362 (不变) |
| robot_joint_2 | 几乎常量 | 6 | -0.0191 (几乎不变) |
| robot_joint_3 | 几乎常量 | 128 | -0.5001 (微小变化) |
| robot_joint_4 | **NaN!!!** | 1 | ⚠️⚠️⚠️ 完全无效 |
| robot_joint_11 | 常量 | 25 | 0.2360 (几乎不变) |
| robot_joint_12 | 几乎常量 | 101 | ~0.0000 |
| robot_joint_13 | 几乎常量 | 122 | -0.3003 |
| robot_joint_14 | 几乎常量 | 59 | 1.6000 |
| robot_joint_15 | 几乎常量 | 104 | -1.6001 |
| robot_joint_16 | 几乎常量 | 184 | -1.8001 |
| robot_joint_17 | 几乎常量 | 108 | ~0.0000 |
| robot_joint_18 | 几乎常量 | 182 | ~0.0000 |

**建议**: 只保留 joint_5-10 (6维) + gripper (2维) = **8维**

---

## 🔧 配置修正方案

### default_version & gt01_no_depth

**修改前**: 41维
```yaml
# state/joint/position: 14维
# state/end/position: 6维
# state/end/orientation: 8维  
# state/waist/position: 2维
# state/head/position: 2维
# state/effector/position: 2维
# state/robot/position: 3维      ❌ 移除
# state/robot/orientation: 4维    ❌ 移除
```

**修改后**: 34维
```yaml
# 移除 robot/position (3维)
# 移除 robot/orientation (4维)
# 添加单位后缀:
#   - joint: _rad
#   - end position: _m
#   - waist/head: _rad
#   - effector: _pct 或 _deg (待确认)
```

---

### gt02_new_version

**修改前**: 20维
```yaml
# robot_joint_1-18: 18维   ❌ 大部分移除
# gripper: 2维
```

**修改后**: 8维
```yaml
# 只保留:
#   - robot_joint_5_rad
#   - robot_joint_6_rad
#   - robot_joint_7_rad
#   - robot_joint_8_rad
#   - robot_joint_9_rad
#   - robot_joint_10_rad
#   - gripper_left_open_pct (或 _deg)
#   - gripper_right_open_pct (或 _deg)
```

---

## ❓ 需要确认的单位

### effector/gripper 单位

**数据范围**:
- default: effector_left: 34.92-119.95
- default: effector_right: 34.96-117.92
- gt01: effector_left: 34.93-112.77
- gt01: effector_right: 34.92-119.95
- gt02: gripper_left: 0-115.15
- gt02: gripper_right: 0-118.06

**可能的单位**:
1. **百分比** (_pct): 0-100% (但范围超过100？)
2. **角度** (_deg): 度数
3. **毫米** (_mm): 开口距离

**建议**: 
- 范围 0-119 看起来像是**角度或扩展的百分比**
- 建议使用 `_deg` (度数) 或 `_pct` (百分比)
- 需要查看数据集文档或询问数据提供方确认

---

## 📐 最终维度统计

| 版本 | 修改前 | 修改后 | 移除 | 说明 |
|------|--------|--------|------|------|
| default_version | 41维 | 34维 | 7维 | 移除robot position/orientation |
| gt01_no_depth | 41维 | 34维 | 7维 | 同上 |
| gt02_new_version | 20维 | 8维 | 12维 | 移除常量/NaN关节，只保留joint_5-10 |

---

## ⚠️ 严重问题

### GT02 的 robot_joint_4 是 NaN

```
robot_joint_4: min=nan, max=nan, mean=nan, std=nan, unique=1
```

这是**数据损坏**的标志，必须移除此维度。

---

## 📝 建议

1. **立即修正**: 移除所有无效维度
2. **单位确认**: 向数据提供方确认 effector/gripper 的单位
3. **数据验证**: GT02 数据质量较差，建议确认是否是数据采集问题
4. **文档更新**: 更新配置文件并添加注释说明移除的字段

---

## 总结

| 问题类型 | 影响 | 修正方案 |
|---------|------|----------|
| 全零字段 | default/gt01: robot position (3维) | ❌ 移除 |
| 常量字段 | default/gt01: robot orientation (4维) | ❌ 移除 |
| 常量字段 | gt02: 12个关节 | ❌ 移除 |
| NaN字段 | gt02: robot_joint_4 | ❌ 移除 |
| 缺少单位 | 所有有效字段 | ✅ 添加_rad/_m/_pct |

**配置质量**: 
- 修正前: ⚠️ 严重问题（包含大量无效数据）
- 修正后: 🟢 优秀（只保留有效数据+正确单位）


