# 数据库集成配置验证器设计文档

**日期**: 2025-10-23  
**版本**: v1.0  
**状态**: 设计完成，待实施

---

## 📋 需求概述

### 核心需求

从数据库中自动获取所有tasks，对每个task随机抽取2个episodes进行配置验证，生成详细的JSON报告。

### 工作流程

```
┌─────────────────────────────────────────────────────────────┐
│  阶段1: 数据库查询                                            │
├─────────────────────────────────────────────────────────────┤
│  1. 连接LeFormatConvertDB数据库                              │
│  2. 查询device_model_annotation表                           │
│  3. 获取所有unique (device_model, version) 组合            │
│  4. 获取每个组合对应的dataset列表                           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  阶段2: Episode抽样                                          │
├─────────────────────────────────────────────────────────────┤
│  对每个task:                                                 │
│  1. 定位task的原始数据路径                                   │
│  2. 使用Converter的episode定位方法找到所有episodes          │
│  3. 随机抽取2个episodes（如果总数<2则全部抽取）             │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  阶段3: 配置验证                                             │
├─────────────────────────────────────────────────────────────┤
│  对每个抽样的episode:                                        │
│  1. 加载对应的converter_config                              │
│  2. 使用Schema Analyzer提取实际schema                       │
│  3. 对比config vs actual schema                            │
│  4. 记录所有不匹配项                                         │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  阶段4: 报告生成                                             │
├─────────────────────────────────────────────────────────────┤
│  生成JSON报告:                                               │
│  1. 全局统计（总tasks数、验证成功/失败率）                  │
│  2. 每个device_model的详细结果                              │
│  3. 每个task的抽样episodes验证结果                          │
│  4. 所有问题的汇总和修复建议                                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 🏗️ 架构设计

### 核心组件

```python
# scripts/config_validation/db_integrated_validator.py

class DatabaseIntegratedConfigValidator:
    """数据库集成的配置验证器"""
    
    def __init__(
        self,
        db_path: str,
        config_dir: Path,
        sample_size: int = 2,
        logger: Optional[logging.Logger] = None
    ):
        """
        Args:
            db_path: 数据库路径
            config_dir: 配置文件目录
            sample_size: 每个task抽样的episode数量
            logger: 日志记录器
        """
        pass
    
    def validate_all_tasks(self) -> ValidationReport:
        """验证所有tasks"""
        pass
    
    def _query_tasks_from_db(self) -> List[TaskInfo]:
        """从数据库查询所有tasks"""
        pass
    
    def _sample_episodes(self, task_info: TaskInfo) -> List[Path]:
        """随机抽取episodes"""
        pass
    
    def _validate_episode(
        self, 
        episode_path: Path, 
        converter_config: dict
    ) -> EpisodeValidationResult:
        """验证单个episode"""
        pass
    
    def _generate_report(
        self, 
        results: List[ValidationResult]
    ) -> ValidationReport:
        """生成验证报告"""
        pass
```

### 数据结构

```python
from dataclasses import dataclass
from typing import List, Dict, Optional
from pathlib import Path

@dataclass
class TaskInfo:
    """Task信息"""
    dataset_uuid: str
    dataset_name: str
    dataset_path: Path
    device_model: str
    device_model_version: str
    task_name: str
    task_path: Path

@dataclass
class EpisodeValidationResult:
    """Episode验证结果"""
    episode_path: Path
    episode_index: int
    is_valid: bool
    issues: List[Dict]  # 不匹配的项目列表
    schema: Optional[Dict]
    error: Optional[str]

@dataclass
class TaskValidationResult:
    """Task验证结果"""
    task_info: TaskInfo
    sampled_episodes: List[Path]
    episode_results: List[EpisodeValidationResult]
    is_valid: bool
    common_issues: List[Dict]  # 所有抽样episodes的共同问题

