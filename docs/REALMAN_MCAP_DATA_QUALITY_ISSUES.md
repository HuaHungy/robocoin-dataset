# Realman MCAP数据质量问题分析

**生成时间**: 2025-10-22  
**Episode**: GroceryStore_Restrocking_Fallen_20251012_104159_192_168_10_124

---

## 1. 数据质量评估总览

| 数据源 | 字段 | 状态 | 问题 | 建议 |
|--------|------|------|------|------|
| Joint States | Position (7维) | ✅ 正常 | 无 | 保持配置 |
| Joint States | Velocity (0维) | ❌ 空数组 | 数据不存在 | 不配置 |
| Joint States | Effort (0维) | ❌ 空数组 | 数据不存在 | 不配置 |
| Right Gripper | Position (1维) | ✅ 正常 | 0-0.832 (正常范围) | 保持配置 |
| Left Gripper | Position (1维) | ⚠️ 常量 | 恒为0.907 | **需要标注** |
| Right EEF | Position (3维) | ✅ 正常 | 无 | 保持配置 |
| Right EEF | Orientation (4维) | ✅ 正常 | 无 | 保持配置 |
| Left EEF | Position (3维) | ✅ 正常 | 无 | 保持配置 |
| Left EEF | Orientation (4维) | ✅ 正常 | 无 | 保持配置 |
| Right Six Force | All (6维) | ✅ 正常 | 100%非零率 | 保持配置 |
| Left Six Force | All (6维) | ✅ 正常 | 100%非零率 | 保持配置 |
| Joint Speed | All | ❌ 无法解析 | rosbags bug | 不配置 |
| Joint Acc | All | ❌ 无法解析 | rosbags bug | 不配置 |

---

## 2. 详细数值分析

### 2.1 Left Arm Joint States (Position)

| 关节 | Min | Max | Mean | Std | 非零率 | 状态 |
|------|-----|-----|------|-----|--------|------|
| joint_1 | -0.1078 | -0.0041 | -0.0535 | 0.0418 | 100% | ✅ |
| joint_2 | -2.1411 | -2.1188 | -2.1281 | 0.0095 | 100% | ✅ |
| joint_3 | -0.1165 | -0.0036 | -0.0588 | 0.0475 | 100% | ✅ |
| joint_4 | 0.0138 | 0.3064 | 0.1960 | 0.1249 | 100% | ✅ |
| joint_5 | 0.3797 | 0.4101 | 0.3947 | 0.0096 | 100% | ✅ |
| joint_6 | 0.0705 | 0.7695 | 0.4364 | 0.2983 | 100% | ✅ |
| joint_7 | -0.4726 | -0.3715 | -0.4407 | 0.0352 | 100% | ✅ |

**单位**: rad (已在消息schema中确认)

### 2.2 Right Arm Joint States (Position)

| 关节 | Min | Max | Mean | Std | 非零率 | 状态 |
|------|-----|-----|------|-----|--------|------|
| joint_1 | 0.0019 | 0.4810 | 0.1289 | 0.1904 | 100% | ✅ |
| joint_2 | 2.0456 | 2.0630 | 2.0590 | 0.0059 | 100% | ✅ |
| joint_3 | 0.1766 | 0.4692 | 0.2348 | 0.1084 | 100% | ✅ |
| joint_4 | -0.0402 | 0.1391 | 0.0191 | 0.0557 | 100% | ✅ |
| joint_5 | 1.4467 | 1.7644 | 1.6042 | 0.0745 | 100% | ✅ |
| joint_6 | -0.3415 | 0.3529 | 0.0937 | 0.2248 | 100% | ✅ |
| joint_7 | -2.9465 | -2.4974 | -2.6868 | 0.1308 | 100% | ✅ |

**单位**: rad (已在消息schema中确认)

### 2.3 Left Gripper Position

```
Min:  0.907
Max:  0.907
Mean: 0.907
Std:  0.000
非零率: 100% (17347/17347)
```

**问题**: ⚠️ **常量值0.907** - 在整个episode中未变化

