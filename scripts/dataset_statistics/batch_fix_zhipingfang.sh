#!/bin/bash
# 智平方数据集帧数不一致问题 - 一键修复脚本

set -e  # 遇到错误立即退出

DATASET_ROOT="/mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批-20250930-32274条"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CONFIG_FILE="$PROJECT_ROOT/scripts/format_converters/tolerobot/configs/converter_config_zhipingfang.yaml"

echo "========================================================================"
echo "智平方数据集帧数不一致问题 - 批量修复"
echo "========================================================================"
echo "数据集根目录: $DATASET_ROOT"
echo "配置文件: $CONFIG_FILE"
echo ""

# 检查数据集是否存在
if [ ! -d "$DATASET_ROOT" ]; then
    echo "❌ 错误: 数据集根目录不存在: $DATASET_ROOT"
    echo "   请修改脚本中的 DATASET_ROOT 变量"
    exit 1
fi

# 检查配置文件是否存在
if [ ! -f "$CONFIG_FILE" ]; then
    echo "⚠️  警告: 配置文件不存在: $CONFIG_FILE"
    echo "   将不使用配置文件（检查速度会较慢）"
    CONFIG_ARG=""
else
    CONFIG_ARG="--config $CONFIG_FILE"
fi

# 询问是否先 dry-run
echo "是否先进行 DRY RUN 测试？（推荐）"
read -p "输入 'y' 进行测试，'n' 直接执行，'q' 退出: " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Qq]$ ]]; then
    echo "❌ 用户取消操作"
    exit 0
fi

if [[ $REPLY =~ ^[Yy]$ ]]; then
    DRY_RUN="--dry-run"
    echo "🧪 模式: DRY RUN（不实际移动文件）"
else
    DRY_RUN=""
    echo "⚠️  模式: 实际移动文件"
    echo ""
    echo "⚠️⚠️⚠️  警告 ⚠️⚠️⚠️"
    echo "将移动帧数不一致的文件到 error/ 目录！"
    read -p "确认继续？(输入 'YES' 确认): " CONFIRM
    
    if [ "$CONFIRM" != "YES" ]; then
        echo "❌ 用户取消操作"
        exit 0
    fi
fi

echo ""
echo "========================================================================"
echo "开始处理"
echo "========================================================================"
echo ""

# 统计信息
TOTAL_DATASETS=0
PROCESSED_DATASETS=0
FAILED_DATASETS=0

# 处理每个子数据集
for dataset_dir in "$DATASET_ROOT"/*/; do
    if [ ! -d "$dataset_dir" ]; then
        continue
    fi
    
    dataset_name=$(basename "$dataset_dir")
    TOTAL_DATASETS=$((TOTAL_DATASETS + 1))
    
    echo "========================================================================"
    echo "[$TOTAL_DATASETS] 处理数据集: $dataset_name"
    echo "========================================================================"
    
    # 检查是否有H5文件
    h5_count=$(find "$dataset_dir" -name "*.h5" -not -path "*/error/*" 2>/dev/null | wc -l)
    
    if [ "$h5_count" -eq 0 ]; then
        echo "⏭️  跳过: 没有 H5 文件"
        echo ""
        continue
    fi
    
    echo "📊 发现 $h5_count 个 H5 文件"
    
    # 运行修复脚本
    if python "$PROJECT_ROOT/scripts/dataset_statistics/fix_frame_inconsistency.py" \
        "$dataset_dir" \
        $CONFIG_ARG \
        $DRY_RUN \
        --workers 16; then
        PROCESSED_DATASETS=$((PROCESSED_DATASETS + 1))
        echo "✅ 完成: $dataset_name"
    else
        FAILED_DATASETS=$((FAILED_DATASETS + 1))
        echo "❌ 失败: $dataset_name"
    fi
    
    echo ""
done

# 显示总结
echo "========================================================================"
echo "处理完成"
echo "========================================================================"
echo "总数据集: $TOTAL_DATASETS"
echo "成功处理: $PROCESSED_DATASETS"
echo "失败: $FAILED_DATASETS"
echo ""

if [ -n "$DRY_RUN" ]; then
    echo "🧪 这是 DRY RUN 测试，没有实际移动文件"
    echo ""
    echo "如果结果看起来正确，请重新运行并选择 'n' 来实际执行移动"
else
    echo "✅ 文件已移动到各自的 error/ 目录"
    echo ""
    echo "统计 error 文件:"
    find "$DATASET_ROOT" -name "error" -type d -exec sh -c '
        error_dir="$1"
        parent_dir=$(dirname "$error_dir")
        parent_name=$(basename "$parent_dir")
        count=$(ls -1 "$error_dir" 2>/dev/null | wc -l)
        if [ "$count" -gt 0 ]; then
            echo "  $parent_name: $count 个文件"
        fi
    ' sh {} \;
fi

echo ""
echo "========================================================================"
echo "🎉 完成！"
echo "========================================================================"
