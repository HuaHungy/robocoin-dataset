# 数据库集成配置验证器 - 快速开始

## 🚀 5分钟快速开始

### 1. 准备数据库

首先需要一个包含任务信息的SQLite数据库。如果没有，可以创建一个示例数据库：

```bash
# 进入项目目录
cd /home/liu/program/robocoin-dataset

# 创建数据库目录
mkdir -p db

# 使用Python创建示例数据库
python3 << 'EOF'
import sqlite3
from pathlib import Path

db_path = Path("db/test_datasets.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 创建表
cursor.execute("""
CREATE TABLE IF NOT EXISTS device_model_annotation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_model TEXT NOT NULL,
    device_model_annotation TEXT NOT NULL,
    dataset_path TEXT,
    repo_id TEXT,
    converter_config_path TEXT,
    converter_module TEXT,
    converter_class TEXT
)
""")

# 插入示例数据（根据你的实际数据集修改）
cursor.execute("""
INSERT INTO device_model_annotation 
(device_model, device_model_annotation, dataset_path, repo_id, converter_config_path, converter_module, converter_class)
VALUES 
('yinhe', 'default_version', 
 'data/yinhe:default_version',
 'test/yinhe',
 'scripts/format_converters/tolerobot/configs/converter_config_yinhe.yaml',
 'robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_mp4_json',
 'LerobotFormatConverterMp4Json')
""")

conn.commit()
conn.close()

print(f"✅ 示例数据库已创建: {db_path}")
EOF
```

### 2. 运行验证

```bash
# 基础运行
python scripts/config_validation/db_integrated_validator.py \
  --db-path db/test_datasets.db \
  --num-samples 1

# 查看结果
ls -lh outputs/db_validation/
cat outputs/db_validation/db_validation_report_*.json | python -m json.tool | head -50
```

### 3. 查看报告

```bash
# 查看最新的验证报告
latest_report=$(ls -t outputs/db_validation/db_validation_report_*.json | head -1)
echo "📊 验证报告: $latest_report"
echo ""

# 打印摘要
python3 -c "
import json
with open('$latest_report') as f:
    data = json.load(f)
print('📊 验证摘要:')
print(f\"  总任务数: {data['summary']['total_tasks']}\")
print(f\"  成功: {data['summary']['successful_tasks']}\")
print(f\"  部分成功: {data['summary']['partial_tasks']}\")
print(f\"  失败: {data['summary']['failed_tasks']}\")
"
```

## 📋 典型使用场景

### 场景1: 开发环境测试

```bash
# 只验证本地data目录下的数据集
python scripts/config_validation/db_integrated_validator.py \
  --db-path db/local_datasets.db \
  --num-samples 1 \
  --log-level DEBUG
```

### 场景2: CI/CD集成

```bash
#!/bin/bash
# ci_validate.sh - 在CI/CD中运行

set -e

echo "🔍 运行配置验证..."
python scripts/config_validation/db_integrated_validator.py \
  --db-path db/datasets.db \
  --output-dir ci_outputs/validation \
  --num-samples 2

# 检查验证结果
report=$(ls -t ci_outputs/validation/db_validation_report_*.json | head -1)
failed=$(python3 -c "import json; print(json.load(open('$report'))['summary']['failed_tasks'])")

if [ "$failed" -gt 0 ]; then
    echo "❌ 验证失败: $failed 个任务失败"
    exit 1
else
    echo "✅ 所有任务验证通过"
    exit 0
fi
```

### 场景3: 生产环境验证

```bash
# 完整验证，每个任务抽取5个episodes
python scripts/config_validation/db_integrated_validator.py \
  --db-path /data/production/datasets.db \
  --output-dir /results/validation_$(date +%Y%m%d) \
  --num-samples 5 \
  --log-level INFO

# 生成邮件报告（示例）
python3 scripts/config_validation/generate_email_report.py \
  --report-file /results/validation_$(date +%Y%m%d)/db_validation_report_*.json \
  --send-to team@example.com
```

## 🔍 结果解读

### 验证状态说明

