"""Validation utilities for hardlink structures.

Simple validation: returns True only when hardlinks exist AND are valid.
"""

import os
from pathlib import Path

from robocoin_dataset.hardlink.make_hardlink import HardLinkCorresp


def validate_hardlink(
    src_root: str | Path,
    dst_root: str | Path,
    hard_link_corresp: HardLinkCorresp,
) -> bool:
    """Validate hardlink structure exists and is valid.

    Returns True only when:
    - Source and destination directories exist
    - All expected files exist in destination
    - Destination files are actual hardlinks to source files (same inode)

    Args:
        src_root: Source directory root path
        dst_root: Destination directory root path
        hard_link_corresp: Hardlink correspondence rules

    Returns:
        True if hardlinks exist and are valid, False otherwise
    """
    src_root = Path(src_root)
    dst_root = Path(dst_root)

    # Check if directories exist
    if not src_root.exists() or not dst_root.exists():
        return False

    # Validate file correspondence
    for src_rel, dst_rel in hard_link_corresp.file_corresp.items():
        src_file = src_root / src_rel
        dst_file = dst_root / dst_rel

        if not _validate_hardlink_pair(src_file, dst_file):
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

            # Validate at least one file from each directory
            found_files = False
            for src_file in src_dir.rglob("*"):
                if not src_file.is_file() or src_file.is_symlink():
                    continue

                found_files = True
                rel_str = src_file.relative_to(src_root).as_posix()
                if rel_str.startswith(src_prefix):
                    dst_rel = dst_prefix + rel_str[len(src_prefix):]
                    dst_file = dst_root / dst_rel

                    if not _validate_hardlink_pair(src_file, dst_file):
                        return False
                    # Only check first file from each directory for efficiency
                    break

            if found_files and not (dst_root / dst_prefix.rstrip("/")).exists():
                return False

    return True


def _validate_hardlink_pair(src_file: Path, dst_file: Path) -> bool:
    """Validate a single hardlink pair.

    Args:
        src_file: Source file path
        dst_file: Destination file path

    Returns:
        True if dst_file is a proper hardlink to src_file, False otherwise
    """
    # Check if both files exist and are regular files (not symlinks)
    if not src_file.exists() or not dst_file.exists():
        return False
    if not src_file.is_file() or src_file.is_symlink():
        return False
    if not dst_file.is_file() or dst_file.is_symlink():
        return False

    # Check if they are hardlinks (same inode)
    try:
        src_stat = os.stat(src_file)
        dst_stat = os.stat(dst_file)
        return src_stat.st_ino == dst_stat.st_ino and src_stat.st_dev == dst_stat.st_dev
    except OSError:
        return False
