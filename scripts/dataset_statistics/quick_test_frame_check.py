#!/usr/bin/env python3
"""
快速测试帧数一致性检查功能
直接使用已知有问题的文件
"""

import h5py
from pathlib import Path
from collections import Counter
import sys

def test_single_file():
    """测试单个已知有问题的文件"""
    # 使用第198个文件（已知有问题）
    h5_file = Path("/mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批-20250930-32274条/算法采集_PCB/算法采集_PCB抓拿放取_0925_1538/0629_a.h5")
    
    if not h5_file.exists():
        print(f"❌ 文件不存在: {h5_file}")
        return False
    
    print(f"🧪 测试文件: {h5_file.name}")
    print(f"📁 路径: {h5_file.parent.name}\n")
    
    required_h5_paths = [
        'observations/arm/left/joints',
        'observations/arm/left/pose', 
        'observations/arm/left/wrench',
        'observations/timestamp',
        'observations/camera/rgb/head/images',
        'observations/camera/rgb/left/images'
    ]
    
    errors = []
    warnings = []
    
    try:
        with h5py.File(h5_file, 'r') as f:
            # 检查路径存在
            for path in required_h5_paths:
                if path not in f:
                    errors.append(f"H5缺少路径: {path}")
            
            # 检查帧数一致性
            frame_counts = {}
            video_datasets = set()
            
            for path in required_h5_paths:
                if path not in f:
                    continue
                
                dataset = f[path]
                shape = dataset.shape
                
                # 检测视频数据集
                if 'video' in path.lower():
                    video_datasets.add(path)
                    if shape == ():
                        continue
                
                # 对于非视频数据集，检查帧数
                if len(shape) > 0 and shape[0] > 0:
                    frame_counts[path] = shape[0]
                elif len(shape) > 0 and shape[0] == 0:
                    pass  # 空数据集，正常
                elif shape != ():
                    warnings.append(f"数据集 {path} 形状异常: {shape}")
            
            # 检查帧数是否一致
            if len(frame_counts) > 0:
                unique_counts = set(frame_counts.values())
                if len(unique_counts) > 1:
                    # 帧数不一致！
                    count_freq = Counter(frame_counts.values())
                    most_common_count, most_common_freq = count_freq.most_common(1)[0]
                    
                    errors.append(
                        "帧数不一致: " + 
                        ", ".join([f"{path}={count}" for path, count in sorted(frame_counts.items())])
                    )
                    
                    warnings.append(
                        f"最常见帧数: {most_common_count} "
                        f"({most_common_freq}/{len(frame_counts)} 个数据集)"
                    )
                    
                    print("📊 帧数统计:")
                    for count, freq in count_freq.most_common():
                        print(f"  {count}帧: {freq} 个数据集")
                        for path, cnt in frame_counts.items():
                            if cnt == count:
                                print(f"    - {path}")
    
    except Exception as e:
        errors.append(f"H5读取失败: {e}")
    
    # 打印结果
    print(f"\n{'='*60}")
    if len(errors) == 0:
        print("✅ 验证通过")
        return True
    else:
        print(f"❌ 发现 {len(errors)} 个错误:")
        for error in errors:
            print(f"  - {error}")
        
        if warnings:
            print(f"\n⚠️  {len(warnings)} 个警告:")
            for warning in warnings:
                print(f"  - {warning}")
        
        return False

def main():
    print("🚀 帧数一致性检查 - 快速测试\n")
    
    success = test_single_file()
    
    print(f"\n{'='*60}")
    if success:
        print("✅ 测试失败：应该检测到帧数不一致错误")
        print("   （这个文件已知有问题，不应该通过验证）")
        sys.exit(1)
    else:
        print("✅ 测试成功：正确检测到帧数不一致！")
        print("   验证器修复有效")
        sys.exit(0)

if __name__ == "__main__":
    main()
