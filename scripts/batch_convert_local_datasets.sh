#!/bin/bash
# 批量转换本地数据集脚本
# 用法: bash scripts/batch_convert_local_datasets.sh

set -e  # 遇到错误立即退出

PROJECT_ROOT="/home/liu/program/robocoin-dataset"
cd "$PROJECT_ROOT"

export PYTHONPATH="$PROJECT_ROOT/src:$PYTHONPATH"

# 日志目录
LOG_DIR="$PROJECT_ROOT/outputs/batch_conversion_logs"
mkdir -p "$LOG_DIR"

# 时间戳
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BATCH_LOG="$LOG_DIR/batch_conversion_$TIMESTAMP.log"

echo "======================================" | tee -a "$BATCH_LOG"
echo "🚀 批量转换开始: $(date)" | tee -a "$BATCH_LOG"
echo "======================================" | tee -a "$BATCH_LOG"
echo "" | tee -a "$BATCH_LOG"

# 成功和失败计数
SUCCESS_COUNT=0
FAILED_COUNT=0
SKIPPED_COUNT=0

# 定义要转换的数据集列表（优先级顺序）
# 格式: "device_model:version|数据格式|优先级"
DATASETS=(
    # 已验证的数据集
    "ruantong_a2d:default_version|H5+JPG|high"
    "ruantong_a2d:gt01_no_depth|H5+JPG|high"
    
    # 可立即测试的数据集
    "agilex_cobot_decoupled_magic:mult_sensor|JPG+JSON|high"
    "agilex_cobot_decoupled_magic:masterpuppet_version|H5|high"
    "zhipingfang:dual_arm_no_pose|JPG+JSON|high"
    "zhipingfang:dual_arm_with_pose|JPG+JSON|high"
    "realman_rmc_aidal:default_version|ROSBAG|medium"
    "realman_rmc_aidal:mcap_version|MCAP|medium"
    "leju_robot:waibu_version|LEJU_WAIBU|medium"
    
    # MMK2格式
    "discover_robotics_aitbot_mmk2:third_view|MMK2|medium"
    
    # 其他未测试的数据集
    "agilex_cobot_decoupled_magic:h5_mp4|H5+MP4|low"
    "agilex_cobot_decoupled_magic:h5_mp4_new|H5+MP4|low"
    "galaxea_r1_lite:default_version|H5|low"
    "zhipingfang:dual_arm_no_pose_compressed_video|JPG+JSON|low"
    "zhipingfang:dual_arm_with_pose_compressed_video|JPG+JSON|low"
    "zhipingfang:dual_arm_with_pose_no_left_chest_cam|JPG+JSON|low"
    "zhipingfang:left_arm_with_pose|JPG+JSON|low"
    "zhipingfang:right_arm_with_pose|JPG+JSON|low"
    
    # 有已知问题的数据集（最后尝试）
    # "yinhe:default_version|MP4+JSON|skip"  # 帧数不匹配
    # "galaxea_r1_lite:h5_mp4_version|H5+MP4|skip"  # 视频损坏
)

