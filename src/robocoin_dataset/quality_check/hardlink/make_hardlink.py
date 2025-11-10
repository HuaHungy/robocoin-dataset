import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class RepoHardLinkCorresp:
    def __init__(
        self,
        input_feature: str,
        source_repo_path: str | Path,
        hard_link_repo_path: str | Path,
        video_path_corresp: dict[str | Path, str | Path],
    ) -> None:
        self.source_repo_path = Path(source_repo_path).expanduser().absolute()
        self.hard_link_repo_path = Path(hard_link_repo_path).expanduser().absolute()
        self.video_path_corresp = video_path_corresp
        if not os.path.exists(source_repo_path):
            raise FileNotFoundError(f"源目录不存在: {source_repo_path}")

        self.file_corresp: dict[str, str] = {
            self.source_repo_path / f"meta/{input_feature}_info.json": self.hard_link_repo_path
            / "meta/info.json",
            self.source_repo_path / f"meta/{input_feature}_episodes.jsonl": self.hard_link_repo_path
            / "meta/episodes.jsonl",
            self.source_repo_path
            / f"meta/{input_feature}_episodes_stats.jsonl": self.hard_link_repo_path
            / "meta/episodes_stats.jsonl",
            self.source_repo_path / "meta/tasks.jsonl": self.hard_link_repo_path
            / "meta/tasks.jsonl",
        }
        # _, source_episodes_paths = get_parquet_paths(self.source_repo_path, input_feature)

        source_episodes_paths = Path(self.source_repo_path / f"{input_feature}_data").rglob(
            "episode_*.parquet"
        )
        self.file_corresp.update(
            {
                ep_parquet_path: self.hard_link_repo_path
                / "data"
                / ep_parquet_path.relative_to(self.source_repo_path / f"{input_feature}_data")
                for ep_parquet_path in source_episodes_paths
            }
        )
        self.file_corresp.update(
            {
                Path(source_video_path): self.hard_link_repo_path
                / "videos"
                / Path(hl_video_path).relative_to(self.source_repo_path / "videos")
                for source_video_path, hl_video_path in self.video_path_corresp.items()
            }
        )
        self.dir_corresp: dict[str, str] = {
            self.source_repo_path / "annotations": self.hard_link_repo_path / "annotations",
        }

    def get_hard_link_corresp(self) -> tuple[dict[str, str], dict[str, str]]:
        return self.file_corresp, self.dir_corresp


def create_hardlinks_from_correspondence(
    file_corresp: dict[str, str | Path],
    dir_corresp: dict[str, str | Path],
) -> None:
    """
    根据映射关系创建硬链接。

    Parameters:
        file_corresp: {src_file_path: dst_hardlink_path}
        dir_corresp:  {src_dir_path: dst_dir_path} —— 会递归为 src_dir 下所有文件创建硬链接到 dst_dir
    """
    # 处理文件硬链接
    for src, dst in file_corresp.items():
        src = Path(src).resolve()
        dst = Path(dst)
        if not src.is_file():
            raise FileNotFoundError(f"Source file does not exist: {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            dst.unlink()  # 可选：覆盖已有链接/文件
        os.link(src, dst)

    # 处理目录硬链接（实际上是递归为每个文件建硬链接）
    for src_dir, dst_dir in dir_corresp.items():
        src_dir = Path(src_dir).resolve()
        dst_dir = Path(dst_dir)
        if not src_dir.is_dir():
            raise NotADirectoryError(f"Source directory does not exist: {src_dir}")

        for src_file in src_dir.rglob("*"):
            if src_file.is_file():
                # 计算相对路径
                rel_path = src_file.relative_to(src_dir)
                dst_file = dst_dir / rel_path
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                if dst_file.exists():
                    dst_file.unlink()  # 可选：覆盖
                os.link(src_file, dst_file)
