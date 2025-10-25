#!/bin/bash

# 批量Schema Discovery快速启动脚本
# 用法: ./run_batch_discovery.sh [num_samples] [num_episodes]

set -e  # 遇到错误立即退出

# 默认参数
NUM_SAMPLES=${1:-5}
NUM_EPISODES=${2:-5}

# 项目路径（根据实际情况调整）
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT_DIR="$PROJECT_ROOT/scripts/dataset_schema_discovery"

# 数据库路径（根据实际情况调整）
DATABASE_PATH="/mnt/nas/synnas/database/robocoin.db"

# 配置文件目录
CONFIG_DIR="$PROJECT_ROOT/scripts/format_converters/tolerobot/configs"

# 输出目录（使用时间戳）
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="$PROJECT_ROOT/outputs/schema_discovery_$TIMESTAMP"

echo "=================================="
echo "批量Schema Discovery"
echo "=================================="
echo "项目根目录: $PROJECT_ROOT"
echo "数据库路径: $DATABASE_PATH"
echo "配置目录: $CONFIG_DIR"
echo "输出目录: $OUTPUT_DIR"
echo "采样设置: 每个device_model ${NUM_SAMPLES}个数据集, 每个数据集${NUM_EPISODES}个episodes"
echo "=================================="
echo ""

# 检查数据库是否存在
if [ ! -f "$DATABASE_PATH" ]; then
    echo "❌ 错误: 数据库文件不存在: $DATABASE_PATH"
    echo "请修改脚本中的 DATABASE_PATH 变量"
    exit 1
fi

# 检查配置目录是否存在
if [ ! -d "$CONFIG_DIR" ]; then
    echo "❌ 错误: 配置目录不存在: $CONFIG_DIR"
    echo "请修改脚本中的 CONFIG_DIR 变量"
    exit 1
fi

# 创建输出目录
mkdir -p "$OUTPUT_DIR"

# 激活虚拟环境（如果使用uv）
if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    echo "激活Python虚拟环境..."
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# 运行批量分析
echo "开始运行批量Schema Discovery..."
echo ""

cd "$SCRIPT_DIR"

python batch_schema_discovery.py \
    --database "$DATABASE_PATH" \
    --config-dir "$CONFIG_DIR" \
    --output-dir "$OUTPUT_DIR" \
    --num-samples "$NUM_SAMPLES" \
    --num-episodes "$NUM_EPISODES" \
    --verbose \
    2>&1 | tee "$OUTPUT_DIR/execution.log"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "=================================="
    echo "✅ 批量分析完成！"
    echo "=================================="
    echo "输出目录: $OUTPUT_DIR"
    echo ""
    echo "查看结果:"
    echo "  总体报告:   cat $OUTPUT_DIR/overall_report.json | jq"
    echo "  Schema文件: ls $OUTPUT_DIR/schemas/"
    echo "  诊断文件:   ls $OUTPUT_DIR/diagnoses/"
    echo "  执行日志:   cat $OUTPUT_DIR/execution.log"
    echo "=================================="
else
    echo ""
    echo "=================================="
    echo "❌ 批量分析失败 (退出码: $EXIT_CODE)"
    echo "=================================="
    echo "请查看日志: $OUTPUT_DIR/execution.log"
    echo "=================================="
    exit $EXIT_CODE
fi

