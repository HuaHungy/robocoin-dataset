# 数据库集成配置验证器 - 使用指南

> 版本: v1.0  
> 状态: ✅ 已实现，可用  
> 更新时间: 2025-10-24

## 📋 概述

数据库集成配置验证器是一个自动化工具，可以从数据库中读取所有任务（tasks），为每个任务随机抽取episodes，验证配置文件的正确性，并生成详细的JSON报告。

### 核心功能

1. **自动任务发现**: 从 `device_model_annotation` 表自动读取所有配置好的任务
2. **智能抽样**: 为每个任务随机抽取N个episodes（默认2个）
3. **配置验证**: 使用Schema Analyzer验证配置与实际数据的一致性
4. **详细报告**: 生成包含所有验证结果的JSON报告

### 工作流程

```
┌────────────────────┐
│  1. 连接数据库      │
│  查询任务表        │
└─────────┬──────────┘
          ↓
┌────────────────────┐
│  2. 遍历所有任务    │
│  抽取episodes     │
└─────────┬──────────┘
          ↓
┌────────────────────┐
│  3. 加载converter   │
│  验证配置          │
└─────────┬──────────┘
          ↓
┌────────────────────┐
│  4. 生成JSON报告    │
│  统计结果          │
└────────────────────┘
```

## 🎯 实现状态

| 功能模块 | 状态 | 说明 |
|---------|------|------|
| 数据库查询 | ✅ 已实现 | 从 device_model_annotation 表读取任务 |
| Episode抽样 | ✅ 已实现 | 随机抽取指定数量的episodes |
| 配置验证 | ✅ 已实现 | 使用 Schema Analyzer 验证 |
| 报告生成 | ✅ 已实现 | 生成详细的JSON报告 |
| 错误处理 | ✅ 已实现 | 完整的异常捕获和日志记录 |
| 命令行接口 | ✅ 已实现 | 支持参数配置 |

## 📦 前置条件

### 1. 数据库准备

需要一个包含 `device_model_annotation` 表的SQLite数据库，表结构如下：

```sql
CREATE TABLE device_model_annotation (
    id INTEGER PRIMARY KEY,
    device_model TEXT NOT NULL,
    device_model_annotation TEXT NOT NULL,
    dataset_path TEXT,
    repo_id TEXT,
    converter_config_path TEXT,
    converter_module TEXT,
    converter_class TEXT
);
```

**必需字段**:
- `dataset_path`: 数据集的绝对路径或相对路径
- `converter_config_path`: 配置文件路径（相对于项目根目录）

### 2. 数据集结构

数据集目录需要包含：
- `local_dataset_info.yaml`: 数据集信息
- `local_task_info.yaml`: 任务信息（在task目录下）
- Episode数据文件（H5, MCAP, ROS bag, MP4+JSON, etc.）

### 3. 配置文件

每个任务需要有对应的 `converter_config_*.yaml` 文件。

## 🚀 使用方法

### 基础用法

```bash
cd /home/liu/program/robocoin-dataset

# 基础命令（假设数据库在db/datasets.db）
python scripts/config_validation/db_integrated_validator.py \
  --db-path db/datasets.db \
  --output-dir outputs/db_validation
```

### 完整参数

```bash
python scripts/config_validation/db_integrated_validator.py \
  --db-path /path/to/database.db \      # 数据库文件路径（必需）
  --output-dir /path/to/output \        # 输出目录（默认：outputs/db_validation）
  --num-samples 2 \                     # 每个任务抽取的episode数量（默认：2）
  --log-level INFO                      # 日志级别：DEBUG|INFO|WARNING|ERROR
```

### 参数说明

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `--db-path` | ✅ | - | 数据库文件路径 |
| `--output-dir` | ❌ | `outputs/db_validation` | 输出目录 |
| `--num-samples` | ❌ | `2` | 每个任务抽取的episode数量 |
| `--log-level` | ❌ | `INFO` | 日志级别 |

### 示例场景

#### 场景1: 快速验证（单个episode）

```bash
# 每个任务只抽取1个episode，快速完成
python scripts/config_validation/db_integrated_validator.py \
  --db-path db/datasets.db \
  --num-samples 1
```

#### 场景2: 深度验证（多个episodes）

