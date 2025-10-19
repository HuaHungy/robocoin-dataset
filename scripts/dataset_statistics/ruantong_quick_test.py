#!/usr/bin/env python3
"""
软通天擎数据集预转换验证工具 - 简化测试版

快速测试版本，用于调试和验证核心逻辑
"""

import sys
from pathlib import Path

import h5py
import yaml


def find_episodes_fast(base_dir: Path, max_count: int = 10) -> list:
    """快速查找 episode（限制数量用于测试）"""
    episodes = []
    
    def search(directory: Path, depth: int = 0):
        if depth > 6 or len(episodes) >= max_count:
            return
        
        h5_file = directory / "aligned_joints.h5"
        if h5_file.exists():
            episodes.append(directory)
            return
        
        try:
            for child in directory.iterdir():
                if child.is_dir() and not child.name.startswith('.'):
                    search(child, depth + 1)
        except (PermissionError, OSError):
            pass
    
    search(base_dir)
    return episodes


def main():
    data_root = Path("/mnt/nas/synnas/docker2/外部数据/软通天擎")
    config_dir = Path("scripts/format_converters/tolerobot/configs")
    
    print("=" * 80)
    print("软通天擎快速测试")
    print("=" * 80)
    
    # 1. 发现版本
    print("\\n步骤 1: 发现版本")
    version_dirs = [d for d in data_root.iterdir() 
                   if d.is_dir() and d.name not in ['config', 'error']]
    print(f"找到 {len(version_dirs)} 个版本: {[d.name for d in version_dirs]}")
    
    # 2. 查找配置
    print("\\n步骤 2: 匹配配置")
    for ver_dir in version_dirs:
        pattern = f"converter_config_ruantong_{ver_dir.name}*.yaml"
        configs = list(config_dir.glob(pattern))
        print(f"  {ver_dir.name}: {configs[0].name if configs else '无配置'}")
    
    # 3. 快速查找episode（每个版本最多10个）
    print("\\n步骤 3: 快速索引 Episode（每版本最多10个）")
    for ver_dir in sorted(version_dirs):
        print(f"  正在扫描 {ver_dir.name}...")
        episodes = find_episodes_fast(ver_dir, max_count=10)
        print(f"  {ver_dir.name}: 找到 {len(episodes)} 个 episode")
        
        if episodes:
            print(f"    示例: {episodes[0].relative_to(data_root)}")
    
    # 4. 验证一个 episode
    print("\\n步骤 4: 验证示例 Episode")
    test_version = version_dirs[0]
    test_episodes = find_episodes_fast(test_version, max_count=1)
    
    if not test_episodes:
        print("  未找到测试 episode")
        return
    
    test_ep = test_episodes[0]
    print(f"  测试: {test_ep.relative_to(data_root)}")
    
    # 检查结构
    h5_file = test_ep / "aligned_joints.h5"
    camera_dir = test_ep / "camera"
    meta_file = test_ep / "meta_info.json"
    
    print(f"    aligned_joints.h5: {'✓' if h5_file.exists() else '✗'}")
    print(f"    camera/: {'✓' if camera_dir.exists() else '✗'}")
    print(f"    meta_info.json: {'✓' if meta_file.exists() else '✗'}")
    
    # 检查 H5 内容
    if h5_file.exists():
        try:
            with h5py.File(h5_file, 'r') as f:
                print(f"\\n    H5 Groups:")
                for key in list(f.keys())[:5]:
                    print(f"      - {key}")
                
                # 查看 state 结构
                if 'state' in f:
                    print(f"\\n    state/ 结构:")
                    def show_structure(name, obj):
                        if isinstance(obj, h5py.Dataset):
                            print(f"      {name}: {obj.shape}")
                    f['state'].visititems(show_structure)
        except Exception as e:
            print(f"    H5 读取错误: {e}")
    
    # 检查图像
    if camera_dir.exists():
        frame_dirs = sorted([d for d in camera_dir.iterdir() if d.is_dir() and d.name.isdigit()])
        if frame_dirs:
            first_frame = frame_dirs[0]
            images = list(first_frame.glob("*.jpg")) + list(first_frame.glob("*.png"))
            print(f"\\n    相机帧 {first_frame.name}:")
            for img in images[:5]:
                print(f"      - {img.name}")
    
    print("\\n" + "=" * 80)
    print("测试完成!")
    print("=" * 80)


if __name__ == "__main__":
    main()
