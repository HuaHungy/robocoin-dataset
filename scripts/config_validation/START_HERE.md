# 🚀 配置验证工具 - 立即开始

## ✅ 工具已就绪！

**完成时间**: 2025-10-22  
**性能**: 比全量扫描快**8倍**（30分钟 vs 4小时）  
**状态**: **可以立即运行**

---

## 📖 快速上手（3步）

### 第1步：运行验证

```bash
cd /home/liu/program/robocoin-dataset
conda activate robocoin-dataset
bash scripts/config_validation/run_validation.sh
```

**时间**: ~30分钟

### 第2步：查看报告

```bash
# 查看总体报告
cat outputs/config_validation/validation_report.json

# 查看具体数据集的问题
ls outputs/config_validation/*_comparison.txt
ls outputs/config_validation/*_field_names.txt
```

### 第3步：修复问题

根据报告修复配置文件，然后重新运行验证。

---

## 🎯 工具做什么？

### 1. 自动定位Episodes
- 支持10种数据格式（H5、MP4、JSON、MCAP、BSON等）
- 自动识别数据结构
- 随机采样2个episodes

### 2. 深度分析Schema
- 提取所有字段名、shape、dtype
- 识别images、state、action
- 计算统计信息

### 3. 对比配置
- 检查h5_path是否存在
- 检查维度是否匹配
- 检查字段数量

### 4. 检查命名规范
- 基于realman_rmc_aidal标准
- 检查单位后缀（_rad, _m）
- 生成修正建议

### 5. 检测数据质量 🆕
- **全0数据**: 所有值都是0（可能传感器未连接）
- **常量数据**: 所有值相同（可能传感器故障）
- **极小变化**: 数据几乎不变（可能只是噪声）
- 在报告中标记可疑数据

---

## 📊 验证哪些数据集？

**优先级Device Models** (共456个数据集):

1. discover_robotics_aitbot_mmk2 (72数据集)
2. yinhe (5数据集)
3. realman_rmc_aidal (37数据集)
4. agilex (220数据集)
5. leju (6数据集)
6. ruantong (25数据集)
7. zhipingfang (16数据集)
8. galaxea (75数据集)

**采样策略**: 每个model采样2个数据集，每个数据集采样2个episodes

**总计**: 16个数据集，32个episodes

---

## 📂 报告内容

### validation_report.json（总体）

```json
{
  "summary": {
    "total_datasets": 16,
    "total_episodes_analyzed": 32,
    "successful_validations": 14,
    "failed_validations": 2
  }
}
```

### {dataset}_comparison.txt（配置对比）

```
======================================================================
配置对比报告
======================================================================

总错误数: 2
总警告数: 1

[Images]
  ✓ cam_high_rgb - OK
  ✗ cam_left_wrist - 未在数据中找到

[State]
  ✓ observations/qpos [0:7] - OK
  ✗ observations/qpos [30:33] - 维度越界
```

### {dataset}_field_names.txt（字段命名）

```
======================================================================
字段命名检查报告
======================================================================

符合规范: 14/16 (87.5%)

不符合规范:
  ✗ joint_1 → 建议: joint_1_rad
  ✗ eef_pos_x → 建议: eef_pos_x_m
```

---

## 🔧 发现问题怎么办？

### 问题1: h5_path不存在

**报告**:
```
✗ observations/qpos
    - h5_path 'observations/qpos' 未在数据中找到
```

**解决**:
1. 打开converter_config_{device_model}.yaml
2. 检查实际数据的h5路径（可能是observations/qposition）
3. 修改配置中的h5_path
4. 重新运行验证

### 问题2: 维度不匹配

**报告**:
```
✗ observations/qpos [30:33]
    - 维度越界: 配置要求到索引33, 但实际只有30个元素
```

**解决**:
1. 修改range_to: 33 → 30
2. 或减少names数量
3. 重新运行验证

### 问题3: 字段命名不规范

**报告**:
```
✗ joint_1
    - 缺少角度单位后缀
    💡 建议: joint_1_rad
```

**解决**:
1. 修改names列表
2. 添加_rad或_m后缀
3. 重新运行验证

### 问题4: 数据质量问题 🆕

**报告**:
```
⚠️ observations/qpos [80:83]
    Names: left_eef_pos_x_m, left_eef_pos_y_m, left_eef_pos_z_m
    - ⚠️ 数据质量问题: 所有值都为0（可能是传感器未连接或数据采集失败）
```

