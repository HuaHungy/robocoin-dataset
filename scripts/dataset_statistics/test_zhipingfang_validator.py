#!/usr/bin/env python3
"""
测试智平方数据集验证工具的简化版本
用于快速验证功能是否正常
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, '/home/diy01/dev/robocoin-dataset')

from scripts.dataset_statistics.zhipingfang_dataset_validator import ZhipingfangDatasetValidator

def test_validator():
    """测试验证器基本功能"""
    
    print("=" * 80)
    print("智平方数据集验证工具 - 快速测试")
    print("=" * 80)
    
    # 使用真实路径
    data_root = "/mnt/nas/synnas/docker2/外部数据/智平方"
    
    # 检查路径是否存在
    if not os.path.exists(data_root):
        print(f"❌ 数据根目录不存在: {data_root}")
        return False
    
    print(f"✓ 数据根目录存在: {data_root}\n")
    
    # 创建验证器实例
    try:
        validator = ZhipingfangDatasetValidator(data_root=data_root)
        print("✓ 验证器实例创建成功\n")
    except Exception as e:
        print(f"❌ 创建验证器失败: {e}")
        return False
    
    # 测试步骤1: 查找 YAML 文件
    try:
        print("测试步骤 1: 查找 device_model_annotation.yaml")
        print("-" * 80)
        yaml_files = validator.find_device_yaml_files()
        print(f"\n✓ 找到 {len(yaml_files)} 个 YAML 文件")
        
        if len(yaml_files) == 0:
            print("⚠️  警告: 没有找到 YAML 文件，可能需要手动创建")
            return False
            
    except Exception as e:
        print(f"❌ 查找 YAML 文件失败: {e}")
        return False
    
    # 测试步骤2: 查找 H5 文件（限制数量以加快测试）
    try:
        print("\n测试步骤 2: 查找 H5 文件")
        print("-" * 80)
        h5_files = validator.find_h5_files_around_yaml()
        print(f"\n✓ 找到 {len(h5_files)} 个 H5 文件")
        
        if len(h5_files) == 0:
            print("⚠️  警告: 没有找到 H5 文件")
            return False
        
        # 只分析前5个文件进行测试
        test_count = min(5, len(h5_files))
        validator.h5_files = validator.h5_files[:test_count]
        validator.total_h5_count = test_count
        print(f"\n⚠️  测试模式: 仅分析前 {test_count} 个文件")
        
    except Exception as e:
        print(f"❌ 查找 H5 文件失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 测试步骤3: 分析 H5 文件
    try:
        print("\n测试步骤 3: 分析 H5 文件结构")
        print("-" * 80)
        validator.analyze_h5_files()
        
        valid_count = sum(1 for info in validator.h5_infos.values() if info.is_valid)
        print(f"\n✓ 分析完成: {valid_count}/{test_count} 文件有效")
        
    except Exception as e:
        print(f"❌ 分析 H5 文件失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 测试步骤4: 检查路径一致性
    try:
        print("\n测试步骤 4: 检查路径一致性")
        print("-" * 80)
        consistency_result = validator.check_path_consistency_across_files()
        
        print(f"\n✓ 路径一致性检查完成")
        print(f"  - 多数派出现次数: {consistency_result.get('majority_count', 0)}")
        print(f"  - 异常文件数: {len(consistency_result.get('anomaly_files', []))}")
        print(f"  - 路径变体数: {consistency_result.get('path_variations', 0)}")
        
    except Exception as e:
        print(f"❌ 路径一致性检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "=" * 80)
    print("✓ 所有测试步骤通过！")
    print("=" * 80)
    print("\n可以安全运行完整验证:")
    print("  python scripts/dataset_statistics/zhipingfang_dataset_validator.py --dry-run")
    
    return True

if __name__ == "__main__":
    success = test_validator()
    sys.exit(0 if success else 1)
