# Dataset Schema Discovery 工具集

自动发现数据集的实际数据结构（schema），并与converter配置文件对比，诊断配置问题。

## 📋 功能

### 核心功能
1. **自动Schema发现**: 分析H5、JSON、MCAP、BSON、视频等多种格式
2. **数据库集成**: 从数据库批量查询和采样数据集
3. **配置诊断**: 对比发现的schema与converter config，识别配置错误
4. **批量处理**: 支持优先级device_model的批量分析
5. **详细报告**: 生成JSON格式的schema、诊断和总体报告

### 支持的数据格式
- ✅ H5/HDF5文件
- ✅ JSON文件
- ✅ MCAP文件（ROS2）
- ✅ BSON文件（MMK2）
- ✅ 视频文件（MP4, AVI, MOV等）
- ⚠️  Rosbag（待实现）

---

## 🚀 快速开始

### 方式1: 批量分析（推荐）

批量分析优先级device_model的数据集：

```bash
python batch_schema_discovery.py \
    --database /path/to/database.db \
    --config-dir /path/to/converter/configs \
    --output-dir ./outputs/schema_discovery \
    --num-samples 5 \
    --num-episodes 5
```

**参数说明**:
- `--database`: 数据库路径
- `--config-dir`: Converter配置文件目录（通常是 `scripts/format_converters/tolerobot/configs/`）
- `--output-dir`: 输出目录（会自动创建）
- `--num-samples`: 每个device_model采样多少个数据集（默认5）
- `--num-episodes`: 每个数据集采样多少个episodes（默认5）
- `--verbose`, `-v`: 详细输出（可选）

**输出**:
```
outputs/schema_discovery/
├── schemas/                    # 发现的schema文件
│   ├── mmk2_dataset1_schema.json
│   ├── yinhe_dataset2_schema.json
│   └── ...
├── diagnoses/                  # 诊断结果
│   ├── mmk2_dataset1_diagnosis.json
│   ├── yinhe_dataset2_diagnosis.json
│   └── ...
└── overall_report.json         # 总体报告
```

### 方式2: 分析单个数据集

```bash
python dataset_schema_discoverer.py \
    /path/to/dataset \
    --device-model mmk2 \
    --num-episodes 5 \
    --output discovered_schema.json
```

### 方式3: 对比Schema和Config

如果已经有了discovered schema文件：

```bash
python schema_config_comparator.py \
    discovered_schema.json \
    converter_config.yaml \
    --output diagnosis.json
```

---

## 📂 工具模块

### 1. 基础Schema发现器

#### H5 Schema Discoverer
```bash
# 分析单个H5文件
python h5_schema_discoverer.py /path/to/file.h5

# 分析整个数据集
python h5_schema_discoverer.py /path/to/dataset/
```

#### JSON Schema Discoverer
```bash
python json_schema_discoverer.py /path/to/file.json
```

#### MCAP Schema Discoverer
```bash
python mcap_schema_discoverer.py /path/to/file.mcap
```

#### MMK2 BSON Schema Discoverer
```bash
python mmk2_schema_discoverer.py /path/to/file.bson
```

#### Video Metadata Extractor
```bash
python video_metadata_extractor.py /path/to/video.mp4
```

### 2. 数据库查询工具

```bash
# 列出所有device_model
python database_query_tool.py --database /path/to/db.db --action list

# 查询特定device_model的数据集
python database_query_tool.py --database /path/to/db.db --action query --device-model mmk2

# 采样数据集
python database_query_tool.py --database /path/to/db.db --action sample --device-model mmk2 --num-samples 5
```

---

## 📊 输出格式

### Schema文件格式

```json
{
  "dataset_path": "/path/to/dataset",
  "device_model": "mmk2",
  "detected_formats": ["h5", "video"],
  "data_formats": {
    "h5": {
      "total_h5_files": 100,
      "sampled_files": 5,
      "structure": {
        "observations": {
          "type": "group",
          "children": {
            "qpos": {
              "type": "dataset",
              "dtype": "float64",
              "shape": [107, 14],
              "statistics": {...}
            }
          }
        }
      },
      "consistency": "consistent"
    },
    "video": {
      "total_video_files": 300,
      "camera_groups": {
        "cam_high": {
          "total_files": 100,
          "sampled_files": 5,
          "metadata_samples": [...]
        }
      }
    }
  },
  "summary": {...}
}
```

