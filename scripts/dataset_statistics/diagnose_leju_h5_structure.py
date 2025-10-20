#!/usr/bin/env python3
"""
诊断乐聚H5文件结构，列出所有数据集路径

用法：
  python3 scripts/dataset_statistics/diagnose_leju_h5_structure.py <h5_file_path>

示例：
  python3 scripts/dataset_statistics/diagnose_leju_h5_structure.py \
    /mnt/nas/synnas/docker2/外部数据/乐聚2/hotel_services_wy/hotel_services/front_desk/customer_check_in/001b8a0d-e7af-41ff-bb8f-aa33785948e4/data.h5
"""

import argparse
import sys
from pathlib import Path

import h5py


def print_h5_structure(h5_file_path: Path):
    """打印H5文件的完整结构"""
    
    if not h5_file_path.exists():
        print(f"❌ 文件不存在: {h5_file_path}")
        return
    
    file_size = h5_file_path.stat().st_size / 1024 / 1024
    print(f"\n{'='*80}")
    print(f"📁 H5文件: {h5_file_path.name}")
    print(f"📂 完整路径: {h5_file_path}")
    print(f"💾 文件大小: {file_size:.2f} MB")
    print(f"{'='*80}\n")
    
    try:
        with h5py.File(h5_file_path, "r") as f:
            # 收集所有数据集
            datasets = []
            groups = []
            
            def collect_items(name, obj):
                if isinstance(obj, h5py.Dataset):
                    datasets.append((name, obj.shape, obj.dtype))
                elif isinstance(obj, h5py.Group):
                    groups.append(name)
            
            f.visititems(collect_items)
            
            # 打印组（目录）
            print(f"📂 组（共 {len(groups)} 个）:")
            for group_name in sorted(groups):
                print(f"   📁 {group_name}/")
            
            print(f"\n📊 数据集（共 {len(datasets)} 个）:")
            
            # 按类别分组打印
            categories = {}
            for name, shape, dtype in datasets:
                category = name.split('/')[0] if '/' in name else 'root'
                if category not in categories:
                    categories[category] = []
                categories[category].append((name, shape, dtype))
            
            for category in sorted(categories.keys()):
                print(f"\n   🏷️  {category.upper()}:")
                for name, shape, dtype in sorted(categories[category]):
                    shape_str = ' x '.join(map(str, shape))
                    print(f"      ✓ {name:50s} | shape: {shape_str:20s} | dtype: {dtype}")
            
            # 检查配置中期望的路径
            print(f"\n{'='*80}")
            print(f"🔍 检查配置中期望的路径:")
            print(f"{'='*80}\n")
            
            expected_paths = [
                "state/joint/position",
                "state/leg/position",
                "state/effector/position(dexhand)",
                "state/head/position",
                "state/joint/velocity",
                "action/joint/position",
                "action/leg/position",
                "action/effector/position(dexhand)",
                "action/head/position",
            ]
            
            found_count = 0
            missing_count = 0
            
            for path in expected_paths:
                if path in f:
                    shape = f[path].shape
                    dtype = f[path].dtype
                    print(f"   ✅ {path:50s} | shape: {shape} | dtype: {dtype}")
                    found_count += 1
                else:
                    print(f"   ❌ {path:50s} | 不存在")
                    missing_count += 1
            
            print(f"\n{'='*80}")
            print(f"✅ 找到: {found_count}/{len(expected_paths)}")
            print(f"❌ 缺失: {missing_count}/{len(expected_paths)}")
            print(f"{'='*80}\n")
            
            if missing_count > 0:
                print("💡 建议:")
                print("   1. 检查 H5 文件是否完整")
                print("   2. 确认数据采集时是否记录了所有必需的数据项")
                print("   3. 更新配置文件使用实际存在的路径")
                print("   4. 如果路径名称不同，查找相似的路径并更新配置\n")
    
    except Exception as e:
        print(f"❌ 读取H5文件失败: {e}")
        return


def main():
    parser = argparse.ArgumentParser(
        description="诊断乐聚H5文件结构",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "h5_file",
        type=str,
        help="H5文件路径",
    )
    
    args = parser.parse_args()
    h5_file_path = Path(args.h5_file)
    
    print_h5_structure(h5_file_path)


if __name__ == "__main__":
    main()