**可能原因**:
1. 该episode中左臂未被使用
2. 左夹爪保持固定位置
3. 可能是数据采集问题

**建议**:
- 在配置中**添加注释标注此问题**
- 考虑在converter中添加validation检查常量gripper
- 如果多个episode都有此问题，考虑**不使用该字段**

### 2.4 Right Gripper Position

```
Min:  0.000
Max:  0.832
Mean: 0.432
Std:  0.271
非零率: 100% (17201/17201)
```

**状态**: ✅ **正常** - 有明显的开合动作

---

## 3. 配置修正建议

### 3.1 ✅ 已正确配置的字段

以下字段已在配置中，数据质量正常：
- ✅ Right/Left arm joint positions (各7维)
- ✅ Right gripper (1维)
- ✅ Left gripper (1维) - 虽然此episode中是常量
- ✅ Right/Left EEF position (各3维)
- ✅ Right/Left EEF orientation (各4维→转换为3维euler)
- ✅ Right/Left six force (各6维)

### 3.2 ⚠️ 需要标注的问题

**Left Gripper常量问题** - 建议在配置中添加注释：

```yaml
# 在left_gripper_open_rad字段添加注释
- names: 
    - left_gripper_open_rad
  args:
    mcap_topic: /left_arm_controller/rm_driver/gripper_pos
    range_from: 0
    range_to: 1
  # ⚠️ 注意：某些episode中此字段可能为常量（例如GroceryStore_Restrocking_Fallen中恒为0.907）
  # 这表明该episode中左臂未被使用，但字段仍保留以保持数据一致性
```

### 3.3 ❌ 不应配置的字段

以下字段**不应添加到配置**（数据不存在或无法解析）：
- ❌ Joint States velocity - 数据中为空数组
- ❌ Joint States effort - 数据中为空数组
- ❌ Joint speed (`/udp_joint_speed`) - rosbags库反序列化bug
- ❌ Joint acceleration (`/udp_joint_acc`) - rosbags库反序列化bug

---

## 4. Converter实现建议

### 4.1 处理rosbags反序列化bug

Joint States需要**手动CDR解析**以绕过rosbags库bug：

```python
def parse_cdr_joint_state(data):
    """手动解析CDR格式的JointState消息"""
    # 见 scripts/parse_realman_joint_states_manual.py
    # 已验证可以正确解析position字段
```

### 4.2 添加数据验证

建议在converter中添加：

```python
def _validate_gripper_data(self, gripper_values):
    """检测gripper是否为常量（未使用）"""
    if np.std(gripper_values) < 1e-6:
        logger.warning(f"Gripper appears to be constant: {gripper_values[0]:.3f}")
```

---

## 5. 对比其他Episode

**重要**: 需要检查其他episode是否也有类似问题：

1. **Left gripper常量** - 是个别episode还是普遍问题？
2. **Joint velocity/effort空** - 是否所有episode都没有这些数据？
3. **Joint speed/acc无法解析** - 是否所有episode都有此问题？

**建议**: 分析至少3-5个不同的episodes以确认数据质量问题的普遍性。

---

## 6. 最终结论

### 数据质量评分

| 类别 | 评分 | 说明 |
|------|------|------|
| 关节位置 | ✅ 优秀 | 7×2=14维，全部正常 |
| 夹爪 | ⚠️ 良好 | 右臂正常，左臂某些episode为常量 |
| 末端执行器 | ✅ 优秀 | 6×2=12维，全部正常 |
| 六维力 | ✅ 优秀 | 6×2=12维，全部正常 |
| 速度/加速度 | ❌ 缺失 | 数据不存在或无法解析 |

**总体评分**: ✅ **良好** (核心数据完整，但缺少速度/加速度信息)

### 配置完整性

- **Observation State**: 38维 (26基础 + 12六维力) ✅
- **Action**: 26维 (不含六维力) ✅
- **Images**: 3个相机 ✅

**配置完整性**: ✅ **已完成**

---

**报告生成完毕** ✅

