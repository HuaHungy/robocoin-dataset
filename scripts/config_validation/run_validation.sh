#!/bin/bash

# 配置验证快速运行脚本

set -e

cd "$(dirname "$0")/../.."

echo "======================================================================="
echo "轻量级配置验证工具"
echo "======================================================================="
echo ""

# 配置
DATABASE="/mnt/db/datasets.db"
CONFIG_DIR="./scripts/format_converters/tolerobot/configs/"
OUTPUT_DIR="./outputs/config_validation"
NUM_DATASETS=2
NUM_EPISODES=2

# 检查数据库是否存在
if [ ! -f "$DATABASE" ]; then
    echo "错误: 数据库不存在: $DATABASE"
    exit 1
fi

# 创建输出目录
mkdir -p "$OUTPUT_DIR"

echo "配置:"
echo "  数据库: $DATABASE"
echo "  配置目录: $CONFIG_DIR"
echo "  输出目录: $OUTPUT_DIR"
echo "  每个model采样: $NUM_DATASETS 个数据集"
echo "  每个数据集采样: $NUM_EPISODES 个episodes"
echo ""
echo "开始验证..."
echo "======================================================================="
echo ""

# 运行验证
python scripts/config_validation/batch_validation.py \
    --database "$DATABASE" \
    --config-dir "$CONFIG_DIR" \
    --output-dir "$OUTPUT_DIR" \
    --num-datasets $NUM_DATASETS \
    --num-episodes $NUM_EPISODES

echo ""
echo "======================================================================="
echo "验证完成！"
echo "======================================================================="
echo "查看报告:"
echo "  总体报告: $OUTPUT_DIR/validation_report.json"
echo "  详细报告: $OUTPUT_DIR/*.txt"
echo ""