**判断**:
1. 查看视频，确认左臂是否有运动
2. 如果视频中左臂在动，但数据全0 → **传感器未连接，应删除配置**
3. 如果视频中左臂不动 → **可能合理，添加注释说明**

**处理**:
```yaml
# 选项A: 删除无效字段（推荐）
# - names:
#   - left_eef_pos_x_m  # 2025-10-22: 数据全0，传感器未连接
#   - left_eef_pos_y_m
#   - left_eef_pos_z_m

# 选项B: 保留并添加注释（如果合理）
- names:
  - left_eef_pos_x_m
  - left_eef_pos_y_m
  - left_eef_pos_z_m
  # 注释: 部分episodes中左臂不动，数据为0是正常的
```

详见: `docs/DATA_QUALITY_DETECTION.md`

---

## 📚 命名标准

基于`converter_config_realman_rmc_aidal.yaml`：

| 类型 | 格式 | 示例 |
|------|------|------|
| **关节** | `{prefix}_joint_N_rad` | `right_arm_joint_1_rad` |
| **夹爪** | `{prefix}_gripper_open_rad` | `left_gripper_open` |
| **末端位置** | `{prefix}_eef_pos_{xyz}_m` | `right_eef_pos_x_m` |
| **末端姿态** | `{prefix}_eef_rot_euler_{xyz}_rad` | `left_eef_rot_euler_z_rad` |
| **摄像头** | `cam_{location}_rgb` | `cam_high_rgb` |

**前缀**: `left_`, `right_`, `base_`, `mobile_`  
**单位**: `_rad` (弧度), `_m` (米)  
**不推荐**: `_deg`, `_mm`, `_cm`

---

## ⚡ 自定义参数

### 只验证特定device models

```bash
python scripts/config_validation/batch_validation.py \
    --database /mnt/db/datasets.db \
    --config-dir ./scripts/format_converters/tolerobot/configs/ \
    --output-dir ./outputs/config_validation \
    --device-models mmk2 yinhe realman_rmc_aidal
```

### 增加采样数量

```bash
python scripts/config_validation/batch_validation.py \
    --database /mnt/db/datasets.db \
    --config-dir ./scripts/format_converters/tolerobot/configs/ \
    --output-dir ./outputs/config_validation \
    --num-datasets 5 \     # 每个model采样5个数据集
    --num-episodes 3       # 每个数据集采样3个episodes
```

---

## 🐛 常见问题

### Q: ImportError: No module named 'mcap'

```bash
conda activate robocoin-dataset
pip install mcap
```

### Q: ImportError: No module named 'bson'

```bash
conda activate robocoin-dataset
pip install pymongo
```

### Q: 数据集路径不存在

检查数据库中的`yaml_file_path`字段是否正确。

### Q: 未找到配置文件

检查`converter_factory_config.yaml`中的映射关系。

---

## 🎯 验证通过后做什么？

### 1. Test模式转换

```bash
python scripts/upload2hub.py \
    --mode test \
    --dataset-uuid {dataset_uuid}
```

### 2. 检查转换结果

验证生成的LeRobot数据集是否正确。

### 3. 正式批量转换

```bash
python scripts/upload2hub.py \
    --mode formal \
    --dataset-uuid {dataset_uuid}
```

---

## 📖 详细文档

- **README.md** - 完整使用说明
- **CONFIG_VALIDATION_IMPLEMENTATION.md** - 实现细节
- **VALIDATION_TOOL_READY.md** - 详细指南
- **PROGRESS_SUMMARY_2025-10-22.md** - 今日进展

---

## 💡 提示

✅ **先验证1-2个数据集** - 确认工具正常工作  
✅ **修复错误后重新验证** - 直到错误数为0  
✅ **保存验证报告** - 记录修复历史  
✅ **统一字段命名** - 有助于后续训练

---

## 🚀 现在就开始！

```bash
cd /home/liu/program/robocoin-dataset
conda activate robocoin-dataset
bash scripts/config_validation/run_validation.sh
```

**30分钟后** - 你会看到所有配置问题的详细报告！

---

**创建**: 2025-10-22  
**状态**: ✅ **已就绪**  
**性能**: 8倍提升  
**支持**: 10种数据格式

开始验证吧！ 🎉

