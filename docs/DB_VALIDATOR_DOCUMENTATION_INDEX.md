# 数据库集成配置验证器 - 文档索引

> 最后更新: 2025-10-24  
> 版本: v1.0

## 📚 文档总览

这个目录包含了数据库集成配置验证器的完整文档。根据你的需求选择合适的文档：

### 快速开始
- [5分钟快速开始](../scripts/config_validation/README_DB_VALIDATOR.md) ← **从这里开始！**
  - 创建示例数据库
  - 运行第一个验证
  - 查看和分析报告

### 完整用户指南
- [用户指南](DB_CONFIG_VALIDATOR_USER_GUIDE.md) - **详细文档**
  - 功能介绍和实现状态
  - 完整的使用方法
  - 参数说明和示例场景
  - 输出格式详解
  - 故障排查指南
  - 性能优化建议

### 设计文档
- [设计文档](DB_INTEGRATED_CONFIG_VALIDATOR_DESIGN.md) - **架构和设计**
  - 需求分析
  - 系统架构
  - 工作流程
  - 数据库schema
  - 输出格式设计

## 🗂️ 文件结构

```
robocoin-dataset/
├── scripts/
│   └── config_validation/
│       ├── db_integrated_validator.py      # 主程序
│       ├── README_DB_VALIDATOR.md          # 快速开始
│       ├── converter_loader.py             # Converter加载器
│       └── schema_analyzer.py              # Schema分析器
│
├── docs/
│   ├── DB_CONFIG_VALIDATOR_USER_GUIDE.md           # 用户指南
│   ├── DB_INTEGRATED_CONFIG_VALIDATOR_DESIGN.md    # 设计文档
│   └── DB_VALIDATOR_DOCUMENTATION_INDEX.md (本文件)
│
└── db/
    └── (数据库文件存放位置)
```

## 🎯 按需求选择文档

### 场景1: 我是新用户，想快速了解怎么用

👉 阅读: [5分钟快速开始](../scripts/config_validation/README_DB_VALIDATOR.md)

### 场景2: 我需要详细了解所有功能和参数

👉 阅读: [用户指南](DB_CONFIG_VALIDATOR_USER_GUIDE.md)

### 场景3: 我遇到了问题，需要排查

👉 查看: [用户指南 - 故障排查章节](DB_CONFIG_VALIDATOR_USER_GUIDE.md#故障排查)

### 场景4: 我想了解系统架构和设计

👉 阅读: [设计文档](DB_INTEGRATED_CONFIG_VALIDATOR_DESIGN.md)

### 场景5: 我想扩展或修改功能

👉 阅读: 
1. [设计文档](DB_INTEGRATED_CONFIG_VALIDATOR_DESIGN.md)
2. [用户指南 - 扩展开发章节](DB_CONFIG_VALIDATOR_USER_GUIDE.md#扩展开发)

## 📝 相关工具文档

### 配置验证工具链

| 工具 | 位置 | 用途 |
|------|------|------|
| db_integrated_validator | scripts/config_validation/ | 数据库驱动的自动化验证 |
| schema_analyzer | scripts/config_validation/ | Schema提取和分析 |
| config_comparator | scripts/config_validation/ | 配置对比 |
| converter_loader | scripts/config_validation/ | 动态加载Converter |
| batch_validation | scripts/config_validation/ | 批量验证（目录扫描） |

### Converter相关

| 文档 | 位置 | 说明 |
|------|------|------|
| Converter开发指南 | docs/ | Converter实现规范 |
| Config字段命名 | docs/CONFIG_FIELD_NAMING.md | 配置字段命名规范 |
| Format Converter重构 | docs/REFACTOR_COMPLETION_REPORT.md | 重构完成报告 |

## 🔗 关键概念链接

- **Schema**: 数据结构描述（observation, action的shape和dtype）
- **Episode**: 一次完整的数据采集记录
- **Task**: 一个具体的任务（如"抓取苹果"）
- **device_model_annotation**: 数据库表，存储所有任务信息
- **Converter**: 将原始数据格式转换为LeRobot格式的工具

## 🚀 命令速查

```bash
# 快速验证
python scripts/config_validation/db_integrated_validator.py \
  --db-path db/datasets.db --num-samples 1

# 完整验证
python scripts/config_validation/db_integrated_validator.py \
  --db-path db/datasets.db --num-samples 2

# 调试模式
python scripts/config_validation/db_integrated_validator.py \
  --db-path db/datasets.db --log-level DEBUG

# 自定义输出目录
python scripts/config_validation/db_integrated_validator.py \
  --db-path db/datasets.db \
  --output-dir /custom/path/validation_results
```

## 📊 输出文件速查

| 文件 | 位置 | 说明 |
|------|------|------|
| 验证报告 | `outputs/db_validation/db_validation_report_*.json` | JSON格式的完整验证结果 |
| 日志文件 | `outputs/db_validation/logs/*.log` | 详细的运行日志 |

## ❓ 常见问题

### Q1: 我没有数据库文件怎么办？

A: 参考 [快速开始 - 准备数据库](../scripts/config_validation/README_DB_VALIDATOR.md#1-准备数据库) 章节，里面有创建示例数据库的脚本。

### Q2: 验证报告怎么看？

A: 参考 [用户指南 - 输出说明](DB_CONFIG_VALIDATOR_USER_GUIDE.md#输出说明) 章节，有详细的报告格式说明。

### Q3: 可以只验证某些特定的任务吗？

A: 当前版本会验证数据库中的所有任务。如需只验证部分任务，可以创建一个只包含这些任务的临时数据库。

### Q4: 验证失败了怎么办？

A: 查看 [用户指南 - 故障排查](DB_CONFIG_VALIDATOR_USER_GUIDE.md#故障排查) 章节，有详细的错误类型和解决方案。

### Q5: 可以集成到CI/CD吗？

A: 可以！参考 [快速开始 - 场景2: CI/CD集成](../scripts/config_validation/README_DB_VALIDATOR.md#场景2-cicd集成)。

## 💡 最佳实践

1. **首次运行**: 使用 `--num-samples 1` 快速测试
2. **定期验证**: 在数据集或配置更新后运行验证
3. **CI集成**: 将验证集成到CI流程中，自动检测配置问题
4. **报告归档**: 保存历史验证报告，便于追踪问题变化
5. **内存监控**: 对大型数据集验证时注意监控内存使用

## 🆘 获取帮助

1. 查看相关文档（见上方链接）
2. 检查日志文件中的错误信息
3. 参考故障排查指南
4. 联系开发团队

## 📅 更新日志

- **2025-10-24**: 初始版本发布
  - 完成核心功能实现
  - 创建完整文档
  - 添加快速开始指南

---

**文档维护**: RoboCoin Team  
**反馈**: 如发现文档问题或有改进建议，请提交Issue

