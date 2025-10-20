#!/usr/bin/env python3
"""
快速测试智平方数据集中帧数不一致的问题

测试结果将显示：
1. 有多少episodes存在帧数不一致
2. 不一致的模式（哪些路径不一致）
3. 是否是普遍问题还是个例
"""

import h5py
from pathlib import Path
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed

def check_frame_consistency(h5_file_path):
    """检查单个H5文件的帧数一致性"""
    required_paths = [
        'observations/arm/left/joints',
        'observations/arm/left/pose',
        'observations/arm/left/wrench',
        'observations/timestamp',
        'observations/camera/rgb/head/images',
        'observations/camera/rgb/left/images'
    ]
    
    try:
        with h5py.File(h5_file_path, 'r') as f:
            frame_counts = {}
            
            for path in required_paths:
                if path in f:
                    shape = f[path].shape
                    if 'video' in path.lower() and shape == ():
                        continue  # 视频压缩格式
                    if len(shape) > 0 and shape[0] > 0:
                        frame_counts[path] = shape[0]
            
            if len(frame_counts) == 0:
                return None  # 无有效数据
            
            unique_counts = set(frame_counts.values())
            if len(unique_counts) > 1:
                # 帧数不一致
                return {
                    'file': str(h5_file_path),
                    'frame_counts': frame_counts,
                    'inconsistent': True
                }
            else:
                return {
                    'file': str(h5_file_path),
                    'frame_count': list(unique_counts)[0],
                    'inconsistent': False
                }
    except Exception as e:
        return {
            'file': str(h5_file_path),
            'error': str(e),
            'inconsistent': False
        }

def main():
    dataset_path = Path("/mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批-20250930-32274条/算法采集_PCB")
    
    print(f"🔍 扫描数据集: {dataset_path.name}\n")
    
    # 查找所有H5文件
    h5_files = sorted(list(dataset_path.rglob("*.h5")))
    print(f"📊 找到 {len(h5_files)} 个H5文件")
    
    # 限制测试数量（可调整）
    max_test = min(500, len(h5_files))  # 测试前500个
    print(f"🎯 测试前 {max_test} 个文件\n")
    
    inconsistent_count = 0
    consistent_count = 0
    error_count = 0
    inconsistency_patterns = defaultdict(int)
    
    # 多进程检查
    with ProcessPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(check_frame_consistency, h5_file): h5_file 
                   for h5_file in h5_files[:max_test]}
        
        for i, future in enumerate(as_completed(futures), 1):
            if i % 50 == 0:
                print(f"  进度: {i}/{max_test}")
            
            try:
                result = future.result()
                if result is None:
                    continue
                
                if result.get('error'):
                    error_count += 1
                elif result['inconsistent']:
                    inconsistent_count += 1
                    # 记录不一致模式
                    counts_tuple = tuple(sorted(result['frame_counts'].items()))
                    inconsistency_patterns[counts_tuple] += 1
                else:
                    consistent_count += 1
            except Exception as e:
                error_count += 1
    
    # 打印结果
    print(f"\n" + "="*60)
    print(f"📊 测试结果总结")
    print(f"="*60)
    print(f"✅ 帧数一致: {consistent_count} ({consistent_count/max_test*100:.1f}%)")
    print(f"❌ 帧数不一致: {inconsistent_count} ({inconsistent_count/max_test*100:.1f}%)")
    print(f"⚠️  错误/跳过: {error_count} ({error_count/max_test*100:.1f}%)")
    
    if inconsistent_count > 0:
        print(f"\n📋 不一致模式分析:")
        for pattern, count in sorted(inconsistency_patterns.items(), key=lambda x: -x[1]):
            print(f"\n  模式 (出现{count}次):")
            for path, frame_count in pattern:
                print(f"    {path}: {frame_count}帧")
    
    # 结论
    print(f"\n" + "="*60)
    print(f"💡 结论:")
    if inconsistent_count > max_test * 0.1:
        print(f"   ⚠️  {inconsistent_count/max_test*100:.1f}% 的episodes存在帧数不一致")
        print(f"   这是一个普遍性的数据质量问题！")
        print(f"\n   建议：")
        print(f"   1. 检查数据采集脚本")
        print(f"   2. 确认timestamp为什么只有66帧")
        print(f"   3. 考虑修复转换器以处理这种情况")
    elif inconsistent_count > 0:
        print(f"   约 {inconsistent_count} 个episodes存在帧数不一致（个例）")
        print(f"   建议移动这些episodes到error/文件夹")
    else:
        print(f"   ✅ 所有测试的episodes帧数一致")

if __name__ == "__main__":
    main()
