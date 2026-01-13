"""
Local Folder Batch Renaming Script
==================================

This script recursively (at the first-level) renames subdirectories within a target
directory to match the sanitized naming convention required for Hugging Face Hub.

Usage:
    python scripts/hub_upload/rename_local_folders.py /path/to/datasets/
    python scripts/hub_upload/rename_local_folders.py /mnt/nas/synnas/成功区
"""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parents[2]
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from robocoin_dataset.hub_upload.repo_name_util import rename_folder  # noqa: E402


def rename_subdirectories(target_dir: str) -> None:
    """
    Iterate through first-level subdirectories of target_dir and rename them using sanitized names.
    """
    target_path = Path(target_dir).expanduser().resolve()
    if not target_path.is_dir():
        print(f"Error: {target_path} is not a directory.")
        return

    print(f"Processing first-level subdirectories in: {target_path}")

    # We need to list them first because renaming folders while iterating can lead to issues
    # although for first-level it's usually safe if we don't go deeper.
    subdirs = [d for d in target_path.iterdir() if d.is_dir()]

    renamed_count = 0
    error_count = 0

    for subdir in subdirs:
        old_name = subdir.name
        try:
            new_name = rename_folder(subdir)
            if old_name != new_name:
                print(f"  ✅ Renamed: {old_name} -> {new_name}")
                renamed_count += 1
            # else:
            #     print(f"  [Skip] Already sanitized: {old_name}")
        except Exception as e:
            print(f"  ❌ Failed to rename {old_name}: {e}")
            error_count += 1

    print("\nFinished processing.")
    print(f"Total renamed: {renamed_count}")
    if error_count > 0:
        print(f"Total errors: {error_count}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rename first-level subdirectories to sanitized names.")
    parser.add_argument("target_dir", type=str, help="Path to the directory containing subdirectories to rename")

    args = parser.parse_args()
    rename_subdirectories(args.target_dir)
