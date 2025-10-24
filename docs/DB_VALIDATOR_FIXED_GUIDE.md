# 数据库集成配置验证器 - 修正版使用指南

> ✅ 状态: 已修正，基于实际数据库结构  
> 📅 更新时间: 2025-10-24

---

## 问题说明

### 之前的错误假设 ❌

之前创建的 `db_integrated_validator.py` 和 `db_integrated_validator_parallel.py` 假设数据库包含：
- `dataset_path` (文件系统路径)
- `converter_config_path` (配置文件路径)  
- `converter_module` (converter模块)
- `converter_class` (converter类名)
- `repo_id` (Hugging Face仓库ID)

**但实际数据库并不包含这些字段！**

### 实际数据库结构 ✅

`device_model_annotation` 表实际包含：
- `id` - 主键
- `dataset_uuid` - 数据集唯一标识
- `annotation_status` - 标注状态（COMPLETED等）
- `annotatio_file_path` - NAS路径（如 /mnt/nas/synnao/docker/...）
- `device_model` - 设备模型（如 agilex_cobot_decoupled_magic）
- `device_model_version` - 版本（如 h5_mp4_new）

---

## 修正方案

### 核心思路

1. **从数据库读取**: `device_model` + `device_model_version`
2. **映射到本地路径**: `data/{device_model}:{device_model_version}/`
3. **从factory config查找**: converter配置信息
4. **验证配置**: 使用Schema Analyzer

### 映射逻辑

```python
def map_db_to_local(device_model, device_model_version):
    # 1. 构建本地路径
    local_path = data_root / f"{device_model}:{device_model_version}"
    
    # 2. 从 converter_factory_config.yaml 查找
    factory_config = load_yaml('converter_factory_config.yaml')
    versions = factory_config[device_model]
    
    for version_config in versions:
        if version_config['version'] == device_model_version:
            return {
                'dataset_path': local_path,
                'converter_module': version_config['module'],
                'converter_class': version_config['class'],
                'converter_config_path': version_config['converter_config_path'],
            }
```

---

## 使用方法

### 前置条件

1. **数据库文件** - 包含 device_model_annotation 表的SQLite数据库
2. **本地数据** - data/ 目录下的数据集（命名格式：`{device_model}:{device_model_version}/`）
3. **Factory配置** - `converter_factory_config.yaml`

### 基础用法

```bash
cd /home/liu/program/robocoin-dataset

# 基本命令（需要指定数据库路径）
python scripts/config_validation/db_validator_fixed.py \
  --db-path /path/to/database.db
```

### 完整参数

```bash
python scripts/config_validation/db_validator_fixed.py \
  --db-path /path/to/database.db \                          # 数据库文件路径（必需）
  --data-root data/ \                                       # 本地数据根目录（默认: data/）
  --factory-config scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
  --output-dir outputs/db_validation_fixed \                # 输出目录
  --num-samples 2 \                                         # 每任务抽取episodes数
  --log-level INFO                                          # 日志级别
```

### 参数说明

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `--db-path` | ✅ | - | 数据库文件路径 |
| `--data-root` | ❌ | `data/` | 本地数据根目录 |
| `--factory-config` | ❌ | `scripts/.../converter_factory_config.yaml` | Factory配置路径 |
| `--output-dir` | ❌ | `outputs/db_validation_fixed` | 输出目录 |
| `--num-samples` | ❌ | `2` | 每任务抽取episodes数 |
| `--log-level` | ❌ | `INFO` | 日志级别 |

---

## 工作流程

### 完整流程图

```
[数据库] device_model_annotation表
       ↓
   读取所有记录
   (device_model + device_model_version)
       ↓
   ┌─────────────────────────────────────┐
   │ 映射到本地                           │
   │ • 路径: data/{model}:{version}/     │
   │ • 检查路径是否存在                   │
   └──────────┬──────────────────────────┘
              ↓
   ┌─────────────────────────────────────┐
   │ 从Factory Config查找                │
   │ • converter_module                  │
   │ • converter_class                   │
   │ • converter_config_path             │
   └──────────┬──────────────────────────┘
              ↓
   ┌─────────────────────────────────────┐
   │ 验证配置                             │
   │ • 抽取episodes                       │
   │ • 创建converter实例                  │
   │ • 提取schema                         │
   │ • 生成报告                           │
   └─────────────────────────────────────┘
```

