#!/bin/bash
#
# 查找所有验证器创建的error文件夹位置
# 
# 使用方法:
#   bash find_error_folders.sh
#

echo "=========================================="
echo "查找所有数据集的error文件夹"
echo "=========================================="
echo ""

# 1. 银河数据集
echo "📁 1. 银河(Yinhe)数据集"
echo "   基础路径: /mnt/nas/synnas/docker/外部数据/银河通用"
echo "   Error文件夹结构: task_name/robot_id/error/"
echo ""
yinhe_errors=$(find /mnt/nas/synnas/docker/外部数据/银河通用 -type d -name "error" 2>/dev/null | wc -l)
echo "   找到 $yinhe_errors 个error文件夹"
if [ $yinhe_errors -gt 0 ]; then
    echo "   示例路径:"
    find /mnt/nas/synnas/docker/外部数据/银河通用 -type d -name "error" 2>/dev/null | head -3
    echo ""
    echo "   统计每个error文件夹中的episode数:"
    find /mnt/nas/synnas/docker/外部数据/银河通用 -type d -name "error" 2>/dev/null | while read dir; do
        count=$(find "$dir" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)
        if [ $count -gt 0 ]; then
            echo "     $dir: $count episodes"
        fi
    done | head -10
fi
echo ""
echo "----------------------------------------"
echo ""

# 2. 软通天擎数据集
echo "📁 2. 软通天擎(Ruantong)数据集"
echo "   基础路径: /mnt/nas/synnas/docker2/外部数据/软通天擎"
echo "   Error文件夹结构: dataset_name/error/"
echo ""
ruantong_errors=$(find /mnt/nas/synnas/docker2/外部数据/软通天擎 -type d -name "error" 2>/dev/null | wc -l)
echo "   找到 $ruantong_errors 个error文件夹"
if [ $ruantong_errors -gt 0 ]; then
    echo "   示例路径:"
    find /mnt/nas/synnas/docker2/外部数据/软通天擎 -type d -name "error" 2>/dev/null | head -3
fi
echo ""
echo "----------------------------------------"
echo ""

# 3. 智平方数据集
echo "📁 3. 智平方(Zhipingfang)数据集"
echo "   基础路径: (需要提供具体路径)"
echo ""
echo "----------------------------------------"
echo ""

# 4. 睿尔曼数据集
echo "📁 4. 睿尔曼(Realman)数据集"
echo "   基础路径: /mnt/nas/synnas/docker2/外部数据/外来睿尔曼2000条"
echo "   Error文件夹结构: task_name/error/"
echo ""
realman_errors=$(find /mnt/nas/synnas/docker2/外部数据/外来睿尔曼2000条 -type d -name "error" 2>/dev/null | wc -l)
echo "   找到 $realman_errors 个error文件夹"
if [ $realman_errors -gt 0 ]; then
    echo "   示例路径:"
    find /mnt/nas/synnas/docker2/外部数据/外来睿尔曼2000条 -type d -name "error" 2>/dev/null | head -3
fi
echo ""
echo "----------------------------------------"
echo ""

# 5. 星海图数据集
echo "📁 5. 星海图(Galaxea)数据集"
echo "   基础路径: /mnt/nas/synnas/docker/外部数据/星海图外部1.5w/videos/train"
echo "   Error文件夹结构: task_name/error/"
echo ""
galaxea_errors=$(find /mnt/nas/synnas/docker/外部数据/星海图外部1.5w/videos/train -type d -name "error" 2>/dev/null | wc -l)
echo "   找到 $galaxea_errors 个error文件夹"
if [ $galaxea_errors -gt 0 ]; then
    echo "   示例路径:"
    find /mnt/nas/synnas/docker/外部数据/星海图外部1.5w/videos/train -type d -name "error" 2>/dev/null | head -3
fi
echo ""
echo "----------------------------------------"
echo ""

# 6. 乐聚数据集
echo "📁 6. 乐聚(Leju)数据集"
echo "   基础路径: /mnt/nas/synnas/docker2/外部数据/乐聚2"
echo "   Error文件夹结构: task/subtask/error/"
echo ""
leju_errors=$(find /mnt/nas/synnas/docker2/外部数据/乐聚2 -type d -name "error" 2>/dev/null | wc -l)
echo "   找到 $leju_errors 个error文件夹"
if [ $leju_errors -gt 0 ]; then
    echo "   示例路径:"
    find /mnt/nas/synnas/docker2/外部数据/乐聚2 -type d -name "error" 2>/dev/null | head -3
fi
echo ""
echo "=========================================="
echo "总结"
echo "=========================================="
echo "所有验证器的error文件夹位置规则:"
echo ""
echo "  银河: /path/to/task/robot_id/error/episode_name/"
echo "  软通: /path/to/dataset/error/episode_id/"
echo "  智平方: /path/to/dataset/error/episode_name/"
echo "  睿尔曼: /path/to/task/error/episode_folder/"
echo "  星海图: /path/to/task/error/episode_folder/"
echo "  乐聚: /path/to/subtask/error/episode_uuid/"
echo ""
echo "注意: error文件夹与episode的原始位置在同一父目录下"
echo "=========================================="
