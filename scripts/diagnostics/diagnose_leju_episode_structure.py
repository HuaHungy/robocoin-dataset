#!/usr/bin/env python3
"""
诊断Leju数据集结构，找出为什么无法识别episode目录
"""
from pathlib import Path
import json
import sys


def check_episode_dir(dir_path: Path) -> dict:
    """检查一个目录是否是有效的episode目录
    
    Returns:
        dict with keys: is_episode, has_metadata, has_h5, details
    """
    result = {
        "is_episode": False,
        "has_metadata": False,
        "has_h5": False,
        "has_metadata_in_root": False,
        "has_h5_in_root": False,
        "details": []
    }
    
    # 检查 metadata.json
    metadata_path = dir_path / "metadata.json"
    if metadata_path.exists():
        result["has_metadata"] = True
        result["details"].append(f"✅ Found metadata.json")
        try:
            with open(metadata_path) as f:
                metadata = json.load(f)
                task = metadata.get("task", "N/A")
                result["details"].append(f"   Task: {task}")
        except Exception as e:
            result["details"].append(f"   ⚠️  Failed to read: {e}")
    else:
        result["details"].append(f"❌ No metadata.json")
        
        # 检查是否在子目录中
        for subdir in dir_path.iterdir():
            if subdir.is_dir():
                subdir_metadata = subdir / "metadata.json"
                if subdir_metadata.exists():
                    result["details"].append(f"   ℹ️  Found in subdir: {subdir.name}/metadata.json")
                    result["has_metadata_in_root"] = False
                    break
    
    # 检查 proprio_stats/proprio_stats.hdf5
    h5_path = dir_path / "proprio_stats" / "proprio_stats.hdf5"
    if h5_path.exists():
        result["has_h5"] = True
        size_mb = h5_path.stat().st_size / (1024 * 1024)
        result["details"].append(f"✅ Found proprio_stats/proprio_stats.hdf5 ({size_mb:.2f} MB)")
    else:
        result["details"].append(f"❌ No proprio_stats/proprio_stats.hdf5")
        
        # 检查是否proprio_stats目录存在
        proprio_dir = dir_path / "proprio_stats"
        if proprio_dir.exists():
            files = list(proprio_dir.iterdir())
            result["details"].append(f"   ℹ️  proprio_stats/ exists with {len(files)} items:")
            for f in files[:5]:  # 只显示前5个
                result["details"].append(f"      - {f.name}")
            if len(files) > 5:
                result["details"].append(f"      ... and {len(files) - 5} more")
        else:
            result["details"].append(f"   ℹ️  proprio_stats/ directory not found")
            
            # 检查是否在子目录中
            for subdir in dir_path.iterdir():
                if subdir.is_dir():
                    subdir_h5 = subdir / "proprio_stats" / "proprio_stats.hdf5"
                    if subdir_h5.exists():
                        result["details"].append(f"   ℹ️  Found in subdir: {subdir.name}/proprio_stats/...")
                        result["has_h5_in_root"] = False
                        break
    
    result["is_episode"] = result["has_metadata"] and result["has_h5"]
    return result


