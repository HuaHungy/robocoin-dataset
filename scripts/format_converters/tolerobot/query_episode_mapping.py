#!/usr/bin/env python3
"""
Episode Source Mapping 查询工具

用于查询转换后数据集的 episode 源文件映射信息
"""

import json
import argparse
from pathlib import Path
from typing import Optional


def load_mapping(dataset_path: str) -> dict:
    """加载映射文件"""
    mapping_file = Path(dataset_path) / "episode_source_mapping.json"
    
    if not mapping_file.exists():
        raise FileNotFoundError(
            f"❌ Mapping file not found: {mapping_file}\n"
            f"   Make sure the dataset has been converted and mapping was generated."
        )
    
    with open(mapping_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def print_dataset_info(mapping: dict) -> None:
    """打印数据集基本信息"""
    info = mapping["dataset_info"]
    print("=" * 80)
    print("📊 DATASET INFORMATION")
    print("=" * 80)
    print(f"Source Dataset:  {info['source_dataset_path']}")
    print(f"Output Dataset:  {info['output_dataset_path']}")
    print(f"Repo ID:         {info['repo_id']}")
    print(f"Device Model:    {info['device_model']}")
    print(f"Total Episodes:  {info['total_episodes']}")
    print("=" * 80)


def get_episode_info(mapping: dict, global_ep_idx: int) -> Optional[dict]:
    """获取指定 episode 的信息"""
    for episode in mapping["episodes"]:
        if episode["global_episode_index"] == global_ep_idx:
            return episode
    return None


def print_episode_info(episode: dict) -> None:
    """打印 episode 详细信息"""
    print("\n" + "=" * 80)
    print(f"📁 EPISODE {episode['global_episode_index']}")
    print("=" * 80)
    print(f"Task:                 {episode['task']}")
    print(f"Task Path:            {episode['task_path']}")
    print(f"Task Episode Index:   {episode['task_episode_index']}")
    print(f"Global Episode Index: {episode['global_episode_index']}")
    print("\n" + "-" * 80)
    print("SOURCE FILES:")
    print("-" * 80)
    
    source_files = episode["source_files"]
    for key, value in source_files.items():
        if value is not None:
            print(f"  {key:25s}: {value}")
    print("=" * 80)


def find_episodes_by_task(mapping: dict, task_name: str) -> list[dict]:
    """查找特定任务的所有 episodes"""
    episodes = []
    for episode in mapping["episodes"]:
        if task_name in episode["task"]:
            episodes.append(episode)
    return episodes


def find_episodes_by_source_file(mapping: dict, filename: str) -> list[dict]:
    """查找使用特定源文件的 episodes"""
    episodes = []
    for episode in mapping["episodes"]:
        source_files = episode["source_files"]
        for key, value in source_files.items():
            if isinstance(value, str) and filename in value:
                episodes.append(episode)
                break
    return episodes


def list_all_tasks(mapping: dict) -> list[str]:
    """列出所有唯一的任务名称"""
    tasks = set()
    for episode in mapping["episodes"]:
        tasks.add(episode["task"])
    return sorted(tasks)


def main():
    parser = argparse.ArgumentParser(
        description="Query episode source file mapping",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show dataset info
  python query_episode_mapping.py --dataset-path outputs/lerobot_converter --info
  
  # Show specific episode
  python query_episode_mapping.py --dataset-path outputs/lerobot_converter --episode 0
  
  # List all tasks
  python query_episode_mapping.py --dataset-path outputs/lerobot_converter --list-tasks
  
  # Find episodes by task name
  python query_episode_mapping.py --dataset-path outputs/lerobot_converter --task "pick_cube"
  
  # Find episodes by source file
  python query_episode_mapping.py --dataset-path outputs/lerobot_converter --source-file "episode_0"
        """
    )
    
    parser.add_argument(
        "--dataset-path",
        type=str,
        required=True,
        help="Path to the converted LeRobot dataset"
    )
    
    parser.add_argument(
        "--info",
        action="store_true",
        help="Show dataset information"
    )
    
    parser.add_argument(
        "--episode",
        type=int,
        help="Show specific episode by global index"
    )
    
    parser.add_argument(
        "--task",
        type=str,
        help="Find episodes by task name (substring match)"
    )
    
    parser.add_argument(
        "--source-file",
        type=str,
        help="Find episodes by source file name (substring match)"
    )
    
    parser.add_argument(
        "--list-tasks",
        action="store_true",
        help="List all unique task names"
    )
    
    args = parser.parse_args()
    
    try:
        # Load mapping
        mapping = load_mapping(args.dataset_path)
        
        # Show dataset info
        if args.info or not any([args.episode is not None, args.task, args.source_file, args.list_tasks]):
            print_dataset_info(mapping)
        
        # Show specific episode
        if args.episode is not None:
            episode = get_episode_info(mapping, args.episode)
            if episode:
                print_episode_info(episode)
            else:
                print(f"❌ Episode {args.episode} not found")
                print(f"   Valid range: 0 to {mapping['dataset_info']['total_episodes'] - 1}")
        
        # List all tasks
        if args.list_tasks:
            tasks = list_all_tasks(mapping)
            print("\n" + "=" * 80)
            print(f"📋 ALL TASKS ({len(tasks)} unique tasks)")
            print("=" * 80)
            for i, task in enumerate(tasks, 1):
                episodes_count = len(find_episodes_by_task(mapping, task))
                print(f"{i:3d}. {task:50s} ({episodes_count} episodes)")
            print("=" * 80)
        
        # Find episodes by task
        if args.task:
            episodes = find_episodes_by_task(mapping, args.task)
            print("\n" + "=" * 80)
            print(f"🔍 EPISODES FOR TASK: '{args.task}' ({len(episodes)} found)")
            print("=" * 80)
            for episode in episodes:
                print(f"  Episode {episode['global_episode_index']:4d} (task_ep={episode['task_episode_index']:3d}): {episode['task']}")
            print("=" * 80)
        
        # Find episodes by source file
        if args.source_file:
            episodes = find_episodes_by_source_file(mapping, args.source_file)
            print("\n" + "=" * 80)
            print(f"🔍 EPISODES WITH SOURCE FILE: '{args.source_file}' ({len(episodes)} found)")
            print("=" * 80)
            for episode in episodes:
                print(f"  Episode {episode['global_episode_index']:4d}: {episode['task']}")
                # Show which source file matched
                for key, value in episode["source_files"].items():
                    if isinstance(value, str) and args.source_file in value:
                        print(f"         {key}: {value}")
            print("=" * 80)
    
    except FileNotFoundError as e:
        print(str(e))
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
