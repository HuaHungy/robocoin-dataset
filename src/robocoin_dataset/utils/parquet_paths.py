import json
from pathlib import Path


def get_parquet_paths(
    root_dir: str | Path,
    new_parquet_type: str = "",
    meta_info_type: str = "",
    ori_parquet_type: str = "",
) -> tuple[list[Path], list[Path]]:
    root_dir = Path(root_dir).expanduser().absolute()
    if meta_info_type:
        meta_info_file_path = root_dir / f"meta/{meta_info_type}_info.json"
    else:
        meta_info_file_path = root_dir / "meta/info.json"

    with open(meta_info_file_path) as f:
        meta_info = json.load(f)
        chunk_size = meta_info.get("chunk_size", None)
        total_episodes = meta_info.get("total_episodes", None)

    parquet_files = []
    new_parquet_files = []
    if new_parquet_type:
        (root_dir / f"{new_parquet_type}_data").mkdir(parents=True, exist_ok=True)

    for ep_id in range(total_episodes):
        chunk_idx = ep_id // chunk_size
        if ori_parquet_type:
            parquet_file_path = (
                root_dir
                / f"{ori_parquet_type}_data"
                / f"chunk_{chunk_idx:03d}"
                / f"ep_{ep_id:06d}.parquet"
            )
        else:
            parquet_file_path = (
                root_dir / "data" / f"chunk_{chunk_idx:03d}" / f"ep_{ep_id:06d}.parquet"
            )
        parquet_files.append(parquet_file_path)
        if new_parquet_type:
            new_parquet_file_path = (
                root_dir
                / f"{new_parquet_type}_data"
                / f"chunk_{chunk_idx:03d}"
                / f"{new_parquet_type}_{ep_id:06d}.parquet"
            )
            new_parquet_files.append(new_parquet_file_path)

    if new_parquet_type:
        return parquet_files, new_parquet_files
    return parquet_files, None


def get_meta_info_file_path(root_dir: str | Path, new_parquet_type: str) -> tuple[Path, Path]:
    root_dir = Path(root_dir).expanduser().absolute()
    return root_dir / "meta/info.json", root_dir / f"meta/{new_parquet_type}_info.json"


def get_episode_stats_file_path(root_dir: str | Path, new_parquet_type: str) -> tuple[Path, Path]:
    root_dir = Path(root_dir).expanduser().absolute()
    return (
        root_dir / "meta/episodes_stats.jsonl",
        root_dir / f"meta/{new_parquet_type}_episodes_stats.jsonl",
    )
