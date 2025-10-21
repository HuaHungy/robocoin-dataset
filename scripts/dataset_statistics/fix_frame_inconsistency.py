#!/usr/bin/env python3
"""
自动处理智平方数据集中帧数不一致的文件

功能：
1. 扫描所有 H5 文件
2. 检测帧数不一致的文件
3. 自动移动到 error/ 目录
4. 生成报告
"""

import sys
import shutil
from pathlib import Path
from collections import defaultdict
import h5py
import yaml
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Optional, Dict, List


def load_converter_config(config_path: Path) -> dict:
    """加载 converter 配置以获取需要检查的路径"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        print(f"⚠️  无法加载配置文件 {config_path}: {e}")
        return {}


def extract_h5_paths_from_config(config: dict) -> List[str]:
    """从配置中提取需要检查的 H5 路径"""
    paths = []
    
    # 提取 state 路径
    if 'features' in config and 'observation' in config['features']:
        obs = config['features']['observation']
        
        if 'state' in obs and 'sub_state' in obs['state']:
            for sub_state in obs['state']['sub_state']:
                if 'h5_path' in sub_state:
                    paths.append(sub_state['h5_path'])
    
    return paths


def check_h5_frame_consistency(
    h5_file_path: Path,
    check_paths: Optional[List[str]] = None
) -> Optional[Dict]:
    """检查单个 H5 文件的帧数一致性
    
    Args:
        h5_file_path: H5 文件路径
        check_paths: 要检查的路径列表，如果为 None 则检查所有数据集
    
    Returns:
        None: 文件无效或无数据
        Dict: 包含检查结果的字典
    """
    try:
        with h5py.File(h5_file_path, 'r') as f:
            frame_counts = {}
            
            if check_paths:
                # 使用配置中的路径
                paths_to_check = check_paths
            else:
                # 检查所有顶层数据集（递归查找所有路径会太慢）
                def find_datasets(group, prefix=''):
                    datasets = []
                    for key in group.keys():
                        path = f"{prefix}/{key}" if prefix else key
                        item = group[key]
                        if isinstance(item, h5py.Dataset):
                            datasets.append(path)
                        elif isinstance(item, h5py.Group):
                            datasets.extend(find_datasets(item, path))
                    return datasets
                
                paths_to_check = find_datasets(f)
            
            # 检查每个路径的帧数
            for path in paths_to_check:
                try:
                    if path in f:
                        dataset = f[path]
                        shape = dataset.shape
                        
                        # 跳过标量数据
                        if shape == ():
                            continue
                        
                        # 跳过空数据
                        if len(shape) > 0 and shape[0] == 0:
                            continue
                        
                        # 记录帧数
                        if len(shape) > 0:
                            frame_counts[path] = shape[0]
                except Exception:
                    continue  # 跳过无法访问的路径
            
            if len(frame_counts) == 0:
                return None  # 无有效数据
            
            # 检查是否一致
            unique_counts = set(frame_counts.values())
            
            if len(unique_counts) > 1:
                # 帧数不一致
                return {
                    'file': h5_file_path,
                    'frame_counts': frame_counts,
                    'inconsistent': True,
                    'reference_count': min(frame_counts.values()),  # 使用最小帧数作为参考
                }
            else:
                # 帧数一致
                return {
                    'file': h5_file_path,
                    'frame_count': list(unique_counts)[0],
                    'inconsistent': False,
                }
    
    except Exception as e:
        return {
            'file': h5_file_path,
            'error': str(e),
            'inconsistent': False,
        }


def move_to_error_folder(h5_file_path: Path, dry_run: bool = False) -> bool:
    """移动文件到 error/ 目录
    
    Args:
        h5_file_path: 文件路径
        dry_run: 如果为 True，只打印不实际移动
    
    Returns:
        bool: 是否成功移动
    """
    error_dir = h5_file_path.parent / "error"
    target_path = error_dir / h5_file_path.name
    
    if dry_run:
        print(f"  [DRY RUN] 将移动: {h5_file_path.name}")
        print(f"           目标: {error_dir}")
        return True
    
    try:
        # 创建 error 目录
        error_dir.mkdir(exist_ok=True)
        
        # 移动文件
        shutil.move(str(h5_file_path), str(target_path))
        
        print(f"  ✅ 已移动: {h5_file_path.name} -> error/")
        return True
    
    except Exception as e:
        print(f"  ❌ 移动失败: {h5_file_path.name}")
        print(f"     错误: {e}")
        return False


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="自动检测并移动帧数不一致的 H5 文件"
    )
    parser.add_argument(
        "dataset_path",
        type=Path,
        help="数据集根目录路径"
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Converter 配置文件路径（可选）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只检测不移动文件"
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="最多检查的文件数（用于测试）"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="并行处理的工作进程数"
    )
    
    args = parser.parse_args()
    
    dataset_path = args.dataset_path
    
    if not dataset_path.exists():
        print(f"❌ 数据集路径不存在: {dataset_path}")
        sys.exit(1)
    
    print("="*70)
    print("H5 文件帧数一致性检查与修复")
    print("="*70)
    print(f"📁 数据集: {dataset_path}")
    print(f"🔧 模式: {'DRY RUN（不实际移动）' if args.dry_run else '实际移动文件'}")
    print()
    
    # 加载配置（如果提供）
    check_paths = None
    if args.config and args.config.exists():
        print(f"📋 加载配置: {args.config}")
        config = load_converter_config(args.config)
        check_paths = extract_h5_paths_from_config(config)
        if check_paths:
            print(f"   将检查 {len(check_paths)} 个配置的路径")
        print()
    
    # 查找所有 H5 文件
    print("🔍 扫描 H5 文件...")
    h5_files = sorted(list(dataset_path.rglob("*.h5")))
    
    # 排除已经在 error 目录中的文件
    h5_files = [f for f in h5_files if "error" not in f.parts]
    
    print(f"   找到 {len(h5_files)} 个 H5 文件")
    
    if args.max_files:
        h5_files = h5_files[:args.max_files]
        print(f"   限制检查前 {args.max_files} 个文件")
    
    print()
    
    # 多进程检查
    print("⚙️  检查帧数一致性...")
    inconsistent_files = []
    error_files = []
    consistent_count = 0
    
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(check_h5_frame_consistency, h5_file, check_paths): h5_file
            for h5_file in h5_files
        }
        
        for i, future in enumerate(as_completed(futures), 1):
            if i % 100 == 0:
                print(f"   进度: {i}/{len(h5_files)}")
            
            try:
                result = future.result()
                
                if result is None:
                    continue
                
                if result.get('error'):
                    error_files.append(result)
                elif result['inconsistent']:
                    inconsistent_files.append(result)
                else:
                    consistent_count += 1
            
            except Exception as e:
                h5_file = futures[future]
                print(f"   ⚠️  处理失败: {h5_file.name} - {e}")
    
    print()
    
    # 显示结果
    print("="*70)
    print("检查结果")
    print("="*70)
    print(f"✅ 一致: {consistent_count} 个文件")
    print(f"❌ 不一致: {len(inconsistent_files)} 个文件")
    print(f"⚠️  错误: {len(error_files)} 个文件")
    print()
    
    # 处理不一致的文件
    if inconsistent_files:
        print("="*70)
        print(f"处理 {len(inconsistent_files)} 个帧数不一致的文件")
        print("="*70)
        print()
        
        moved_count = 0
        failed_count = 0
        
        for result in inconsistent_files:
            h5_file = result['file']
            frame_counts = result['frame_counts']
            
            print(f"📁 {h5_file.relative_to(dataset_path)}")
            
            # 显示帧数详情
            unique_counts = set(frame_counts.values())
            if len(unique_counts) <= 5:  # 只显示少量不同的帧数
                print(f"   帧数差异:")
                for path, count in sorted(frame_counts.items(), key=lambda x: x[1]):
                    print(f"     {count:4d} 帧: {path}")
            else:
                counts_summary = defaultdict(list)
                for path, count in frame_counts.items():
                    counts_summary[count].append(path)
                print(f"   帧数分布:")
                for count in sorted(counts_summary.keys()):
                    paths = counts_summary[count]
                    print(f"     {count:4d} 帧: {len(paths)} 个路径")
            
            # 移动文件
            if move_to_error_folder(h5_file, dry_run=args.dry_run):
                moved_count += 1
            else:
                failed_count += 1
            
            print()
        
        print("="*70)
        print("移动结果")
        print("="*70)
        if args.dry_run:
            print(f"[DRY RUN] 将移动 {len(inconsistent_files)} 个文件到 error/ 目录")
        else:
            print(f"✅ 成功移动: {moved_count} 个文件")
            if failed_count > 0:
                print(f"❌ 移动失败: {failed_count} 个文件")
        print()
    
    # 显示错误文件
    if error_files:
        print("="*70)
        print(f"⚠️  {len(error_files)} 个文件处理时出错")
        print("="*70)
        for result in error_files[:10]:  # 只显示前10个
            print(f"  {result['file'].name}: {result['error']}")
        if len(error_files) > 10:
            print(f"  ... 还有 {len(error_files) - 10} 个错误")
        print()
    
    print("="*70)
    print("✅ 完成")
    print("="*70)


if __name__ == "__main__":
    main()
