# H5+MP4数据集 - 数据质量问题报告

## 📅 分析日期
2025-10-22

---

## 🔍 分析的数据集

### 1. Agilex h5_mp4 
**文件**: `data/agilex_cobot_decoupled_magic:h5_mp4/打开台灯_蓝咖餐布_69/data.hdf5`

### 2. Galaxea h5_mp4_version
**文件**: `data/galaxea_r1_lite:h5_mp4_version/865/865.hdf5`

---

## 🚨 发现的严重问题

### 问题1: Agilex h5_mp4 - 右臂数据异常

**期望**: 14维（左臂6关节+夹爪 + 右臂6关节+夹爪）

**实际情况**:
```
✅ [0-6]  左臂6关节+夹爪：有效数据
❌ [7-9]  右臂前3个关节：常量（无变化）
❌ [10]   右臂第4关节：全0
⚠️  [11]   右臂第5关节：几乎常量（0.212-0.213）
❌ [12-13] 右臂第6关节+夹爪：常量

详细数据：
  [0] min=0.012, max=0.458, std=0.205  ✅
  [1] min=0.003, max=1.929, std=0.803  ✅
  [2] min=-1.258, max=0.010, std=0.544  ✅
  [3] min=-0.147, max=0.104, std=0.063  ✅
  [4] min=0.012, max=0.687, std=0.183  ✅
  [5] min=-0.269, max=0.937, std=0.279  ✅
  [6] min=0.003, max=0.024, std=0.009  ✅ (gripper)
  
  [7]  min=0.007, max=0.007, std=0.000  ❌ 常量
  [8]  min=-0.003, max=-0.003, std=0.000  ❌ 常量
  [9]  min=0.007, max=0.007, std=0.000  ❌ 常量
  [10] min=0.000, max=0.000, std=0.000  ❌ 全0
  [11] min=0.212, max=0.213, std=0.000075  ⚠️ 几乎常量
  [12] min=0.059, max=0.059, std=0.000  ❌ 常量
  [13] min=0.002, max=0.002, std=0.000  ❌ 常量
```

**结论**: 
- ✅ **只有左臂（[0-6]）是有效数据**
- ❌ **右臂数据（[7-13]）全部无效**（常量或全0）
- ⚠️ **这个数据集可能只采集了左臂的动作**

**配置修正建议**:
```yaml
# 当前配置：期望14维
# 建议修改：只使用前7维（左臂）

state:
  sub_state:
    # 只保留左臂（0:7）
    - names:
        - left_arm_joint_1_rad
        - left_arm_joint_2_rad
        - left_arm_joint_3_rad
        - left_arm_joint_4_rad
        - left_arm_joint_5_rad
        - left_arm_joint_6_rad
        - left_gripper_open_rad
      args:
        h5_path: qpos
        range_from: 0
        range_to: 7
    
    # 右臂数据无效，建议移除或标记为可选
```

---

### 问题2: Galaxea h5_mp4_version - Gripper单位错误

**期望**: 所有数据都是弧度（rad）

**实际情况**:
```
✅ [0-5]  左臂6关节：弧度 ✅
❌ [6]    左夹爪：2.853-95.172 (不是弧度！)
✅ [7-12] 右臂6关节：弧度 ✅
❌ [13]   右夹爪：2.331-95.329 (不是弧度！)

详细数据：
  [0]  min=-0.869, max=1.014  ✅ rad
  [1]  min=-0.000, max=2.376  ✅ rad
  [2]  min=-1.987, max=0.000  ✅ rad
  [3]  min=-0.758, max=0.037  ✅ rad
  [4]  min=-0.589, max=0.459  ✅ rad
  [5]  min=-0.331, max=0.263  ✅ rad
  [6]  min=2.853, max=95.172  ❌ 不是rad！
  [7]  min=-0.635, max=0.663  ✅ rad
  [8]  min=-0.000, max=1.908  ✅ rad
  [9]  min=-1.338, max=0.000  ✅ rad
  [10] min=-0.988, max=0.000  ✅ rad
  [11] min=-0.374, max=0.383  ✅ rad
  [12] min=-0.405, max=0.083  ✅ rad
  [13] min=2.331, max=95.329  ❌ 不是rad！
```

**结论**:
- ✅ 关节角度：都是弧度
- ❌ **夹爪（[6], [13]）：值范围2-95，可能是百分比或角度**
- 🔗 **与Galaxea rosbag版本的问题一致**

**配置修正建议**:
```yaml
# 需要确认gripper的实际单位
# 可能的单位：
# - 百分比（0-100%）
# - 角度（degree，0-90度）
# - 编码器值

# 修正字段名：
- left_gripper_open_rad   # ❌ 错误
+ left_gripper_open_pct   # 或 _deg, 待确认
```

---

## 📊 数据集对比

| 数据集 | 左臂关节 | 左夹爪 | 右臂关节 | 右夹爪 | 总维度 |
|--------|---------|--------|---------|--------|--------|
| Agilex h5_mp4 | ✅ 有效 | ✅ 有效(rad) | ❌ 常量 | ❌ 常量 | 7/14有效 |
| Galaxea h5_mp4_version | ✅ 有效 | ❌ 非rad | ✅ 有效 | ❌ 非rad | 14/14有数据 |

---

## 🎯 修正优先级

### 🔴 Critical - Galaxea Gripper单位

**问题**: Gripper值2-95，不是弧度

**影响**: 
- 字段命名错误（`_rad`后缀不正确）
- 可能影响训练（单位不统一）

**需要**: 
1. 确认gripper实际单位（百分比？角度？）
2. 修改配置文件字段后缀
3. 如需要，添加单位转换

### 🟡 High - Agilex h5_mp4右臂数据

**问题**: 右臂数据全是常量或全0

**影响**:
- 转换时会产生无用的常量数据
- 可能误导训练

**建议**:
1. 检查是否所有episode都是这样
2. 如果是，修改配置只使用左臂（0:7）
3. 或标记为单臂数据集

---

## 🔗 相关问题

### Galaxea rosbag vs h5_mp4

**rosbag版本问题**:
- Gripper: 97-100（不是rad）
- Chassis: position全0
- Torso: 第4关节全0

**h5_mp4版本问题**:
- Gripper: 2-95（不是rad）✅ 一致
- 维度: 14维全部有数据

**结论**: Gripper单位问题在两个版本中都存在，需要统一确认和修正。

---

## 📝 需要确认的问题

### 1. Galaxea Gripper单位（Critical）
**当前值**: 2-95  
**可能的单位**:
- [ ] 百分比（0-100%）
- [ ] 角度（degree）
- [ ] 其他？

### 2. Agilex h5_mp4右臂数据（High）
**问题**: 右臂数据全是常量  
**需要确认**:
- [ ] 所有episode都是这样吗？
- [ ] 这是单臂数据集吗？
- [ ] 配置是否应该只使用左臂？

---

## 📚 相关文档

- Galaxea配置分析: `docs/GALAXEA_R1_LITE_CONFIG_ANALYSIS.md`
- Galaxea数据问题: `docs/GALAXEA_R1_LITE_DATA_ISSUES.md`
- H5+MP4总结: `docs/H5_MP4_DATASETS_SUMMARY.md`
- 今日总结: `docs/SESSION_SUMMARY_20251022.md`

---

## 🔄 下一步行动

1. **立即**: 标记这些问题，继续完成converter优化
2. **短期**: 确认gripper单位和agilex右臂数据
3. **中期**: 修正所有配置文件
4. **长期**: 在schema_analyzer中自动检测这类问题