```bash
# 每个任务抽取5个episodes，更全面的验证
python scripts/config_validation/db_integrated_validator.py \
  --db-path db/datasets.db \
  --num-samples 5 \
  --log-level DEBUG
```

#### 场景3: 指定输出目录

```bash
# 输出到自定义目录
python scripts/config_validation/db_integrated_validator.py \
  --db-path /data/robocoin.db \
  --output-dir /results/validation_$(date +%Y%m%d)
```

## 📊 输出说明

### 输出文件结构

```
outputs/db_validation/
├── logs/
│   └── db_integrated_validator_YYYYMMDD_HHMMSS.log  # 详细日志
└── db_validation_report_YYYYMMDD_HHMMSS.json        # 验证报告
```

### 报告格式

验证报告是一个JSON文件，包含以下结构：

```json
{
  "metadata": {
    "validation_date": "2025-10-24T15:30:00",
    "database_path": "/path/to/database.db",
    "total_tasks": 15,
    "samples_per_task": 2
  },
  "summary": {
    "total_tasks": 15,
    "successful_tasks": 12,
    "partial_tasks": 2,
    "failed_tasks": 1
  },
  "validation_results": [
    {
      "task_id": 1,
      "task_name": "zhipingfang:dual_arm_with_pose",
      "device_model": "zhipingfang",
      "device_model_annotation": "dual_arm_with_pose",
      "dataset_path": "/data/zhipingfang/dual_arm",
      "converter_config": "configs/converter_config_zhipingfang.yaml",
      "sampled_episodes": [
        {
          "task_path": "/data/zhipingfang/dual_arm/task1",
          "episode_index": 0,
          "validation_status": "success",
          "schema": {
            "observation": {
              "state": {"shape": [79], "dtype": "float32"},
              "images": {
                "cam_high_rgb": {"shape": [720, 1280, 3], "dtype": "uint8"}
              }
            },
            "action": {"shape": [79], "dtype": "float32"}
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

### 验证状态

| 状态 | 说明 |
|------|------|
| `success` | 所有抽样episodes验证成功 |
| `partial` | 部分episodes验证成功 |
| `failed` | 所有episodes验证失败 |
| `skipped` | 未找到episodes，跳过验证 |
| `unknown` | 验证未完成或发生异常 |

## 📝 验证逻辑

### Episode抽样策略

1. **扫描数据集**: 查找所有包含 `local_task_info.yaml` 的目录
2. **估算episode数量**:
   - H5格式：统计 `*.h5`/`*.hdf5` 文件
   - MCAP格式：统计 `*.mcap` 文件
   - 目录格式：统计包含 "episode" 的子目录
3. **随机抽取**: 使用 `random.sample()` 随机抽取N个episodes

### 配置验证流程

1. **加载配置**: 读取 `converter_config_*.yaml`
2. **创建Converter实例**: 根据配置实例化对应的converter
3. **提取Schema**: 使用 Schema Analyzer 从实际数据中提取结构
4. **对比验证**: 比较配置中的预期结构与实际结构
5. **记录结果**: 保存验证状态和错误信息

## ⚠️ 注意事项

### 1. 数据库要求

- 数据库文件必须存在且可读
- `device_model_annotation` 表必须包含所需字段
- `dataset_path` 和 `converter_config_path` 不能为空

### 2. 数据集路径

- 如果 `dataset_path` 是相对路径，会相对于项目根目录解析
- 确保数据集路径存在且可访问
- 路径中的数据集必须包含正确的 `local_task_info.yaml`

### 3. 内存和性能

- **大文件警告**: 对于MCAP等大文件（>1GB），验证可能消耗大量内存
- **建议**: 
  - 先使用 `--num-samples 1` 快速测试
  - 对于大型数据集，考虑分批验证
  - 监控系统内存使用情况

### 4. 错误处理

- 单个任务验证失败不会中断整个流程
- 所有错误都会被记录到报告中
- 详细的错误信息会写入日志文件

### 5. 当前限制

- ✅ 支持所有已实现的converter格式
- ❌ 不支持未在数据库中注册的任务
- ❌ 不验证数据质量（只验证结构）
- ⏳ Schema对比功能待完善（目前只提取schema）

## 🔧 故障排查

### 问题1: 数据库文件未找到

```
FileNotFoundError: Database not found: /path/to/db
```

**解决方案**:
- 检查数据库文件路径是否正确
- 确保数据库文件存在且有读取权限
- 使用绝对路径避免路径解析问题

### 问题2: 数据集路径不存在

```
⚠️ 数据集路径不存在: /path/to/dataset
```

**解决方案**:
- 检查数据库中的 `dataset_path` 是否正确
- 更新数据库中的路径为实际路径
- 确保数据集已下载并解压

### 问题3: 未找到episodes

```
⚠️ 未能抽取到episodes，跳过
```

**解决方案**:
- 检查数据集目录结构是否正确
- 确保存在 `local_task_info.yaml` 文件
- 检查episode文件是否存在（H5, MCAP等）

### 问题4: Converter实例化失败

```
Task validation error: Failed to create converter instance
```

**解决方案**:
- 检查 `converter_config_path` 是否正确
- 验证配置文件语法是否正确
- 确保配置文件中的所有路径存在

## 📈 性能优化建议

### 1. 分批验证

对于大量任务，可以分批运行：

```bash
# 修改数据库查询，只获取特定任务
# 或者手动创建多个小数据库文件
```

### 2. 并行处理（未来功能）

当前版本是串行处理，未来可以考虑：
- 多进程并行验证
- 异步IO处理
- 分布式验证

### 3. 缓存优化

- Converter实例可以复用（针对相同配置的任务）
- Schema提取结果可以缓存（针对相同episode）

## 🔄 与现有工具的关系

### Config Validation体系

```
┌─────────────────────────────────────────────────────────────┐
│  手动工具                                                     │
│  • schema_analyzer.py - 单个数据集Schema分析                 │
│  • config_comparator.py - 配置对比                          │
│  • batch_validation.py - 批量验证（基于目录扫描）           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  自动化工具（本工具）                                         │
│  • db_integrated_validator.py - 数据库驱动的自动化验证       │
│  • 从数据库自动发现任务                                      │
│  • 智能抽样 + 验证 + 报告                                    │
└─────────────────────────────────────────────────────────────┘
```

### 使用建议

1. **开发阶段**: 使用 `schema_analyzer.py` 手动分析单个数据集
2. **配置调整**: 使用 `config_comparator.py` 对比配置
3. **批量测试**: 使用 `batch_validation.py` 验证多个数据集
4. **生产验证**: 使用 `db_integrated_validator.py` 自动化验证所有任务

## 🛠️ 扩展开发

### 自定义Episode抽样策略

修改 `_estimate_episodes()` 方法：

```python
def _estimate_episodes(self, task_path: Path) -> int:
    # 添加自定义逻辑
    # 例如：只计算某种类型的episodes
    return episode_count
