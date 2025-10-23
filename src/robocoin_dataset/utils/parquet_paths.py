import re
from pathlib import Path

from natsort import natsorted


def get_parquet_paths(root_dir: str | Path, new_parquet_type: str) -> tuple[list[Path], list[Path]]:
    root_dir = Path(root_dir).expanduser().absolute()
    data_dir_path = root_dir / "data"
    new_parquet_data_dir_name = f"{new_parquet_type}_data"
    new_parquet_data_dir_path = root_dir / new_parquet_data_dir_name

    regex = re.compile(r"episode_(?P<idx>\d{6})\.parquet$")
    parquet_files = []
    for file_path in data_dir_path.rglob("episode_*.parquet"):
        match = regex.match(file_path.name)
        if match:
            parquet_files.append(file_path)

    parquet_files = natsorted(parquet_files, key=lambda x: x.name)

    new_parquet_files: list[Path] = []
    for path in parquet_files:
        path_str = str(path)
        new_path_str = path_str.replace(str(data_dir_path), str(new_parquet_data_dir_path))
        new_parquet_files.append(Path(new_path_str))

    return parquet_files, new_parquet_files


def get_meta_info_file_path(root_dir: str | Path, new_parquet_type: str) -> tuple[Path, Path]:
    return root_dir / "meta/info.json", root_dir / f"meta/{new_parquet_type}_info.json"


def get_episode_stats_file_path(root_dir: str | Path, new_parquet_type: str) -> tuple[Path, Path]:
    return (
        root_dir / "meta/episode_stats.jsonl",
        root_dir / f"meta/{new_parquet_type}_episode_stats.jsonl",
    )
