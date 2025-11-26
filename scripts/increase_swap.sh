#!/bin/bash
# 临时增加swap空间到8GB

echo "当前swap状态:"
free -h
echo ""
swapon --show
echo ""

# 检查是否已有额外的swap文件
if [ -f /swapfile_extra ]; then
    echo "额外的swap文件已存在，先关闭它..."
    sudo swapoff /swapfile_extra
    sudo rm -f /swapfile_extra
fi

echo "创建6GB额外swap文件（总共8GB）..."
sudo fallocate -l 300G /swapfile_extra
sudo chmod 600 /swapfile_extra
sudo mkswap /swapfile_extra
sudo swapon /swapfile_extra

echo ""
echo "新的swap状态:"
free -h
echo ""
swapon --show
echo ""
echo "✅ Swap空间已增加到8GB!"