```

### 自定义验证逻辑

修改 `validate_task()` 方法：

```python
def validate_task(self, task, sampled_episodes):
    # 添加自定义验证
    # 例如：检查数据质量、帧数一致性等
    return result
```

### 自定义报告格式

修改 `generate_report()` 方法：

```python
def generate_report(self, validation_results):
    # 添加自定义报告格式
    # 例如：生成HTML报告、Excel表格等
    return report_path
```

## 📚 相关文档

- [设计文档](DB_INTEGRATED_CONFIG_VALIDATOR_DESIGN.md) - 详细的设计说明
- [Schema Analyzer文档](../scripts/config_validation/README.md) - Schema分析工具说明
- [Converter开发指南](../docs/CONVERTER_DEVELOPMENT_GUIDE.md) - Converter实现规范

## 🎯 后续计划

### 短期（已规划）
- [ ] 添加Schema对比功能（配置 vs 实际）
- [ ] 生成HTML格式报告
- [ ] 添加数据质量检查（帧数、图像大小等）

### 中期
- [ ] 支持并行验证
- [ ] 集成到CI/CD流程
- [ ] 添加Web界面

### 长期
- [ ] 支持自动修复配置
- [ ] 集成到数据集管理系统
- [ ] 添加历史报告对比功能

---

**最后更新**: 2025-10-24  
**维护者**: RoboCoin Team  
**状态**: ✅ 生产可用

