#!/bin/bash
# 星海图 AV1 视频问题快速修复脚本

echo "======================================================================"
echo "🔧 星海图 AV1 视频解码支持安装"
echo "======================================================================"

# 检测环境
if command -v conda &> /dev/null; then
    echo "✅ 检测到 conda 环境"
    echo ""
    echo "📦 安装 AV1 解码器和 OpenCV..."
    echo ""
    
    # 方法1: conda 安装（最可靠）
    echo "执行命令："
    echo "  conda install -c conda-forge dav1d opencv -y"
    echo ""
    read -p "是否执行安装? (y/n) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        conda install -c conda-forge dav1d opencv -y
        
        echo ""
        echo "✅ 安装完成"
        echo ""
        echo "🧪 测试视频读取..."
        python3 scripts/dataset_statistics/test_galaxea_video_local.py
    fi
    
elif command -v apt-get &> /dev/null; then
    echo "✅ 检测到 apt 包管理器"
    echo ""
    echo "📦 安装系统依赖..."
    echo ""
    
    # 方法2: apt 安装系统库
    echo "执行命令："
    echo "  sudo apt-get update"
    echo "  sudo apt-get install -y libdav1d-dev libavcodec-dev libavformat-dev libavutil-dev libswscale-dev"
    echo "  pip uninstall -y opencv-python opencv-contrib-python"
    echo "  pip install --no-binary opencv-python opencv-python"
    echo ""
    read -p "是否执行安装? (y/n) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo apt-get update
        sudo apt-get install -y \
            libdav1d-dev \
            libavcodec-dev \
            libavformat-dev \
            libavutil-dev \
            libswscale-dev
        
        pip uninstall -y opencv-python opencv-contrib-python
        pip install --no-binary opencv-python opencv-python
        
        echo ""
        echo "✅ 安装完成"
        echo ""
        echo "🧪 测试视频读取..."
        python3 scripts/dataset_statistics/test_galaxea_video_local.py
    fi
    
else
    echo "❌ 未检测到 conda 或 apt-get"
    echo ""
    echo "请手动选择以下方法之一："
    echo ""
    echo "方法1: 使用 PyAV 库（最简单）"
    echo "  pip install av"
    echo "  然后修改转换器代码使用 PyAV"
    echo ""
    echo "方法2: 转换视频为 H.264 格式"
    echo "  使用 convert_av1_to_h264.py 脚本"
    echo ""
    echo "详见: docs/GALAXEA_AV1_VIDEO_FIX.md"
fi

echo ""
echo "======================================================================"