def diagnose_dataset(dataset_path: str, max_subdirs: int = 10):
    """诊断数据集结构"""
    print("=" * 80)
    print("Leju Episode Structure Diagnostic")
    print("=" * 80)
    print()
    print(f"📂 Dataset path: {dataset_path}")
    print()
    
    path = Path(dataset_path)
    
    if not path.exists():
        print(f"❌ Path does not exist!")
        return
    
    if not path.is_dir():
        print(f"❌ Path is not a directory!")
        return
    
    # 列出所有子目录
    try:
        subdirs = [d for d in path.iterdir() if d.is_dir() and not d.name.startswith('.') and not d.name.startswith('@')]
        print(f"📊 Found {len(subdirs)} subdirectories (excluding hidden/special)")
        print()
    except Exception as e:
        print(f"❌ Failed to list directories: {e}")
        return
    
    # 统计
    stats = {
        "total": len(subdirs),
        "valid_episodes": 0,
        "has_metadata_only": 0,
        "has_h5_only": 0,
        "has_neither": 0,
        "nested_structure": 0
    }
    
    # 检查前N个子目录
    print(f"🔍 Checking first {min(max_subdirs, len(subdirs))} directories:")
    print()
    
    for i, subdir in enumerate(subdirs[:max_subdirs]):
        print(f"{'─' * 80}")
        print(f"Directory {i+1}/{min(max_subdirs, len(subdirs))}: {subdir.name}")
        print(f"{'─' * 80}")
        
        result = check_episode_dir(subdir)
        
        for detail in result["details"]:
            print(f"  {detail}")
        
        print()
        
        if result["is_episode"]:
            stats["valid_episodes"] += 1
            print(f"  🎯 Result: VALID EPISODE ✅")
        elif result["has_metadata"] and not result["has_h5"]:
            stats["has_metadata_only"] += 1
            print(f"  🎯 Result: Has metadata but missing H5 ⚠️")
        elif not result["has_metadata"] and result["has_h5"]:
            stats["has_h5_only"] += 1
            print(f"  🎯 Result: Has H5 but missing metadata ⚠️")
        elif not result["has_metadata_in_root"] or not result["has_h5_in_root"]:
            stats["nested_structure"] += 1
            print(f"  🎯 Result: Possible nested structure (files in subdirs) 🔍")
        else:
            stats["has_neither"] += 1
            print(f"  🎯 Result: NOT an episode (missing both files) ❌")
        
        print()
    
    if len(subdirs) > max_subdirs:
        print(f"{'─' * 80}")
        print(f"ℹ️  Checking remaining {len(subdirs) - max_subdirs} directories (summary only)...")
        print()
        
        for subdir in subdirs[max_subdirs:]:
            result = check_episode_dir(subdir)
            if result["is_episode"]:
                stats["valid_episodes"] += 1
            elif result["has_metadata"] and not result["has_h5"]:
                stats["has_metadata_only"] += 1
            elif not result["has_metadata"] and result["has_h5"]:
                stats["has_h5_only"] += 1
            elif not result["has_metadata_in_root"] or not result["has_h5_in_root"]:
                stats["nested_structure"] += 1
            else:
                stats["has_neither"] += 1
    
    # 打印统计结果
    print("=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    print()
    print(f"Total directories checked: {stats['total']}")
    print(f"  ✅ Valid episodes (has both metadata.json and H5): {stats['valid_episodes']}")
    print(f"  ⚠️  Has metadata only: {stats['has_metadata_only']}")
    print(f"  ⚠️  Has H5 only: {stats['has_h5_only']}")
    print(f"  🔍 Possible nested structure: {stats['nested_structure']}")
    print(f"  ❌ Has neither (not an episode): {stats['has_neither']}")
    print()
    
    # 提供建议
    print("=" * 80)
    print("💡 DIAGNOSIS")
    print("=" * 80)
    print()
    
    if stats["valid_episodes"] == 0:
        print("❌ PROBLEM: No valid episodes found!")
        print()
        if stats["nested_structure"] > 0:
            print("🔍 Possible cause: Episodes are nested deeper (not direct children of dataset_path)")
            print("   Solution: These UUID directories may contain episode subdirectories")
            print("   Action needed: Check one of these directories manually")
        elif stats["has_metadata_only"] > 0 or stats["has_h5_only"] > 0:
            print("🔍 Possible cause: Incomplete episodes (missing metadata or H5)")
            print("   Solution: Check if data collection was interrupted")
        else:
            print("🔍 Possible cause: Wrong dataset_path or unusual structure")
            print("   Solution: Verify the correct dataset path")
    else:
        print(f"✅ SUCCESS: Found {stats['valid_episodes']} valid episodes!")
        print()
        if stats["valid_episodes"] < stats["total"]:
            print(f"⚠️  Note: {stats['total'] - stats['valid_episodes']} directories are not valid episodes")
            print("   This is normal if dataset has other subdirectories")
    
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python diagnose_leju_episode_structure.py <dataset_path> [max_subdirs_to_check]")
        print()
        print("Example:")
        print("  python diagnose_leju_episode_structure.py /path/to/leju/dataset 10")
        sys.exit(1)
    
    dataset_path = sys.argv[1]
    max_subdirs = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    
    diagnose_dataset(dataset_path, max_subdirs)

