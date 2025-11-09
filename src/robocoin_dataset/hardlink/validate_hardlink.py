"""Validation utilities for hardlink structures.

This module contains all local, database-irrelevant operations:
- Source dataset validation
- Hardlink structure validation
- Hardlink creation (slow operation, no database access)
"""

import logging
from pathlib import Path

from robocoin_dataset.hardlink.make_hardlink import HardLinkCorresp

logger = logging.getLogger(__name__)


def validate_source_for_lerobot(source_path: Path) -> None:
    """Validate source dataset has required files for LeRobotDataset.

    Checks that source has the files needed by LeRobotDataset before
    attempting to create hardlinks. This prevents hardlink creation for
    incomplete datasets that would fail during dataloader detection.

    Required files (based on RepoHardLinkCorresp mapping):
    - meta/merged_info.json → will become meta/info.json in hardlink
    - meta/episodes.jsonl → will become meta/episodes.jsonl in hardlink

    Args:
        source_path: Source dataset directory

    Raises:
        FileNotFoundError: If required files are missing
    """
    required_files = [
        source_path / "meta" / "merged_info.json",
        source_path / "meta" / "episodes.jsonl",
    ]

    missing = [f for f in required_files if not f.exists()]
    if missing:
        raise FileNotFoundError(
            "Source dataset missing required files for LeRobotDataset:\n" +
            "\n".join(f"  - {f.relative_to(source_path)}" for f in missing) +
            "\n\nDataloader detection requires these files to load the dataset."
        )


def create_or_validate_hardlinks(src: Path, dst: Path) -> Path:
    """Check if hardlink structure exists or create new hardlinks.

    This is the slow operation that should be called outside of database sessions
    to avoid blocking other clients. Pure file system operation, no database access.

    Args:
        src: Source dataset directory
        dst: Target directory for hardlinks

    Returns:
        Path to the hardlink directory
    """
    from robocoin_dataset.hardlink.make_hardlink import (
        RepoHardLinkCorresp,
        create_hardlinks_from_correspondence,
    )

    hardlink_corresp = RepoHardLinkCorresp()

    # Check if hardlink structure exists -> Create if needed
    if dst.exists():
        try:
            if validate_hardlink(src, dst, hardlink_corresp):
                logger.info(f"Reusing existing hardlink structure: {dst}")
                return dst
        except Exception:
            pass

    # Create hardlinks
    logger.info(f"Creating hardlinks: {src} → {dst}")
    create_hardlinks_from_correspondence(src, dst, hardlink_corresp)
    logger.info(f"Hardlinks created successfully: {dst}")

    return dst


def validate_hardlink(
    src_root: str | Path,
    dst_root: str | Path,
    hard_link_corresp: HardLinkCorresp,
) -> bool:
    """Validate hardlink structure exists with expected files.

    Returns:
        True if hardlink structure exists with expected files, False otherwise
    """
    src_root = Path(src_root)
    dst_root = Path(dst_root)

    # Check if directories exist
    if not src_root.exists() or not dst_root.exists():
        return False

    # Validate file correspondence - just check if destination files exist
    for dst_rel in hard_link_corresp.file_corresp.values():
        dst_file = dst_root / dst_rel

        if not dst_file.exists() or not dst_file.is_file():
            return False

    # Validate directory correspondence (sampling approach)
    if hard_link_corresp.dir_corresp:
        for src_prefix, dst_prefix in hard_link_corresp.dir_corresp.items():
            # Ensure directory format
            src_prefix = src_prefix.rstrip("/") + "/"
            dst_prefix = dst_prefix.rstrip("/") + "/"

            # Check if any files exist in source directory
            src_dir = src_root / src_prefix.rstrip("/")
            if not src_dir.exists():
                continue

            # Validate at least one file exists in destination directory
            dst_dir = dst_root / dst_prefix.rstrip("/")
            if not dst_dir.exists():
                return False

            # Check if at least one corresponding file exists
            found_files = False
            for src_file in src_dir.rglob("*"):
                if not src_file.is_file() or src_file.is_symlink():
                    continue

                found_files = True
                rel_str = src_file.relative_to(src_root).as_posix()
                if rel_str.startswith(src_prefix):
                    dst_rel = dst_prefix + rel_str[len(src_prefix):]
                    dst_file = dst_root / dst_rel

                    if not dst_file.exists() or not dst_file.is_file():
                        return False
                    # Only check first file from each directory for efficiency
                    break

            if found_files and not dst_dir.exists():
                return False

    return True