```python
# 成功 (success)
{
  "validation_status": "success",
  "sampled_episodes": [
    {"validation_status": "success"},  # ✅ 所有episodes都成功
    {"validation_status": "success"}
  ]
}

# 部分成功 (partial)
{
  "validation_status": "partial",
  "sampled_episodes": [
    {"validation_status": "success"},   # ✅ 部分成功
    {"validation_status": "failed"}     # ❌ 部分失败
  ]
}

# 失败 (failed)
{
  "validation_status": "failed",
  "errors": ["Task validation error: ..."],  # ❌ 任务级错误
  "sampled_episodes": []
}

# 跳过 (skipped)
{
  "validation_status": "skipped",
  "errors": ["No episodes found for sampling"]  # ⚠️ 未找到episodes
}
```

### 常见错误及解决方案

#### 错误1: Dataset path not found

```json
{
  "errors": ["Dataset path not found: /path/to/dataset"]
}
```

**解决方案**: 更新数据库中的 `dataset_path` 为正确路径

#### 错误2: No episodes found

```json
{
  "errors": ["No episodes found for sampling"]
}
```

**解决方案**: 检查数据集目录结构，确保包含 `local_task_info.yaml` 和episode文件

#### 错误3: Config file not found

```json
{
  "errors": ["Config file not found: configs/..."]
}
```

**解决方案**: 检查 `converter_config_path` 是否正确

## 📊 报告分析工具

### 分析脚本示例

```python
#!/usr/bin/env python3
"""分析验证报告"""
import json
import sys
from pathlib import Path

def analyze_report(report_path):
    with open(report_path) as f:
        data = json.load(f)
    
    print("="*70)
    print("📊 数据库配置验证报告分析")
    print("="*70)
    print()
    
    # 1. 基本统计
    summary = data['summary']
    total = summary['total_tasks']
    success = summary['successful_tasks']
    partial = summary['partial_tasks']
    failed = summary['failed_tasks']
    
    print(f"总任务数: {total}")
    print(f"  ✅ 成功: {success} ({100*success//total}%)")
    print(f"  ⚠️  部分成功: {partial} ({100*partial//total}%)")
    print(f"  ❌ 失败: {failed} ({100*failed//total}%)")
    print()
    
    # 2. 失败任务详情
    if failed > 0:
        print("❌ 失败的任务:")
        for result in data['validation_results']:
            if result['validation_status'] == 'failed':
                print(f"  - {result['task_name']}")
                for error in result.get('errors', []):
                    print(f"    错误: {error}")
        print()
    
    # 3. 部分成功任务详情
    if partial > 0:
        print("⚠️  部分成功的任务:")
        for result in data['validation_results']:
            if result['validation_status'] == 'partial':
                print(f"  - {result['task_name']}")
                for ep in result.get('sampled_episodes', []):
                    if ep['validation_status'] == 'failed':
                        print(f"    Episode {ep['episode_index']}: {ep.get('errors', [])}")
        print()
    
    # 4. 成功率
    success_rate = 100 * success / total if total > 0 else 0
    print(f"总体成功率: {success_rate:.1f}%")
    
    if success_rate == 100:
        print("🎉 所有任务验证通过！")
    elif success_rate >= 80:
        print("✅ 大部分任务验证通过")
    elif success_rate >= 50:
        print("⚠️  约半数任务需要修复")
    else:
        print("❌ 大量任务需要修复")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_report.py <report.json>")
        sys.exit(1)
    
    analyze_report(sys.argv[1])
```

保存为 `scripts/config_validation/analyze_report.py` 并运行：

```bash
python scripts/config_validation/analyze_report.py \
  outputs/db_validation/db_validation_report_*.json
```

## 🔗 相关链接

- [完整用户指南](../../docs/DB_CONFIG_VALIDATOR_USER_GUIDE.md)
- [设计文档](../../docs/DB_INTEGRATED_CONFIG_VALIDATOR_DESIGN.md)
- [Schema Analyzer](schema_analyzer.py)
- [Converter Loader](converter_loader.py)

## 💡 提示

1. **首次运行**: 建议使用 `--num-samples 1` 快速测试
2. **大型数据集**: 注意监控内存使用，特别是MCAP格式
3. **CI集成**: 可以设置失败任务数量阈值来决定是否通过CI
4. **定期验证**: 建议在数据集或配置更新后运行验证

---

**需要帮助?** 查看 [完整用户指南](../../docs/DB_CONFIG_VALIDATOR_USER_GUIDE.md)