# 转换单个数据集的函数
convert_dataset() {
    local dataset_info="$1"
    local device_model_version="${dataset_info%%|*}"
    local remaining="${dataset_info#*|}"
    local data_format="${remaining%%|*}"
    local priority="${remaining##*|}"
    
    local device_model="${device_model_version%:*}"
    local version="${device_model_version#*:}"
    
    # 检查数据集是否存在
    local dataset_path="$PROJECT_ROOT/data/$device_model_version"
    if [ ! -d "$dataset_path" ]; then
        echo "⏭️  跳过: $device_model_version (数据集不存在)" | tee -a "$BATCH_LOG"
        ((SKIPPED_COUNT++))
        return 0
    fi
    
    # 输出目录
    local output_path="$PROJECT_ROOT/outputs/converted_${device_model}_${version}"
    local repo_id="test/${device_model}_${version}"
    
    echo "" | tee -a "$BATCH_LOG"
    echo "===========================================" | tee -a "$BATCH_LOG"
    echo "📦 开始转换: $device_model_version" | tee -a "$BATCH_LOG"
    echo "   格式: $data_format" | tee -a "$BATCH_LOG"
    echo "   优先级: $priority" | tee -a "$BATCH_LOG"
    echo "   时间: $(date)" | tee -a "$BATCH_LOG"
    echo "===========================================" | tee -a "$BATCH_LOG"
    
    # 如果输出目录已存在，询问是否覆盖（自动模式下跳过）
    if [ -d "$output_path" ]; then
        echo "⚠️  输出目录已存在，跳过: $output_path" | tee -a "$BATCH_LOG"
        ((SKIPPED_COUNT++))
        return 0
    fi
    
    # 运行转换
    local convert_log="$LOG_DIR/convert_${device_model}_${version}_$TIMESTAMP.log"
    
    if python scripts/format_converters/tolerobot/convert2lerobot.py \
        --dataset_path "$dataset_path" \
        --output_path "$output_path" \
        --device_model "$device_model" \
        --device_model_version "$version" \
        --factory_config_path "scripts/format_converters/tolerobot/configs/converter_factory_config.yaml" \
        --repo_id "$repo_id" \
        --log_dir "outputs/conversion_logs" \
        --image_writer_processes 4 \
        --image_writer_threads 4 \
        --video_backend pyav \
        > "$convert_log" 2>&1; then
        
        echo "✅ 成功: $device_model_version" | tee -a "$BATCH_LOG"
        ((SUCCESS_COUNT++))
        
        # 检查生成的mapping文件
        if [ -f "$output_path/episode_source_mapping.json" ]; then
            echo "   ✅ episode_source_mapping.json 已生成" | tee -a "$BATCH_LOG"
        fi
        if [ -f "$output_path/original_data_paths.json" ]; then
            echo "   ✅ original_data_paths.json 已生成" | tee -a "$BATCH_LOG"
        fi
    else
        echo "❌ 失败: $device_model_version" | tee -a "$BATCH_LOG"
        echo "   详细日志: $convert_log" | tee -a "$BATCH_LOG"
        ((FAILED_COUNT++))
    fi
}

# 主循环：按优先级转换
echo "📋 计划转换 ${#DATASETS[@]} 个数据集" | tee -a "$BATCH_LOG"
echo "" | tee -a "$BATCH_LOG"

for dataset in "${DATASETS[@]}"; do
    priority="${dataset##*|}"
    
    # 跳过标记为skip的数据集
    if [ "$priority" == "skip" ]; then
        continue
    fi
    
    convert_dataset "$dataset"
done

# 最终统计
echo "" | tee -a "$BATCH_LOG"
echo "======================================" | tee -a "$BATCH_LOG"
echo "🏁 批量转换完成: $(date)" | tee -a "$BATCH_LOG"
echo "======================================" | tee -a "$BATCH_LOG"
echo "" | tee -a "$BATCH_LOG"
echo "📊 转换统计:" | tee -a "$BATCH_LOG"
echo "   ✅ 成功: $SUCCESS_COUNT" | tee -a "$BATCH_LOG"
echo "   ❌ 失败: $FAILED_COUNT" | tee -a "$BATCH_LOG"
echo "   ⏭️  跳过: $SKIPPED_COUNT" | tee -a "$BATCH_LOG"
echo "" | tee -a "$BATCH_LOG"
echo "📝 批量日志: $BATCH_LOG" | tee -a "$BATCH_LOG"
echo "" | tee -a "$BATCH_LOG"

# 生成汇总报告
SUMMARY_FILE="$PROJECT_ROOT/outputs/batch_conversion_summary_$TIMESTAMP.txt"
cat > "$SUMMARY_FILE" << SUMMARY_EOF
批量转换汇总报告
=================

转换时间: $(date)
总数据集: ${#DATASETS[@]}

统计结果:
- 成功: $SUCCESS_COUNT
- 失败: $FAILED_COUNT
- 跳过: $SKIPPED_COUNT

详细日志: $BATCH_LOG

成功转换的数据集可在以下目录查看:
$PROJECT_ROOT/outputs/converted_*

SUMMARY_EOF

echo "📄 汇总报告已保存: $SUMMARY_FILE" | tee -a "$BATCH_LOG"

# 根据结果返回退出码
if [ $FAILED_COUNT -gt 0 ]; then
    exit 1
else
    exit 0
fi