### 详细步骤

#### 步骤1: 从数据库读取

```sql
SELECT 
    dataset_uuid,
    device_model,
    device_model_version,
    annotation_status,
    annotatio_file_path
FROM device_model_annotation
WHERE device_model IS NOT NULL
    AND device_model_version IS NOT NULL
ORDER BY device_model, device_model_version
```

**示例结果**:
- `agilex_cobot_decoupled_magic` + `h5_mp4_new`
- `galaxea_r1_lite` + `h5_mp4_version`
- `yinhe` + `default_version`

#### 步骤2: 映射到本地

| device_model | device_model_version | 本地路径 |
|-------------|---------------------|---------|
| agilex_cobot_decoupled_magic | h5_mp4_new | `data/agilex_cobot_decoupled_magic:h5_mp4_new/` |
| galaxea_r1_lite | h5_mp4_version | `data/galaxea_r1_lite:h5_mp4_version/` |
| yinhe | default_version | `data/yinhe:default_version/` |

**检查**: 路径必须存在，否则跳过该任务

#### 步骤3: 查找Converter配置

从 `converter_factory_config.yaml` 查找：

```yaml
agilex_cobot_decoupled_magic:
- version: h5_mp4_new
  module: robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_h5_mp4
  class: LerobotFormatConverterH5Mp4
  converter_config_path: converter_config_agilex_cobot_decoupled_magic_h5_mp4_new.yaml
```

**结果**:
- `converter_module`: `robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_h5_mp4`
- `converter_class`: `LerobotFormatConverterH5Mp4`
- `converter_config_path`: `scripts/format_converters/tolerobot/configs/converter_config_agilex_cobot_decoupled_magic_h5_mp4_new.yaml`

#### 步骤4: 验证配置

1. 抽取episodes（随机选取N个）
2. 创建converter实例
3. 使用Schema Analyzer提取schema
4. 记录验证结果

---

## 输出说明

### 输出文件结构

```
outputs/db_validation_fixed/
├── logs/
│   └── db_validator_fixed_YYYYMMDD_HHMMSS.log
└── db_validation_report_YYYYMMDD_HHMMSS.json
```

### 报告格式

```json
{
  "metadata": {
    "validation_date": "2025-10-24T15:30:00",
    "database_path": "/path/to/database.db",
    "data_root": "data/",
    "factory_config": "scripts/.../converter_factory_config.yaml",
    "total_db_tasks": 484,          // 数据库中的任务总数
    "local_available_tasks": 21,    // 本地可用的任务数
    "validated_tasks": 21,          // 实际验证的任务数
    "samples_per_task": 2
  },
  "summary": {
    "total_tasks": 21,
    "successful_tasks": 18,
    "partial_tasks": 2,
    "failed_tasks": 1,
    "skipped_tasks": 0
  },
  "validation_results": [
    {
      "task_name": "agilex_cobot_decoupled_magic:h5_mp4_new",
      "dataset_uuid": "004a37ce-a00a-4547-a5a0-0538af2c8a99",
      "device_model": "agilex_cobot_decoupled_magic",
      "device_model_version": "h5_mp4_new",
      "dataset_path": "data/agilex_cobot_decoupled_magic:h5_mp4_new",
      "converter_config": "scripts/.../converter_config_agilex_cobot_decoupled_magic_h5_mp4_new.yaml",
      "converter_module": "robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_h5_mp4",
      "converter_class": "LerobotFormatConverterH5Mp4",
      "sampled_episodes": [
        {
          "task_path": "打开台灯_蓝咖餐布_69",
          "episode_index": 3,
          "validation_status": "success",
          "schema": {
            "observations": {
              "state": {"shape": [26], "dtype": "float32"},
              "images": {
                "cam_high_rgb": {"shape": [720, 1280, 3], "dtype": "uint8"}
              }
            },
            "actions": {"shape": [26], "dtype": "float32"}
          },
          "errors": []
        }
      ],
      "validation_status": "success",
      "errors": [],
      "warnings": []
    }
  ]
}
```

### 验证状态说明

