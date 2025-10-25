#!/usr/bin/env python3
"""
Yinhe数据集帧数一致性检查工具

检查所有episodes的视频帧数与JSON数据帧数是否匹配
"""

import json
import sys
from pathlib import Path
from subprocess import run, PIPE
from typing import Dict, List

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / 'src'))

def check_episode_consistency(episode_dir: Path) -> Dict:
    """检查单个episode的帧数一致性
    
    Args:
        episode_dir: Episode目录路径
        
    Returns:
        包含检查结果的字典
    """
    result = {
        "episode": episode_dir.name,
        "episode_path": str(episode_dir),
        "video_frames": None,
        "actions_frames": None,
        "observations_frames": None,
        "is_consistent": False,
        "frame_difference": None,
        "error": None
    }
    
    try:
        # 1. 获取视频帧数（使用ffprobe）
        video_files = list(episode_dir.glob("*.mp4"))
        if video_files:
            video_file = video_files[0]  # 假设只有一个视频
            proc = run([
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-count_packets", "-show_entries", "stream=nb_read_packets",
                "-of", "csv=p=0", str(video_file)
            ], capture_output=True, text=True, check=True)
            result["video_frames"] = int(proc.stdout.strip())
            result["video_file"] = video_file.name
        else:
            result["error"] = "No video file found"
            return result
        
        # 2. 获取actions帧数
        actions_file = episode_dir / "actions.json"
        if actions_file.exists():
            with open(actions_file) as f:
                data = json.load(f)
                if isinstance(data, list):
                    result["actions_frames"] = len(data)
                elif isinstance(data, dict) and 'frames' in data:
                    result["actions_frames"] = len(data['frames'])
                else:
                    result["error"] = f"Unexpected actions.json format: {type(data)}"
        else:
            result["error"] = "actions.json not found"
        
        # 3. 获取observations帧数
        obs_file = episode_dir / "observations.json"
        if obs_file.exists():
            with open(obs_file) as f:
                data = json.load(f)
                if isinstance(data, list):
                    result["observations_frames"] = len(data)
                elif isinstance(data, dict) and 'frames' in data:
                    result["observations_frames"] = len(data['frames'])
                else:
                    result["error"] = f"Unexpected observations.json format: {type(data)}"
        
        # 4. 检查一致性
        frames = []
        if result["video_frames"] is not None:
            frames.append(result["video_frames"])
        if result["actions_frames"] is not None:
            frames.append(result["actions_frames"])
        if result["observations_frames"] is not None:
            frames.append(result["observations_frames"])
        
        if len(frames) > 0:
            result["is_consistent"] = len(set(frames)) == 1
            result["frame_difference"] = max(frames) - min(frames) if len(frames) > 1 else 0
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


def check_all_episodes(dataset_path: Path) -> List[Dict]:
    """检查所有episodes
    
    Args:
        dataset_path: 数据集根目录
        
    Returns:
        所有episode的检查结果列表
    """
    results = []
    
    print(f"🔍 扫描数据集: {dataset_path}")
    
    # 查找所有episode目录
    episode_dirs = []
    for path in dataset_path.rglob("episode_*"):
        if path.is_dir():
            episode_dirs.append(path)
    
    print(f"📊 找到 {len(episode_dirs)} 个episodes\n")
    
    # 检查每个episode
    for i, episode_dir in enumerate(sorted(episode_dirs), 1):
        print(f"[{i}/{len(episode_dirs)}] 检查: {episode_dir.relative_to(dataset_path)}", end=" ")
        result = check_episode_consistency(episode_dir)
        results.append(result)
        
        if result["error"]:
            print(f"❌ 错误: {result['error']}")
        elif result["is_consistent"]:
            print(f"✅ 一致 ({result['video_frames']} 帧)")
        else:
            print(f"⚠️  不一致 - video:{result['video_frames']}, "
                  f"actions:{result['actions_frames']}, obs:{result['observations_frames']}")
    
    return results


def print_summary(results: List[Dict]):
    """打印统计摘要
    
    Args:
        results: 检查结果列表
    """
    total = len(results)
    consistent = sum(1 for r in results if r["is_consistent"])
    has_error = sum(1 for r in results if r["error"])
    inconsistent = total - consistent - has_error
    
    print("\n" + "="*70)
    print("📊 统计摘要")
    print("="*70)
    print(f"总episodes:      {total}")
    print(f"✅ 一致:        {consistent} ({consistent/total*100:.1f}%)")
    print(f"⚠️  不一致:      {inconsistent} ({inconsistent/total*100:.1f}%)")
    print(f"❌ 错误:        {has_error} ({has_error/total*100:.1f}%)")
    
    # 统计帧数差异分布
    if inconsistent > 0:
        print("\n帧数差异分布:")
        diff_stats = {}
        for r in results:
            if not r["is_consistent"] and r["frame_difference"] is not None:
                diff = r["frame_difference"]
                diff_stats[diff] = diff_stats.get(diff, 0) + 1
        
        for diff in sorted(diff_stats.keys()):
            count = diff_stats[diff]
            print(f"  差异 {diff} 帧: {count} 个episodes")
    
    # 显示所有不一致的episodes
    if inconsistent > 0:
        print("\n⚠️  不一致的episodes详情:")
        for r in results:
            if not r["is_consistent"] and not r["error"]:
                print(f"  {r['episode']}")
                print(f"    视频帧数:       {r['video_frames']}")
                print(f"    Actions帧数:    {r['actions_frames']}")
                print(f"    Observations帧数: {r['observations_frames']}")
                print(f"    差异:          {r['frame_difference']} 帧")
    
    # 显示所有错误
    if has_error > 0:
        print("\n❌ 错误episodes详情:")
        for r in results:
            if r["error"]:
                print(f"  {r['episode']}: {r['error']}")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="检查Yinhe数据集帧数一致性")
    parser.add_argument(
        "--dataset-path",
        type=Path,
        default=Path("/home/liu/program/robocoin-dataset/data/yinhe:default_version"),
        help="数据集路径"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("yinhe_frame_consistency_report.json"),
        help="输出报告路径"
    )
    
    args = parser.parse_args()
    
    if not args.dataset_path.exists():
        print(f"❌ 数据集路径不存在: {args.dataset_path}")
        return 1
    
    # 检查所有episodes
    results = check_all_episodes(args.dataset_path)
    
    # 打印摘要
    print_summary(results)
    
    # 保存详细报告
    report = {
        "dataset_path": str(args.dataset_path),
        "total_episodes": len(results),
        "consistent_episodes": sum(1 for r in results if r["is_consistent"]),
        "inconsistent_episodes": sum(1 for r in results if not r["is_consistent"] and not r["error"]),
        "error_episodes": sum(1 for r in results if r["error"]),
        "episodes": results
    }
    
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n📄 详细报告已保存: {args.output}")
    
    # 返回状态码
    if report["inconsistent_episodes"] > 0 or report["error_episodes"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

