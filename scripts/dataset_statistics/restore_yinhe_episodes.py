#!/usr/bin/env python3
"""
恢复银河数据集误移动到error文件夹的episodes

问题原因:
之前的验证器代码中,读取JSON时使用了f.read(10 * 1024 * 1024)限制,
导致大于10MB的JSON文件被截断,引发解析错误。
实际上这些episodes的JSON文件是完整有效的。

使用方法:
    # 扫描并统计
    python3 restore_yinhe_episodes.py --dataset-path /path/to/银河通用 --dry-run
    
    # 确认后执行恢复
    python3 restore_yinhe_episodes.py --dataset-path /path/to/银河通用
"""

import argparse
import json
import shutil
import sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed


def test_episode_json(episode_dir: Path) -> tuple[Path, bool, str]:
    """
    测试episode的JSON文件是否真的有问题
    
    Returns:
        (episode_dir, is_valid, error_message)
    """
    json_path = episode_dir / "data.json"
    
    if not json_path.exists():
        return (episode_dir, False, "缺失data.json")
    
    try:
        # 完整读取JSON文件
        with open(json_path, encoding='utf-8') as f:
            data = json.load(f)
        
        # 基本验证
        if 'data' not in data:
            return (episode_dir, False, "JSON缺少data字段")
        
        # 检查是否有必要的字段
        data_section = data['data']
        if not isinstance(data_section, dict) or len(data_section) == 0:
            return (episode_dir, False, "JSON data字段为空")
        
        return (episode_dir, True, "")
    
    except json.JSONDecodeError as e:
        return (episode_dir, False, f"JSON格式错误: {e}")
    except Exception as e:
        return (episode_dir, False, f"读取错误: {e}")


def find_error_episodes(dataset_path: Path) -> list[Path]:
    """查找所有error文件夹中的episodes"""
    print("🔍 查找error文件夹中的episodes...")
    error_episodes = []
    
    # 遍历所有error文件夹
    for error_dir in dataset_path.rglob("error"):
        if not error_dir.is_dir():
            continue
        
        # 遍历error目录下的episode
        for episode_dir in error_dir.iterdir():
            if episode_dir.is_dir():
                error_episodes.append(episode_dir)
    
    print(f"✅ 找到 {len(error_episodes)} 个error中的episodes")
    return error_episodes


def restore_episode(episode_dir: Path, dry_run: bool = True) -> tuple[bool, str]:
    """
    恢复单个episode
    
    Returns:
        (success, message)
    """
    try:
        # 目标路径: 从 robot_id/error/episode -> robot_id/episode
        parent_dir = episode_dir.parent.parent
        dest_path = parent_dir / episode_dir.name
        
        if dest_path.exists():
            return (False, f"目标已存在: {dest_path.name}")
        
        if dry_run:
            return (True, f"将恢复: {episode_dir.parent.parent.name}/{episode_dir.name}")
        else:
            shutil.move(str(episode_dir), str(dest_path))
            return (True, f"已恢复: {episode_dir.parent.parent.name}/{episode_dir.name}")
    
    except Exception as e:
        return (False, f"恢复失败: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="恢复银河数据集误移动到error的episodes",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dataset-path",
        type=Path,
        required=True,
        help="数据集根目录"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只扫描不执行(默认开启)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="并行进程数"
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="跳过JSON验证,直接恢复所有episodes"
    )
    
    args = parser.parse_args()
    
    if not args.dataset_path.exists():
        print(f"❌ 路径不存在: {args.dataset_path}")
        sys.exit(1)
    
    print("="*70)
    print("银河数据集Episode恢复工具")
    print("="*70)
    print(f"数据集路径: {args.dataset_path}")
    print(f"模式: {'预览模式(不执行)' if args.dry_run else '⚠️ 执行模式(会移动文件)'}")
    print(f"并行度: {args.workers}")
    print("="*70)
    print()
    
    # 1. 查找所有error中的episodes
    error_episodes = find_error_episodes(args.dataset_path)
    
    if not error_episodes:
        print("✅ 没有找到error中的episodes")
        return
    
    # 2. 验证哪些episodes是可以恢复的
    print(f"\n🧪 验证episodes有效性 (使用 {args.workers} 个进程)...")
    
    valid_episodes = []
    invalid_episodes = []
    
    if args.skip_validation:
        print("⏭️  跳过验证,将恢复所有episodes")
        valid_episodes = error_episodes
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(test_episode_json, ep): ep for ep in error_episodes}
            
            for i, future in enumerate(as_completed(futures), 1):
                try:
                    episode_dir, is_valid, error_msg = future.result()
                    
                    if is_valid:
                        valid_episodes.append(episode_dir)
                    else:
                        invalid_episodes.append((episode_dir, error_msg))
                    
                    if i % 100 == 0:
                        print(f"  进度: {i}/{len(error_episodes)}")
                
                except Exception as e:
                    print(f"  ❌ 验证异常: {e}")
        
        print(f"\n📊 验证结果:")
        print(f"  ✅ 有效episodes: {len(valid_episodes)}")
        print(f"  ❌ 仍有问题: {len(invalid_episodes)}")
        
        if invalid_episodes and len(invalid_episodes) <= 20:
            print(f"\n  以下episodes仍有问题(将不会恢复):")
            for ep, msg in invalid_episodes[:20]:
                print(f"    - {ep.parent.parent.name}/{ep.name}: {msg}")
    
    # 3. 恢复有效的episodes
    if not valid_episodes:
        print("\n⚠️  没有可恢复的episodes")
        return
    
    print(f"\n{'📋 将要恢复' if args.dry_run else '🚀 开始恢复'} {len(valid_episodes)} 个episodes...")
    
    success_count = 0
    fail_count = 0
    
    for i, episode_dir in enumerate(valid_episodes, 1):
        success, message = restore_episode(episode_dir, dry_run=args.dry_run)
        
        if success:
            success_count += 1
            if args.dry_run and i <= 10:
                print(f"  {message}")
        else:
            fail_count += 1
            print(f"  ❌ {message}")
        
        if i % 100 == 0:
            print(f"  进度: {i}/{len(valid_episodes)}")
    
    # 4. 总结
    print("\n" + "="*70)
    if args.dry_run:
        print("📋 预览总结:")
        print(f"  可恢复: {success_count} 个episodes")
        print(f"  无法恢复: {fail_count} 个episodes")
        print("\n⚠️  这是预览模式,没有实际移动文件")
        print("要执行恢复,请移除 --dry-run 参数重新运行")
    else:
        print("✅ 恢复完成:")
        print(f"  成功: {success_count} 个episodes")
        print(f"  失败: {fail_count} 个episodes")
    print("="*70)


if __name__ == "__main__":
    main()
