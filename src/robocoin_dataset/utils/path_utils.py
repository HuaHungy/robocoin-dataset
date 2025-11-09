import json
import re
from collections import defaultdict
from pathlib import Path


def get_meta_info_file_path(root_dir: str | Path, new_type: str) -> tuple[Path, Path]:
    root_dir = Path(root_dir).expanduser().absolute()
    info_file_path = root_dir / "meta/info.json"
    if info_file_path.exists():
        return info_file_path, root_dir / f"meta/{new_type}_info.json"
    raise FileNotFoundError(f"Meta info file not found at {info_file_path}")


def get_episodes_jsonl_file_paths(root_dir: str | Path, new_type: str) -> tuple[Path, Path]:
    root_dir = Path(root_dir).expanduser().absolute()
    stats_file_path = root_dir / "meta/episodes.jsonl"
    if stats_file_path.exists():
        return stats_file_path, root_dir / f"meta/{new_type}_episodes.jsonl"
    raise FileNotFoundError(f"Episodes jsonl file not found at {stats_file_path}")


def get_episodes_stats_jsonl_file_paths(root_dir: str | Path, new_type: str) -> tuple[Path, Path]:
    root_dir = Path(root_dir).expanduser().absolute()
    stats_file_path = root_dir / "meta/episodes_stats.jsonl"
    if stats_file_path.exists():
        return stats_file_path, root_dir / f"meta/{new_type}_episodes_stats.jsonl"
    raise FileNotFoundError(f"Episodes jsonl file not found at {stats_file_path}")


def get_episodes_frames(root_dir: str | Path) -> dict[int, int]:
    jsonl_path, _ = get_episodes_jsonl_file_paths(root_dir, "")
    with open(jsonl_path) as f:
        episode_frames = {}
        for line in f:
            data = json.loads(line)
            episode_id = data["episode_index"]
            frame_count = data["length"]
            episode_frames[episode_id] = frame_count

    return episode_frames


def get_dataset_video_paths(repo_path: str | Path) -> list[list[Path]]:
    """
    获取数据集中所有 episode 视频路径，并按 episode 编号分组。

    路径格式: videos/chunk_xxx/*/episode_xxxxxx.mp4

    Args:
        dataset_root: 数据集根目录（包含 videos/ 子目录）
        episode_pattern: 用于提取 episode 编号的正则表达式

    Returns:
        List[List[Path]]: 按 episode 编号升序排列，每个元素是该编号的所有视频路径列表。
        例如：[
            [Path(".../episode_000001.mp4"), Path(".../dup/episode_000001.mp4")],
            [Path(".../episode_000002.mp4")],
            ...
        ]
    """
    episode_pattern: str = r"episode_(\d+)\.mp4$"
    dataset_root = Path(repo_path).expanduser().absolute()
    video_dir = dataset_root / "videos"

    # 收集所有匹配的视频文件
    # glob 模式: chunk_xxx 下任意子目录中的 episode_*.mp4
    all_video_paths = []
    for chunk_dir in video_dir.glob("chunk-*"):
        if not chunk_dir.is_dir():
            continue
        # 递归匹配 chunk_xxx 下所有子目录中的 episode_*.mp4
        all_video_paths.extend([video_path for video_path in chunk_dir.rglob("episode_*.mp4")])

    # 按 episode 编号分组
    episode_groups = defaultdict(list)
    pattern = re.compile(episode_pattern)

    for path in all_video_paths:
        match = pattern.search(str(path.name))
        if not match:
            continue  # 跳过不符合命名的文件
        try:
            episode_id = int(match.group(1))
        except ValueError:
            continue  # 编号不是整数，跳过

        if episode_id not in episode_groups:
            episode_groups[episode_id] = []
        episode_groups[episode_id].append(path)

    # 按 episode_id 升序排列，返回分组列表
    sorted_episodes = sorted(episode_groups.items(), key=lambda x: x[0])
    return [paths for _, paths in sorted_episodes]
