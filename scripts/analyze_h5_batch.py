#!/usr/bin/env python3
"""
批量分析H5文件结构脚本
用于分析多个数据集的H5文件内部结构
"""

import sys
from pathlib import Path
import h5py
import numpy as np


def analyze_h5_structure(h5_file_path: Path, max_depth: int = 10):
    """深度分析H5文件结构"""
    print(f"\n{'='*80}")
    print(f"📊 分析文件: {h5_file_path}")
    print(f"📁 文件大小: {h5_file_path.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"{'='*80}\n")
    
    results = {
        "groups": [],
        "datasets": [],
        "total_groups": 0,
        "total_datasets": 0
    }
    
    def visitor(name, obj):
        """递归访问H5对象"""
        depth = name.count('/')
        if depth > max_depth:
            return
        
        indent = "  " * depth
        
        if isinstance(obj, h5py.Group):
            results["groups"].append(name)
            results["total_groups"] += 1
            print(f"{indent}📂 Group: {name}/")
            
        elif isinstance(obj, h5py.Dataset):
            results["datasets"].append(name)
            results["total_datasets"] += 1
            
            shape = obj.shape
            dtype = obj.dtype
            size_mb = obj.size * obj.dtype.itemsize / 1024 / 1024
            
            # 获取数据统计（仅对小型数据集）
            stats_str = ""
            if size_mb < 100:  # 只对小于100MB的数据集计算统计
                try:
                    data = obj[:]
                    if np.issubdtype(dtype, np.number):
                        if data.size > 0:
                            min_val = np.min(data)
                            max_val = np.max(data)
                            mean_val = np.mean(data)
                            std_val = np.std(data)
                            
                            # 检查数据质量
                            zero_count = np.sum(data == 0)
                            zero_ratio = zero_count / data.size
                            
                            stats_str = (
                                f" | min={min_val:.4f}, max={max_val:.4f}, "
                                f"mean={mean_val:.4f}, std={std_val:.4f}, "
                                f"zero_ratio={zero_ratio:.2%}"
                            )
                            
                            # 标记数据质量问题
                            if zero_ratio > 0.95:
                                stats_str += " ⚠️ 全零"
                            elif np.allclose(data, data.flat[0]):
                                stats_str += " ⚠️ 常量"
                except Exception as e:
                    stats_str = f" | 统计失败: {e}"
            else:
                stats_str = " | (数据集过大，跳过统计)"
            
            print(f"{indent}📄 Dataset: {name}")
            print(f"{indent}   Shape: {shape}, Dtype: {dtype}, Size: {size_mb:.2f} MB{stats_str}")
    
    try:
        with h5py.File(h5_file_path, 'r') as f:
            print("🔍 H5文件结构树:\n")
            f.visititems(visitor)
            
        print(f"\n{'='*80}")
        print(f"📊 统计摘要:")
        print(f"   总Groups数: {results['total_groups']}")
        print(f"   总Datasets数: {results['total_datasets']}")
        print(f"{'='*80}\n")
        
        return results
        
    except Exception as e:
        print(f"❌ 分析失败: {e}")
        return None


def main():
    """主函数"""
    # 定义要分析的数据集
    datasets_to_analyze = [
        # Agilex MasterPuppet
        {
            "name": "agilex_cobot_decoupled_magic:masterpuppet_version",
            "path": "data/agilex_cobot_decoupled_magic:masterpuppet_version",
            "sample_file": "episode_4.hdf5"
        },
        # Realman Default
        {
            "name": "realman_rmc_aidal:default_version",
            "path": "data/realman_rmc_aidal:default_version",
            "sample_file": "episode_103.hdf5"
        },
        # Zhipingfang versions
        {
            "name": "zhipingfang:dual_arm_no_pose",
            "path": "data/zhipingfang:dual_arm_no_pose",
            "sample_file": "converted_0294.h5"
        },
        {
            "name": "zhipingfang:dual_arm_no_pose_compressed_video",
            "path": "data/zhipingfang:dual_arm_no_pose_compressed_video",
            "sample_file": "compressed_converted_1490.h5"
        },
        {
            "name": "zhipingfang:dual_arm_with_pose",
            "path": "data/zhipingfang:dual_arm_with_pose",
            "sample_file": "converted_0707.h5"
        },
        {
            "name": "zhipingfang:dual_arm_with_pose_compressed_video",
            "path": "data/zhipingfang:dual_arm_with_pose_compressed_video",
            "sample_file": "compressed_converted_1486.h5"
        },
        {
            "name": "zhipingfang:dual_arm_with_pose_no_left_chest_cam",
            "path": "data/zhipingfang:dual_arm_with_pose_no_left_chest_cam",
            "sample_file": "converted_1474.h5"
        },
        {
            "name": "zhipingfang:left_arm_with_pose",
            "path": "data/zhipingfang:left_arm_with_pose",
            "sample_file": "1088.h5"
        },
        {
            "name": "zhipingfang:right_arm_with_pose",
            "path": "data/zhipingfang:right_arm_with_pose",
            "sample_file": "converted_0195.h5"
        },
    ]
    
    all_results = {}
    
    for dataset in datasets_to_analyze:
        dataset_name = dataset["name"]
        h5_file = Path(dataset["path"]) / dataset["sample_file"]
        
        if not h5_file.exists():
            print(f"\n⚠️ 跳过 {dataset_name}: 文件不存在 {h5_file}")
            continue
        
        print(f"\n\n{'#'*80}")
        print(f"# 数据集: {dataset_name}")
        print(f"{'#'*80}")
        
        results = analyze_h5_structure(h5_file)
        if results:
            all_results[dataset_name] = results
    
    # 生成汇总报告
    print(f"\n\n{'='*80}")
    print("📋 全部数据集汇总")
    print(f"{'='*80}\n")
    
    for dataset_name, results in all_results.items():
        print(f"{dataset_name}:")
        print(f"  Groups: {results['total_groups']}, Datasets: {results['total_datasets']}")
    
    print(f"\n✅ 分析完成！共分析 {len(all_results)} 个数据集")


if __name__ == "__main__":
    main()

