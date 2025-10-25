# Schema Discovery 工具开发总结

**完成时间**: 2025-10-21  
**开发状态**: ✅ **完成并可用**

---

## 🎉 交付成果

### 工具集概览

已完整实现**批量Schema Discovery工具集**，位于 `scripts/dataset_schema_discovery/` 目录：

```
scripts/dataset_schema_discovery/
├── h5_schema_discoverer.py            # H5文件schema发现
├── json_schema_discoverer.py          # JSON文件schema发现
├── mcap_schema_discoverer.py          # MCAP文件schema发现
├── mmk2_schema_discoverer.py          # MMK2 BSON schema发现
├── video_metadata_extractor.py        # 视频元数据提取
├── dataset_schema_discoverer.py       # 统一数据集schema发现
├── database_query_tool.py             # 数据库查询工具
├── schema_config_comparator.py        # Schema vs Config对比
├── batch_schema_discovery.py          # 批量分析主程序 ⭐
├── test_schema_tools.py               # 工具测试脚本
├── run_batch_discovery.sh             # 快速启动脚本 ⭐
└── README.md                          # 完整使用文档 ⭐
```

### 核心能力

1. **全格式支持**: H5、JSON、MCAP、BSON、视频
2. **自动检测**: 智能识别数据集格式
3. **配置诊断**: 对比schema与converter config，识别配置错误
4. **批量处理**: 从数据库批量查询和分析
5. **详细报告**: JSON格式的schema、诊断和总体报告

---

## 📋 使用方式

### 快速开始（3步）

#### 1. 准备环境

```bash
cd /home/liu/program/robocoin-dataset

# 安装依赖（如果还没有）
pip install -e .  # 或 uv pip install -e .

# 验证安装
python -c "import h5py, yaml, sqlalchemy; print('✓ OK')"
```

#### 2. 配置路径

编辑 `scripts/dataset_schema_discovery/run_batch_discovery.sh`，设置数据库路径：

```bash
DATABASE_PATH="/mnt/nas/synnas/database/robocoin.db"  # 修改为实际路径
```

#### 3. 运行批量分析

```bash
cd scripts/dataset_schema_discovery
./run_batch_discovery.sh 5 5
```

参数含义：
- 第1个`5`: 每个device_model采样5个数据集
- 第2个`5`: 每个数据集采样5个episodes

**预计运行时间**: 10-20分钟（取决于数据集大小和网络速度）

---

## 📊 输出结果

运行完成后，会在 `outputs/schema_discovery_TIMESTAMP/` 生成：

```
outputs/schema_discovery_20251021_143000/
├── schemas/                           # 发现的schema（JSON）
│   ├── mmk2_dataset1_schema.json
│   ├── yinhe_dataset2_schema.json
│   └── ... (~40个文件)
├── diagnoses/                         # 诊断结果（JSON）
│   ├── mmk2_dataset1_diagnosis.json
│   ├── yinhe_dataset2_diagnosis.json
│   └── ... (~40个文件)
├── overall_report.json                # 总体报告 ⭐
└── execution.log                      # 执行日志
```

### 查看结果

```bash
# 1. 查看总体摘要
cat outputs/schema_discovery_*/overall_report.json | jq '.summary'

# 输出示例:
# {
#   "total_models_analyzed": 8,
#   "total_datasets_analyzed": 38,
#   "total_errors": 42,
#   "total_warnings": 15
# }

# 2. 查看每个device_model的情况
cat outputs/schema_discovery_*/overall_report.json | jq '.models_analysis'

# 3. 统计每个model的错误数
for model in mmk2 yinhe realman agilex leju ruantong zhipingfang galaxea; do
    echo "=== $model ==="
    grep -c '"severity": "error"' outputs/schema_discovery_*/diagnoses/${model}_* 2>/dev/null || echo "0"
done

# 4. 查看具体错误类型
jq -r '.issues[]? | .category' outputs/schema_discovery_*/diagnoses/*.json | \
    sort | uniq -c | sort -rn
```

---

## 🔍 诊断结果示例

### Schema文件格式

```json
{
  "dataset_path": "/mnt/nas/synnas/.../算法采集_PCB",
  "device_model": "zhipingfang",
  "detected_formats": ["h5", "video"],
  "data_formats": {
    "h5": {
      "total_h5_files": 100,
      "structure": {
        "observations": {
          "qpos": {"type": "dataset", "shape": [107, 14], "dtype": "float64"},
          "qvel": {"type": "dataset", "shape": [107, 14], "dtype": "float64"}
        },
        "action": {"type": "dataset", "shape": [107, 14], "dtype": "float64"}
      }
    },
    "video": {
      "camera_groups": {
        "cam_high": {"total_files": 100, "width": 1920, "height": 1080, "fps": 30}
      }
    }
  }
}
```

### Diagnosis文件格式

