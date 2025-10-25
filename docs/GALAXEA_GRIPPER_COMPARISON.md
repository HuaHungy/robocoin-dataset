# Galaxea R1 Lite - Gripper单位对比分析

## 📅 分析日期
2025-10-22

---

## 🔍 两个版本的Gripper数据对比

### Version 1: rosbag (default_version)

**数据源**: ROS bag文件  
**示例**: `RB250527007_20250717112739604_RAW.bag`

**Gripper数据**:
```
/hdas/feedback_gripper_left:
  position[0] = 97.881347

/hdas/feedback_gripper_right:
  position[0] = 97.341041

/motion_target/target_position_gripper_left:
  position[0] = 100.000000

/motion_target/target_position_gripper_right:
  position[0] = 100.000000
```

**值范围**: **97-100**

---

### Version 2: h5_mp4_version

**数据源**: HDF5文件  
**示例**: `865/865.hdf5`

**Gripper数据** (从qpos中提取):
```
qpos[6]  (左夹爪):  2.853 ~ 95.172
qpos[13] (右夹爪):  2.331 ~ 95.329
```

**值范围**: **2-95**

---

## 🧐 对比分析

### 相同点
1. ✅ **都不是弧度单位**（rad范围应该是0-6.28）
2. ✅ **都在0-100范围内**
3. ✅ **配置都错误地使用了`_rad`后缀**

### 不同点

| 属性 | rosbag版本 | h5_mp4版本 |
|------|-----------|-----------|
| 值范围 | 97-100 | 2-95 |
| 数据来源 | ROS topic | HDF5 qpos |
| 采样状态 | 可能接近关闭 | 包含开合过程 |

---

## 💡 单位推断

### 可能性1: 百分比（Percentage）✅ 最可能

**证据**:
- rosbag版本：97-100% → 几乎关闭
- h5_mp4版本：2-95% → 从开到接近关闭的过程
- 范围0-100符合百分比定义

**语义**:
- 100% = 完全关闭（夹紧）
- 0% = 完全打开

**支持度**: ⭐⭐⭐⭐⭐

---

### 可能性2: 角度（Degree）❌ 不太可能

**为什么不太可能**:
- 夹爪通常开合角度不会到90度
- 如果是角度，rosbag版本的97-100度意味着几乎垂直，不合理
- h5_mp4版本的2-95度范围太大

**支持度**: ⭐

---

### 可能性3: 距离（毫米 mm）⚠️ 有可能

**可能的解释**:
- rosbag版本：两指间距约97-100mm（几乎关闭）
- h5_mp4版本：2-95mm（从2mm到95mm）

**问题**:
- 需要确认gripper的最大开合距离是否约为100mm
- 如果夹爪是小型夹爪，100mm可能太大

**支持度**: ⭐⭐

---

### 可能性4: 编码器值/归一化值 ❌ 不太可能

**为什么不太可能**:
- 如果是编码器值，通常会是更大的数字或负数
- 归一化值通常是0-1或-1到1

**支持度**: ⭐

---

## 🎯 结论和建议

### ✅ 确认的单位: **角度（Degree）**

**理由（2025-10-22用户确认）**:
1. 两个版本的值范围都在0-100内实际上是**度数（degree）**
2. rosbag版本97-100度表示"几乎关闭"的状态
3. h5_mp4版本2-95度表示"从开到接近关闭"的动作
4. 需要使用`degree2rad`转换函数转换为弧度

### 语义定义
```
100度 ≈ 1.745 rad = 接近完全关闭/夹紧
0度 = 0 rad = 完全打开
```

---

## 📝 配置文件修正

### 当前配置（错误）

**rosbag版本**:
```yaml
# converter_config_galaxea_r1_lite.yaml
- names: 
  - left_gripper_open_rad   # ❌ 错误：不是rad
  args:
    topic_name: /hdas/feedback_gripper_left
    range_from: 0
    range_to: 1
```

**h5_mp4版本**: （假设有类似配置）
```yaml
# 假设的配置
- names:
  - left_gripper_open_rad   # ❌ 错误：不是rad
  args:
    h5_path: qpos
    range_from: 6
    range_to: 7
```

### ✅ 修正后配置（已应用）

