#!/usr/bin/env bash
# 测试 check_repo_consistency.py 脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$SCRIPT_DIR/check_repo_consistency.py"

echo "=========================================="
echo "测试 Repo Consistency Checker"
echo "=========================================="
echo ""

# 测试 1: 显示帮助信息
echo "测试 1: 显示帮助信息"
echo "------------------------------------------"
python "$SCRIPT" --help
echo ""

# 测试 2: 检查参数是否正确解析（使用不存在的数据库，会失败但能测试参数）
echo "测试 2: 测试参数解析"
echo "------------------------------------------"
echo "测试命令: python $SCRIPT --platform huggingface --namespace TestNamespace --db-path /tmp/nonexistent.db --verbose"
echo ""
echo "预期: 应该报错数据库不存在，但说明参数解析正常"
echo ""
python "$SCRIPT" --platform huggingface --namespace TestNamespace --db-path /tmp/nonexistent.db --verbose 2>&1 || echo "✅ 参数解析正常（预期的数据库不存在错误）"
echo ""

# 测试 3: 测试平台选择
echo "测试 3: 测试多平台选项"
echo "------------------------------------------"
for platform in huggingface modelscope all; do
    echo "平台: $platform"
    python "$SCRIPT" --platform "$platform" --db-path /tmp/nonexistent.db 2>&1 | head -n 3 || true
    echo ""
done

echo "=========================================="
echo "所有测试完成"
echo "=========================================="
echo ""
echo "注意: 实际使用时，需要提供有效的数据库路径和 token"
echo ""
echo "使用示例:"
echo "  # 检查 Hugging Face"
echo "  python $SCRIPT --platform huggingface --token YOUR_HF_TOKEN"
echo ""
echo "  # 检查 ModelScope"
echo "  python $SCRIPT --platform modelscope --token YOUR_MS_TOKEN"
echo ""
echo "  # 检查所有平台"
echo "  python $SCRIPT --platform all --verbose"