```json
{
  "dataset_path": "/mnt/nas/.../算法采集_PCB",
  "device_model": "zhipingfang",
  "severity": "error",
  "issues": [
    {
      "category": "observation_state",
      "field": "qpos",
      "message": "配置的H5路径不存在: observations/qpos",
      "severity": "error",
      "suggestion": "实际路径是: observation/qpos (少了's')"
    },
    {
      "category": "images",
      "message": "配置中的相机在实际数据中不存在: {'cam_left'}",
      "severity": "error",
      "suggestion": "请从config中删除这些相机配置"
    }
  ],
  "warnings": [
    {
      "category": "images",
      "message": "实际数据中存在但config未配置的相机: {'cam_right'}",
      "severity": "warning",
      "suggestion": "考虑添加这些相机到config"
    }
  ]
}
```

---

## 🛠️ 接下来怎么做？

### 阶段1: 分析诊断结果（半天）

1. **查看总体报告**，了解整体情况
2. **识别高频问题**，找出共性错误
3. **按device_model分组**，制定修复优先级

### 阶段2: 修复配置文件（2-3天）

基于诊断结果，修复 `scripts/format_converters/tolerobot/configs/` 下的配置文件：

**优先级**:
1. **P0 - mmk2, yinhe, realman**: 数据量最大或最重要
2. **P1 - agilex, leju, ruantong**: 次优先级
3. **P2 - zhipingfang, galaxea**: 最后处理

**修复类型**:
- ❌ **删除不存在的字段**（会导致KeyError）
- ✅ **修正字段路径**（如 `observations/qpos` → `observation/qpos`）
- ➕ **添加缺失的必需字段**
- 🔧 **调整数据类型或单位转换**

### 阶段3: 验证修复（1天）

对修复过的config重新运行schema discovery验证：

```bash
# 只分析特定device_model
python batch_schema_discovery.py \
    --database /path/to/db \
    --config-dir ./configs \
    --output-dir ./outputs/validation \
    --num-samples 3 \
    --num-episodes 3
```

确保：
- ✅ `severity: "error"` 减少到0或接近0
- ✅ 只剩下合理的`warning`（如可选字段未配置）

### 阶段4: 小规模转换测试（1天）

使用修复后的config进行实际转换测试：

```bash
# 使用测试模式转换几个数据集
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --dataset-path /path/to/test/dataset \
    --output-path ./test_output \
    --test-mode
```

验证：
- ✅ 转换成功完成
- ✅ 数据正确加载
- ✅ 容错机制工作正常

---

## 📈 预期成果

完成Schema Discovery和配置修复后，应该实现：

### 质量目标
- ✅ **配置错误率**: < 5%（目前可能 > 50%）
- ✅ **转换成功率**: > 95%（跳过少量坏数据）
- ✅ **零返工**: 配置问题在转换前全部解决

### 效率提升
- **减少调试时间**: 从"转换失败→查错→修复→重试"变为"预先检测→批量修复"
- **提高转换速度**: 配置正确后，转换可以一次性完成
- **避免数据丢失**: 不会因为配置错误导致大量数据转换失败

---

## 🎯 关键优势

### 相比手动检查配置
| 方面 | 手动方式 | Schema Discovery |
|------|---------|------------------|
| 速度 | 慢（每个数据集10-30分钟） | 快（批量10-20分钟） |
| 准确性 | 容易遗漏 | 自动化，全面检测 |
| 可追溯 | 难以记录 | 完整JSON报告 |
| 可重复 | 依赖人工 | 自动化脚本 |

### 相比直接转换测试
| 方面 | 直接转换 | Schema Discovery |
|------|---------|------------------|
| 发现问题时间 | 转换时（可能数小时后） | 预先（几分钟） |
| 修复成本 | 高（需要重新转换） | 低（预先修复） |
| 批量处理 | 难（需要逐个转换） | 易（批量诊断） |

---

## 📞 文档索引

- **使用文档**: `scripts/dataset_schema_discovery/README.md`
- **实施报告**: `docs/SCHEMA_DISCOVERY_IMPLEMENTATION.md`
- **总体规划**: `docs/COMPLETE_REFACTORING_PLAN.md`
- **实施计划**: `docs/IMPLEMENTATION_PLAN.md`

---

## ✅ 完成检查清单

已完成：
- [x] H5/JSON/MCAP/BSON/视频 schema发现器
- [x] 数据库查询和采样工具
- [x] Schema vs Config对比诊断工具
- [x] 批量分析主程序
- [x] 完整文档和脚本
- [x] 测试脚本

待用户执行：
- [ ] 在实际环境运行批量discovery
- [ ] 分析诊断结果
- [ ] 修复配置文件
- [ ] 验证修复效果

---

## 🚀 现在可以开始了！

所有工具已就绪，只需运行：

```bash
cd /home/liu/program/robocoin-dataset/scripts/dataset_schema_discovery
./run_batch_discovery.sh
```

然后查看 `outputs/schema_discovery_*/overall_report.json` 开始配置修复工作！

---

**工具开发完成，期待在实际数据上的表现！** 🎊