**使用degree2rad转换函数**
```yaml
# rosbag版本（converter_config_galaxea_r1_lite.yaml）
- names: 
  - left_gripper_open_rad   # ✅ 保持_rad后缀（因为会转换）
  args:
    topic_name: /hdas/feedback_gripper_left
    range_from: 0
    range_to: 1
  convert_func: degree2rad   # ✅ 添加转换函数

# h5_mp4版本（converter_config_galaxea_r1_lite_h5_mp4.yaml）
- names:
  - left_gripper_open_rad
  args:
    h5_path: qpos
    range_from: 6
    range_to: 7
  convert_func: degree2rad   # ✅ 添加转换函数
```

**转换效果**:
```python
# 原始值（degree） → 转换后（rad）
2度  → 0.035 rad
50度 → 0.873 rad
95度 → 1.658 rad
100度 → 1.745 rad
```

---

## ✅ 修正完成的文件（2025-10-22）

### 1. rosbag版本
- [x] `converter_config_galaxea_r1_lite.yaml`
  - ✅ 添加`convert_func: degree2rad`到left/right gripper observation
  - ✅ 添加`convert_func: degree2rad`到left/right gripper action
  - ✅ 字段保持`_rad`后缀（因为会转换为rad）

### 2. h5_mp4版本
- [x] `converter_config_galaxea_r1_lite_h5_mp4.yaml`
  - ✅ 添加`convert_func: degree2rad`到left/right gripper observation
  - ✅ 添加`convert_func: degree2rad`到left/right gripper action
  - ✅ 字段保持`_rad`后缀（因为会转换为rad）

### 3. 文档更新
- [x] `GALAXEA_GRIPPER_COMPARISON.md` - 更新单位确认为degree
- [ ] `GALAXEA_R1_LITE_DATA_ISSUES.md` - 更新单位确认
- [ ] `H5_MP4_DATA_ISSUES.md` - 更新gripper问题

---

## 📊 数据验证

为了进一步确认，建议：

### 1. 检查更多样本
```bash
# 检查多个episode的gripper值范围
for file in data/galaxea_r1_lite:h5_mp4_version/*/\*.hdf5; do
  python -c "import h5py; f=h5py.File('$file', 'r'); print(f'$file: {f[\"qpos\"][:, 6].min():.1f}-{f[\"qpos\"][:, 6].max():.1f}')"
done
```

### 2. 对比开合状态
- [ ] 找一个完全打开的episode，检查gripper值是否接近0
- [ ] 找一个完全关闭的episode，检查gripper值是否接近100
- [ ] 验证中间状态的值是否在合理范围

### 3. 查看机器人文档
- [ ] 查看Galaxea R1 Lite的官方文档
- [ ] 确认gripper的控制接口定义
- [ ] 确认gripper的物理规格（最大开合距离/角度）

---

## ⚠️ 警告

### 对训练的影响

**如果不修正**:
1. 字段命名误导（声称是rad实际是pct）
2. 数据归一化可能不正确
3. 训练时可能与其他rad数据混淆

**修正后**:
1. ✅ 字段命名准确
2. ✅ 单位语义清晰
3. ✅ 可以在训练时对不同单位的数据做不同的归一化处理

---

## 🔗 相关文档

- Galaxea rosbag数据问题: `docs/GALAXEA_R1_LITE_DATA_ISSUES.md`
- Galaxea配置分析: `docs/GALAXEA_R1_LITE_CONFIG_ANALYSIS.md`
- H5+MP4数据问题: `docs/H5_MP4_DATA_ISSUES.md`
- Agilex配置: `scripts/format_converters/tolerobot/configs/converter_config_agilex_cobot_decoupled_magic_h5_mp4.yaml`

---

## 📞 待确认问题

1. **gripper的100%对应的物理状态是什么？**
   - [ ] 完全关闭（夹紧）
   - [ ] 完全打开
   - [ ] 其他状态

2. **gripper的物理规格**
   - [ ] 最大开合距离（mm）
   - [ ] 最大开合角度（degree）
   - [ ] 控制接口文档

3. **是否需要转换为统一单位（rad）？**
   - [ ] 保持原始单位（pct）
   - [ ] 转换为rad（需要转换公式）
   - [ ] 转换为m（如果是距离）

---

## ✅ 下一步行动

1. **立即**: 修改配置文件中的字段后缀 `_rad` → `_pct`
2. **短期**: 验证更多样本数据确认单位
3. **中期**: 决定是否需要单位转换
4. **长期**: 在schema_analyzer中自动检测单位不匹配问题