@dataclass
class ValidationReport:
    """完整验证报告"""
    total_tasks: int
    total_episodes_validated: int
    valid_tasks: int
    invalid_tasks: int
    task_results: List[TaskValidationResult]
    summary: Dict
    recommendations: List[str]
```

---

## 💾 数据库查询

### SQL查询逻辑

```python
def _query_tasks_from_db(self) -> List[TaskInfo]:
    """从数据库查询所有tasks
    
    查询逻辑:
    1. 从LeFormatConvertDB表获取所有数据集
    2. 读取每个数据集的device_model_annotation.yaml
    3. 读取每个数据集的local_dataset_info.yaml获取tasks
    4. 扫描数据集目录，找到所有local_task_info.yaml定位task_path
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    engine = create_engine(f'sqlite:///{self.db_path}')
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # 查询所有待转换或已转换的数据集
        from robocoin_dataset.server.db_models import LeFormatConvertDB, TaskStatus
        
        datasets = session.query(LeFormatConvertDB).filter(
            LeFormatConvertDB.convert_status.in_([
                TaskStatus.PENDING,
                TaskStatus.PROCESSING,
                TaskStatus.SUCCESS,
                TaskStatus.FAILED
            ])
        ).all()
        
        task_infos = []
        
        for dataset in datasets:
            dataset_path = Path(dataset.original_dataset_path)
            
            if not dataset_path.exists():
                self.logger.warning(f"数据集路径不存在: {dataset_path}")
                continue
            
            # 读取device_model_annotation
            annotation_file = dataset_path / "device_model_annotation.yaml"
            if not annotation_file.exists():
                self.logger.warning(f"未找到annotation文件: {annotation_file}")
                continue
            
            with open(annotation_file) as f:
                annotation = yaml.safe_load(f)
            
            device_model = annotation['device_model']
            device_model_version = annotation.get('device_model_version', 'default_version')
            
            # 读取local_dataset_info获取tasks
            dataset_info_file = dataset_path / "local_dataset_info.yaml"
            if not dataset_info_file.exists():
                self.logger.warning(f"未找到dataset_info文件: {dataset_info_file}")
                continue
            
            with open(dataset_info_file) as f:
                dataset_info = yaml.safe_load(f)
            
            tasks = dataset_info.get('task_descriptions', [])
            
            # 找到所有task_path
            for task_dir in dataset_path.rglob("local_task_info.yaml"):
                task_path = task_dir.parent
                
                with open(task_dir) as f:
                    task_info_data = yaml.safe_load(f)
                
                task_index = task_info_data.get('task_index', 0)
                task_name = tasks[task_index] if task_index < len(tasks) else "unknown"
                
                task_info = TaskInfo(
                    dataset_uuid=dataset.dataset_uuid,
                    dataset_name=dataset.dataset_name,
                    dataset_path=dataset_path,
                    device_model=device_model,
                    device_model_version=device_model_version,
                    task_name=task_name,
                    task_path=task_path
                )
                
                task_infos.append(task_info)
        
        return task_infos
        
    finally:
        session.close()
```

---

## 🎲 Episode抽样

### 抽样策略

```python
def _sample_episodes(self, task_info: TaskInfo) -> List[Path]:
    """随机抽取episodes
    
    策略:
    1. 使用对应的Converter定位所有episodes
    2. 随机抽取sample_size个（默认2个）
    3. 如果总数少于sample_size，全部抽取
    """
    import random
    from robocoin_dataset.format_converter.utils.converter_loader import (
        load_converter_class,
        create_converter_instance
    )
    
    # 1. 加载converter config
    config_file = self._get_converter_config_path(
        task_info.device_model,
        task_info.device_model_version
    )
    
    with open(config_file) as f:
        converter_config = yaml.safe_load(f)
    
    # 2. 创建converter实例（用于episode定位）
    try:
        converter = create_converter_instance(
            converter_config=converter_config,
            dataset_path=str(task_info.dataset_path),
            output_path="/tmp/dummy_output",  # 不会实际转换
            logger=self.logger
        )
    except Exception as e:
        self.logger.error(f"无法创建converter: {e}")
        return []
    
    # 3. 获取该task的所有episodes
    episodes = self._get_task_episodes(converter, task_info.task_path)
    
    if not episodes:
        self.logger.warning(f"Task无episodes: {task_info.task_path}")
        return []
    
    # 4. 随机抽样
    sample_count = min(self.sample_size, len(episodes))
    sampled = random.sample(episodes, sample_count)
    
    self.logger.info(
        f"从 {len(episodes)} 个episodes中抽取 {sample_count} 个: "
        f"{task_info.task_path.name}"
    )
    
    return sampled


def _get_task_episodes(self, converter: Any, task_path: Path) -> List[Path]:
    """获取task的所有episodes（使用converter的定位方法）
    
    根据不同converter类型调用相应的方法
    """
    episodes = []
    
    # 方法1: H5单文件格式
    if hasattr(converter, 'task_episode_h5file_paths'):
        h5_files_dict = converter.task_episode_h5file_paths
        if task_path in h5_files_dict:
            episodes = h5_files_dict[task_path]
    
    # 方法2: 目录格式（JPG+JSON, H5+JPG等）
    elif hasattr(converter, '_get_all_episode_dirs'):
        episodes = converter._get_all_episode_dirs(task_path)
    
    # 方法3: H5+MP4格式
    elif hasattr(converter, '_get_all_episode_h5_files'):
        episodes = converter._get_all_episode_h5_files(task_path)
    
    # 方法4: MCAP格式
    elif hasattr(converter, '_get_all_mcap_files'):
        episodes = converter._get_all_mcap_files(task_path)
    
    # 方法5: 通用索引方式
    elif hasattr(converter, '_get_task_episodes_num'):
        num_episodes = converter._get_task_episodes_num(task_path)
        # 返回episode索引列表（而不是路径）
        episodes = list(range(num_episodes))
    
    return episodes
```

---

## ✅ 配置验证

### 验证逻辑

```python
def _validate_episode(
    self, 
    episode_path: Path,
    task_info: TaskInfo,
    converter_config: dict,
    episode_index: int
) -> EpisodeValidationResult:
    """验证单个episode
    
    使用Schema Analyzer提取schema并对比配置
    """
    from robocoin_dataset.config_validation.schema_analyzer import SchemaAnalyzer
    
    result = EpisodeValidationResult(
        episode_path=episode_path,
        episode_index=episode_index,
        is_valid=True,
        issues=[],
        schema=None,
        error=None
    )
    
    try:
        # 1. 创建Schema Analyzer
        analyzer = SchemaAnalyzer(
            config_dir=self.config_dir,
            logger=self.logger
        )
        
        # 2. 提取schema（使用converter）
        schema = analyzer._extract_episode_schema_from_converter(
            converter=self._create_converter(task_info, converter_config),
            task_path=task_info.task_path,
            episode_info={
                'episode_path': episode_path,
                'episode_idx': episode_index,
                'type': self._infer_episode_type(episode_path)
            }
        )
        
        result.schema = schema
        
        # 3. 对比schema vs config
        issues = analyzer._compare_schema_with_config(
            schema=schema,
            config=converter_config
        )
        
        result.issues = issues
        result.is_valid = len(issues) == 0
        
    except Exception as e:
        result.is_valid = False
        result.error = str(e)
        self.logger.error(f"验证episode失败: {episode_path}, 错误: {e}")
    
    return result
```

---

## 📊 报告生成

### JSON报告格式

```json
{
  "validation_summary": {
    "timestamp": "2025-10-23T21:30:00",
    "total_tasks": 150,
    "total_episodes_validated": 300,
    "valid_tasks": 142,
    "invalid_tasks": 8,
    "success_rate": 94.7,
    "sample_size_per_task": 2
  },
  
  "device_models": [
    {
      "device_model": "zhipingfang",
      "device_model_version": "dual_arm_no_pose",
      "total_tasks": 45,
      "valid_tasks": 43,
      "invalid_tasks": 2,
      "config_file": "converter_config_zhipingfang_dual_arm_no_pose.yaml",
      
      "common_issues": [
        {
          "issue_type": "missing_in_config",
          "field": "observations/qvel",
          "frequency": "43/45 tasks",
          "description": "数据中存在qvel字段，但配置中未定义",
          "recommendation": "添加到observation.state.sub_state配置"
        }
      ],
      
      "task_results": [
        {
          "task_info": {
            "dataset_uuid": "xxx-yyy-zzz",
            "dataset_name": "算法采集_PCB",
            "task_name": "pick_and_place",
            "task_path": "/path/to/task"
          },
          
          "sampled_episodes": [
            {
              "episode_index": 5,
              "episode_path": "/path/to/episode_5.h5",
              "is_valid": false,
              "issues": [
                {
                  "type": "missing_in_config",
                  "field": "observations/qvel",
                  "actual_shape": [100],
                  "actual_dtype": "float32"
                },
                {
                  "type": "shape_mismatch",
                  "field": "observations/images/cam_high",
                  "config_expects": "any",
                  "actual_shape": [107, 480, 640, 3]
                }
              ],
              "schema": {
                "observations": {...},
                "actions": {...}
              }
            },
            {
              "episode_index": 12,
              "episode_path": "/path/to/episode_12.h5",
              "is_valid": true,
              "issues": [],
              "schema": {...}
            }
          ],
          
          "is_valid": false,
          "common_issues_in_task": [
            {
              "type": "missing_in_config",
              "field": "observations/qvel",
              "appears_in": "2/2 sampled episodes"
            }
          ]
        }
      ]
    }
  ],
  
  "recommendations": [
    {
      "priority": "high",
      "device_model": "zhipingfang",
      "device_model_version": "dual_arm_no_pose",
      "action": "add_missing_field",
      "field": "observations/qvel",
      "affected_tasks": 43,
      "config_snippet": "observation:\n  state:\n    sub_state:\n      - names: [velocity_1, ...]\n        args:\n          h5_path: observations/qvel\n          range_from: 0\n          range_to: 100"
    }
  ]
}
```

---

## 🚀 使用方式

### 命令行接口

```bash
# 验证所有tasks（默认每task抽2个episodes）
python scripts/config_validation/db_integrated_validator.py \
  --db-path /path/to/convert_db.db \
  --config-dir /path/to/configs \
  --output validation_report.json

# 指定抽样数量
python scripts/config_validation/db_integrated_validator.py \
  --db-path /path/to/convert_db.db \
  --config-dir /path/to/configs \
  --output validation_report.json \
  --sample-size 5

# 只验证特定device_model
python scripts/config_validation/db_integrated_validator.py \
  --db-path /path/to/convert_db.db \
  --config-dir /path/to/configs \
  --output validation_report.json \
  --device-model zhipingfang

# 只验证特定version
python scripts/config_validation/db_integrated_validator.py \
  --db-path /path/to/convert_db.db \
  --config-dir /path/to/configs \
  --output validation_report.json \
  --device-model zhipingfang \
  --version dual_arm_no_pose
```

### Python API

```python
from pathlib import Path
from robocoin_dataset.config_validation.db_integrated_validator import (
    DatabaseIntegratedConfigValidator
)

# 创建验证器
validator = DatabaseIntegratedConfigValidator(
    db_path="/path/to/convert_db.db",
    config_dir=Path("/path/to/configs"),
    sample_size=2
)

# 执行验证
report = validator.validate_all_tasks()

# 保存报告
report.save_json("validation_report.json")

# 打印摘要
report.print_summary()

# 获取所有问题
all_issues = report.get_all_issues()

# 获取修复建议
recommendations = report.get_recommendations()
```

---

## 📁 文件结构

```
scripts/config_validation/
├── db_integrated_validator.py      # 主验证器
├── validation_models.py            # 数据模型定义
├── episode_sampler.py              # Episode抽样逻辑
├── report_generator.py             # 报告生成器
└── utils/
    ├── db_query.py                 # 数据库查询工具
    └── episode_locator_adapter.py  # Episode定位适配器
```

---

## ⚙️ 配置选项

### 验证器配置文件

```yaml
# scripts/config_validation/validator_config.yaml

sampling:
  # 每个task抽样的episode数量
  sample_size: 2
  
  # 如果task的episode数少于此值，全部验证
  min_episodes_for_sampling: 5
  
  # 随机种子（用于可复现的抽样）
  random_seed: 42

validation:
  # 是否验证schema的详细内容
  validate_schema_details: true
  
  # 是否检查数据类型匹配
  validate_dtype: true
  
  # 是否检查shape匹配
  validate_shape: true
  
  # 允许的shape容差（用于变长数据）
  shape_tolerance: 0

report:
  # 报告格式
  format: "json"  # json, yaml, html
  
  # 是否包含完整schema
  include_full_schema: false
  
  # 是否包含成功的验证结果
  include_successful_results: false
  
  # 只报告共同问题（出现在多个episodes的问题）
  only_common_issues: true

database:
  # 查询的任务状态
  query_status: ["PENDING", "SUCCESS", "FAILED"]
  
  # 是否跳过已经成功转换的tasks
  skip_successful_tasks: false
```

---

## 🔄 与现有系统集成

### 与Schema Analyzer集成

```python
# 复用现有的Schema Analyzer
from robocoin_dataset.config_validation.schema_analyzer import SchemaAnalyzer

# 在验证过程中调用
schema = analyzer._extract_episode_schema_from_converter(
    converter=converter,
    task_path=task_path,
    episode_info=episode_info
)
```

### 与Converter Loader集成

```python
# 复用现有的Converter Loader
from robocoin_dataset.config_validation.converter_loader import (
    create_converter_instance
)

# 动态创建converter实例
converter = create_converter_instance(
    converter_config=config,
    dataset_path=dataset_path,
    output_path="/tmp/dummy",
    logger=logger
)
```

---

## 🎯 实施计划

### Phase 1: 核心功能 (2天)

**Day 1**:
- [x] 设计文档完成
- [ ] 实现数据库查询模块
- [ ] 实现Episode抽样逻辑
- [ ] 测试基本流程

**Day 2**:
- [ ] 集成Schema Analyzer
- [ ] 实现配置对比逻辑
- [ ] 测试验证功能

### Phase 2: 报告生成 (1天)

**Day 3**:
- [ ] 实现JSON报告生成
- [ ] 实现问题汇总
- [ ] 实现修复建议生成
- [ ] 完整测试

### Phase 3: 优化和文档 (0.5天)

**Day 4**:
- [ ] 性能优化
- [ ] 错误处理完善
- [ ] 使用文档
- [ ] 示例脚本

---

## 📝 总结

### 关键特性

✅ **数据库驱动**: 自动从数据库获取所有tasks  
✅ **智能抽样**: 随机抽取代表性episodes，节省时间  
✅ **全面验证**: 集成Schema Analyzer，深度对比配置  
✅ **详细报告**: JSON格式，包含所有问题和修复建议  
✅ **可复现**: 支持固定随机种子  
✅ **灵活过滤**: 可按device_model、version过滤

### 优势

1. **自动化**: 无需手动指定数据集列表
2. **高效**: 抽样验证而不是全量验证
3. **准确**: 使用实际converter逻辑定位episodes
4. **实用**: 生成可操作的修复建议

### 下一步

1. 确认设计方案
2. 实施Phase 1核心功能
3. 小规模测试验证
4. 全量运行生成报告

---

**文档版本**: v1.0  
**作者**: AI Assistant  
**状态**: 待用户确认

