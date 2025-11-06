import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class HardLinkCorresp:
    file_corresp: dict[str, str] = field(default_factory=dict)
    dir_corresp: dict[str, str] | None = None


@dataclass
class RepoHardLinkCorresp(HardLinkCorresp):
    file_corresp: dict[str, str] = field(
        default_factory=lambda: {
            "meta/merged_info.json": "meta/info.json",
            "meta/episodes.jsonl": "meta/episodes.jsonl",
            "meta/merged_episodes_stats.jsonl": "meta/episodes_stats.jsonl",
            "meta/tasks.jsonl": "meta/tasks.jsonl",
        }
    )
    dir_corresp: dict[str, str] = field(
        default_factory=lambda: {
            "merged_data/": "data/",
            "videos/": "videos/",
            "annotations/": "annotations/",
        }
    )


def create_hardlinks_from_correspondence(
    src_root: str | Path,
    dst_root: str | Path,
    hard_link_corresp: HardLinkCorresp,
) -> None:
    """
    根据文件和目录对应关系，创建硬链接。

    参数:
        src_root: 源目录根路径。
        dst_root: 目标目录根路径。
        file_corresp: 映射 {源相对路径: 目标相对路径}。
        dir_corresp: 映射 {源目录前缀: 目标目录前缀}，如 {"merged_data/": "data/"}。

    规则:
        - file_corresp 中的文件优先处理，不会被 dir_corresp 覆盖。
        - dir_corresp 用于处理未在 file_corresp 中列出的文件。
        - 所有路径均为字符串形式的相对路径（使用 POSIX 风格，如 "a/b.txt"）。
    """
    src_root = Path(src_root)
    dst_root = Path(dst_root)

    file_corresp = hard_link_corresp.file_corresp
    dir_corresp = hard_link_corresp.dir_corresp

    if not src_root.exists():
        raise FileNotFoundError(f"源目录不存在: {src_root}")
    dst_root.mkdir(parents=True, exist_ok=True)

    # Step 1: 处理 file_corresp 中的文件
    handled_src_rels = set()  # 记录已处理的源相对路径（字符串）
    for src_rel_str, dst_rel_str in file_corresp.items():
        src_path = src_root / src_rel_str
        dst_path = dst_root / dst_rel_str

        if not src_path.is_file():
            raise FileNotFoundError(f"源文件不存在或不是普通文件: {src_path}")

        dst_path.parent.mkdir(parents=True, exist_ok=True)
        if dst_path.is_symlink() or dst_path.exists():
            dst_path.unlink()

        try:
            os.link(src_path, dst_path)
            logger.debug(f"Created hardlink: {src_path} → {dst_path}")
        except OSError as e:
            if e.errno == 18:
                raise OSError(
                    f"❌ 跨文件系统无法创建硬链接: {src_path} → {dst_path}\n"
                    "请确保 src_root 和 dst_root 在同一挂载点。"
                ) from e
            if e.errno == 17:
                raise FileExistsError(f"❌ 目标已存在: {dst_path}") from e
            raise
        handled_src_rels.add(src_rel_str)

    # Step 2: 处理 dir_corresp 中的文件（未被 file_corresp 覆盖的）
    if not dir_corresp:
        return

    # 将 dir_corresp 的 key/value 转为 Path 并确保以 '/' 结尾（用于前缀匹配）
    dir_map = {}
    for src_prefix, dst_prefix in dir_corresp.items():
        # 确保是目录形式（以 / 结尾）
        if not src_prefix.endswith("/"):
            src_prefix += "/"
        if not dst_prefix.endswith("/"):
            dst_prefix += "/"
        dir_map[src_prefix] = dst_prefix

    # 遍历源目录所有文件
    for src_file in src_root.rglob("*"):
        if not src_file.is_file() or src_file.is_symlink():
            continue

        try:
            rel_str = src_file.relative_to(src_root).as_posix()  # "merged_data/1.txt"
        except ValueError:
            continue  # 不应在正常情况下发生

        # 跳过已在 file_corresp 中处理的文件
        if rel_str in handled_src_rels:
            continue

        # 尝试匹配 dir_corresp 前缀
        for src_prefix, dst_prefix in dir_map.items():
            if rel_str.startswith(src_prefix):
                # 替换前缀
                dst_rel_str = dst_prefix + rel_str[len(src_prefix) :]
                dst_path: Path = dst_root / dst_rel_str

                dst_path.parent.mkdir(parents=True, exist_ok=True)
                if dst_path.is_symlink() or dst_path.exists():
                    dst_path.unlink()

                try:
                    os.link(src_file, dst_path)
                    logger.debug(f"Created hardlink: {src_file} → {dst_path}")
                except OSError as e:
                    if e.errno == 18:
                        raise OSError(
                            f"❌ 跨文件系统无法创建硬链接: {src_file} → {dst_path}\n"
                            "请确保 src_root 和 dst_root 在同一挂载点。"
                        ) from e
                    if e.errno == 17:
                        raise FileExistsError(f"❌ 目标已存在: {dst_path}") from e
                    raise
