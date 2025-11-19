import json
from pathlib import Path


def get_meta_info_file(root_dir: str | Path, meta_feature: str | None = None) -> Path:
    root_dir = Path(root_dir).expanduser().absolute()
    if not meta_feature:
        return root_dir / "meta/info.json"

    return root_dir / f"meta/{meta_feature}_info.json"


def get_tasks_jsonl_file(root_dir: str | Path, feature: str | None = None) -> Path:
    root_dir = Path(root_dir).expanduser().absolute()
    if not feature:
        return root_dir / "meta/tasks.jsonl"
    return root_dir / f"meta/{feature}_tasks.jsonl"


def get_episodes_jsonl_file(root_dir: str | Path, meta_feature: str | None = None) -> Path:
    root_dir = Path(root_dir).expanduser().absolute()
    if not meta_feature:
        return root_dir / "meta/episodes.jsonl"
    return root_dir / f"meta/{meta_feature}_episodes.jsonl"


def get_episodes_stats_jsonl_file(root_dir: str | Path, meta_feature: str | None = None) -> Path:
    root_dir = Path(root_dir).expanduser().absolute()
    if not meta_feature:
        return root_dir / "meta/episodes_stats.jsonl"
    return root_dir / f"meta/{meta_feature}_episodes_stats.jsonl"


def get_episodes_frames(root_dir: str | Path, meta_feature: str | None = None) -> dict[int, int]:
    jsonl_path = get_episodes_jsonl_file(root_dir, meta_feature=meta_feature)
    with open(jsonl_path) as f:
        episode_frames = {}
        for line in f:
            data = json.loads(line)
            episode_id = data["episode_index"]
            frame_count = data["length"]
            episode_frames[episode_id] = frame_count

    return episode_frames


def get_episode_num(repo_path: str | Path, meta_feature: str | None = None) -> int:
    try:
        with open(get_meta_info_file(repo_path, meta_feature)) as f:
            return json.load(f)["total_episodes"]
    except FileNotFoundError:
        return 0


def get_meta_info(repo_path: str | Path, meta_feature: str | None) -> tuple[int, int, int] | None:
    with open(get_meta_info_file(repo_path, meta_feature)) as f:
        meta_info = json.load(f)
        total_episodes = meta_info["total_episodes"]
        chunk_size = meta_info["chunks_size"]
        total_frames = meta_info["total_frames"]
        return total_episodes, chunk_size, total_frames


def get_video_files(
    repo_path: str | Path, video_feature: str | None = None, meta_feature: str | None = None
) -> list[list[Path]]:
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
    try:
        repo_path = Path(repo_path).expanduser().absolute()
        if video_feature:
            video_dir = repo_path / f"{video_feature}_videos"
        else:
            video_dir = repo_path / "videos"
        ep_num, chunk_size, _ = get_meta_info(repo_path, meta_feature=meta_feature)
        camera_features = []

        camera_features = [
            camera_feature.name
            for camera_feature in (video_dir / "chunk-000").glob("*")
            if camera_feature.is_dir()
        ]
        if not camera_features:
            raise ValueError("No video directory found.")
        return [
            [
                video_dir
                / f"chunk-{ep_idx // chunk_size:03d}/{cam_feature}/episode_{ep_idx:06d}.mp4"
                for cam_feature in camera_features
            ]
            for ep_idx in range(ep_num)
        ]

    except Exception as e:
        raise e


def get_parquet_files(
    root_dir: str | Path,
    feature: str | None = None,
    meta_feature: str | None = None,
) -> list[Path]:
    root_dir = Path(root_dir).expanduser().absolute()

    total_episodes, chunk_size, _ = get_meta_info(root_dir, meta_feature)

    if feature:
        data_dir = root_dir / f"{feature}_data"
    else:
        data_dir = root_dir / "data"
    print(data_dir, total_episodes)
    return [
        data_dir / f"chunk-{(ep_idx // chunk_size):03d}/episode_{ep_idx:06d}.parquet"
        for ep_idx in range(total_episodes)
    ]