| 状态 | 说明 |
|------|------|
| `success` | 所有抽样episodes验证成功 |
| `partial` | 部分episodes验证成功 |
| `failed` | 所有episodes验证失败 |
| `skipped` | 未找到episodes或路径不存在 |

---

## 与三阶段验证系统的关系

### 在三阶段流程中的位置

```
阶段1: 配置检测器 (Config Validator)
══════════════════════════════════════
   |
   ├─→ 方式A: 文件系统扫描 (batch_validation.py)
   |   • 扫描 data/ 目录
   |   • 查找 local_dataset_info.yaml
   |
   └─→ 方式B: 数据库驱动 (db_validator_fixed.py) ← 新增
       • 从数据库读取任务列表
       • 映射到本地数据集
       • 验证配置
         ↓
阶段2: is_test 模式
══════════════════════════════════════
   • 执行真实转换（前10帧）
         ↓
阶段3: 正式转换
══════════════════════════════════════
   • 完整转换所有数据
```

### 选择建议

| 场景 | 推荐工具 | 原因 |
|------|---------|------|
| 只有本地数据 | `batch_validation.py` | 不需要数据库 |
| 有数据库+本地数据 | `db_validator_fixed.py` | 可以跟踪所有任务 |
| 生产环境 | `db_validator_fixed.py` | 集成数据库管理 |

---

## 示例

### 示例1: 基本验证

```bash
# 假设数据库在项目外部
python scripts/config_validation/db_validator_fixed.py \
  --db-path /mnt/external/robocoin.db \
  --num-samples 1
```

### 示例2: 自定义配置

```bash
# 使用自定义data目录和factory配置
python scripts/config_validation/db_validator_fixed.py \
  --db-path ~/databases/robocoin.db \
  --data-root /mnt/datasets/ \
  --factory-config custom_factory_config.yaml \
  --output-dir results/validation_$(date +%Y%m%d)
```

### 示例3: 调试模式

```bash
# 启用调试日志，深度验证（5个episodes）
python scripts/config_validation/db_validator_fixed.py \
  --db-path db/test.db \
  --num-samples 5 \
  --log-level DEBUG
```

---

## 常见问题

### Q1: 数据库中有484个任务，但只验证了21个？

**A**: 这是正常的。原因：
- 数据库中的 `annotatio_file_path` 指向NAS路径
- 您当前无法挂载NAS
- 只有 `data/` 目录下存在的数据集才会被验证
- 484个任务中，只有21个在本地有数据

### Q2: 如何知道哪些任务被跳过了？

**A**: 查看日志文件：
```bash
grep "⏭️  跳过任务" outputs/db_validation_fixed/logs/*.log
```

或查看报告中的metadata:
```json
{
  "metadata": {
    "total_db_tasks": 484,
    "local_available_tasks": 21,  // 只有21个在本地可用
    "validated_tasks": 21
  }
}
```

### Q3: 可以同时使用Schema对比功能吗？

**A**: 当前版本的 `db_validator_fixed.py` 只提取schema，不进行对比。
如果需要Schema对比，可以：
1. 使用 `db_validator_fixed.py` 生成报告
2. 然后使用 `schema_comparator.py` 对比结果

或者等待集成版本（计划中）。

### Q4: 如何获取数据库文件？

**A**: 请联系数据库管理员或查看项目文档中的数据库配置信息。

---

## 技术细节

### 与之前版本的对比

| 特性 | 错误版本 | 修正版 |
|------|---------|--------|
| 数据来源 | 假设数据库包含路径信息 | 从数据库读取device_model信息 |
| 路径映射 | 直接从数据库读取 | 根据规则构建本地路径 |
| Converter配置 | 从数据库读取 | 从factory config查找 |
| 适用场景 | ❌ 不可用 | ✅ 适用于实际环境 |

### 依赖关系

```
db_validator_fixed.py
    ├─→ SQLite数据库
    ├─→ converter_factory_config.yaml
    ├─→ converter_loader.py
    ├─→ schema_analyzer.py
    └─→ 本地 data/ 目录
```

---

## 未来改进计划

- [ ] 集成Schema对比功能
- [ ] 并行处理支持
- [ ] 将验证结果写回数据库
- [ ] 生成HTML格式报告
- [ ] 自动修复建议

---

**文档版本**: v1.0  
**最后更新**: 2025-10-24  
**维护者**: RoboCoin Team