### Diagnosis文件格式

```json
{
  "dataset_path": "/path/to/dataset",
  "device_model": "mmk2",
  "severity": "error",  // ok, warning, error
  "issues": [
    {
      "category": "observation_state",
      "field": "qpos",
      "message": "配置的H5路径不存在: observations/qpos",
      "severity": "error",
      "suggestion": "实际存在的H5字段: ['observation/qpos', 'action/qpos']"
    }
  ],
  "warnings": [...],
  "suggestions": [...]
}
```

---

## 🔍 诊断问题类型

Schema vs Config对比会检测以下问题：

### 错误（Errors）
1. **缺少device_model_annotation.yaml**: 数据集目录缺少必需的标注文件
2. **配置字段不存在**: Config中配置的H5路径/MCAP topic在实际数据中不存在
3. **相机配置错误**: Config中配置的相机在实际视频数据中不存在
4. **数据类型不匹配**: 字段的数据类型与预期不符

### 警告（Warnings）
1. **未配置的字段**: 实际数据中存在但config未配置的字段
2. **Schema不一致**: 不同episodes之间的数据结构不一致
3. **相机缺失**: 实际数据中有相机但config未配置

---

## 🛠️ 典型工作流程

### 阶段1: 批量Schema Discovery（2天）

```bash
# 1. 运行批量分析
python batch_schema_discovery.py \
    --database /mnt/nas/synnas/database/robocoin.db \
    --config-dir /path/to/robocoin-dataset/scripts/format_converters/tolerobot/configs \
    --output-dir ./outputs/schema_discovery_$(date +%Y%m%d) \
    --num-samples 5 \
    --num-episodes 5 \
    --verbose

# 2. 查看总体报告
cat ./outputs/schema_discovery_*/overall_report.json | jq '.summary'

# 3. 查看特定device_model的诊断
ls ./outputs/schema_discovery_*/diagnoses/mmk2_*
```

### 阶段2: 分析诊断结果（1天）

```bash
# 统计每个device_model的错误数量
for model in mmk2 yinhe realman agilex leju ruantong zhipingfang galaxea; do
    echo "=== $model ==="
    grep -l "\"severity\": \"error\"" outputs/schema_discovery_*/diagnoses/${model}_* | wc -l
done

# 查看具体的错误类型
jq '.issues[] | .category' outputs/schema_discovery_*/diagnoses/*.json | sort | uniq -c
```

### 阶段3: 修复配置文件（2天）

基于诊断结果，手动或半自动修复converter config文件。

### 阶段4: 验证修复（半天）

重新运行schema discovery，验证修复结果：

```bash
# 只分析之前有错误的数据集
python dataset_schema_discoverer.py /path/to/fixed/dataset \
    --device-model mmk2 \
    --output fixed_schema.json

python schema_config_comparator.py \
    fixed_schema.json \
    fixed_config.yaml
```

---

## 📝 注意事项

### 性能优化
- **采样数量**: 默认每个device_model采样5个数据集，每个数据集5个episodes
  - 如果数据集很一致，可以减少采样
  - 如果数据集差异大，建议增加采样
- **并行处理**: 当前是串行处理，如果需要加速可以并行化

### 依赖项
确保已安装：
```bash
pip install h5py pyyaml sqlalchemy mcap pymongo opencv-python
```

### 存储路径
- 确保数据库中的 `dataset_path` 字段指向正确的NAS路径
- 如果路径不存在，会跳过该数据集

---

## 🐛 故障排除

### 问题1: 找不到数据集
```
WARNING - 未找到device_model为 xxx 的数据集
```
**解决**: 检查数据库中是否有该device_model的`DmvAnnotationDB`记录

### 问题2: H5分析失败
```
ERROR - H5分析失败: No H5 files found
```
**解决**: 
- 检查数据集路径是否正确
- 确认是否真的是H5格式（可能是其他格式如MCAP、BSON）

### 问题3: 内存不足
**解决**: 减少`--num-samples`和`--num-episodes`参数

---

## 📞 联系

如有问题，请查看:
- 主项目文档: `docs/COMPLETE_REFACTORING_PLAN.md`
- 实施计划: `docs/IMPLEMENTATION_PLAN.md`

---

**开发时间**: 2025-10-21  
**状态**: 实施中

