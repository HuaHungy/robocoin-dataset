#!/usr/bin/env python3
"""
Script to create symbolic links from actual data pipeline structure to LeRobot dataset standard structure.

This script creates a LeRobot-compatible directory structure with symbolic links pointing to
the actual data files from your production pipeline.

USAGE:
  # Use default target (creates '<source_name>_symlink' next to source):
  python make_data_sym_links.py --source /path/to/your/pipeline/data
  python make_data_sym_links.py -s /path/to/your/pipeline/data

  # Specify custom target directory:
  python make_data_sym_links.py --source /path/to/your/pipeline/data --target /path/to/lerobot/dataset
  python make_data_sym_links.py -s /path/to/your/pipeline/data -t /path/to/lerobot/dataset
"""

import argparse
import os
from pathlib import Path


def create_symlink(target_path: Path, source_path: Path, relative: bool = True) -> None:
    """
    Create a symbolic link.

    Args:
        target_path: The path where the symlink will be created
        source_path: The path that the symlink will point to
        relative: If True, create relative symlinks; otherwise use absolute paths
    """
    # Remove existing symlink or file if it exists
    if target_path.exists() or target_path.is_symlink():
        print(f"  Removing existing: {target_path}")
        if target_path.is_dir() and not target_path.is_symlink():
            import shutil
            shutil.rmtree(target_path)
        else:
            target_path.unlink()

    # Ensure parent directory exists
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Calculate relative path if needed
    if relative:
        try:
            link_source = os.path.relpath(source_path, target_path.parent)
        except ValueError:
            # If paths are on different drives (Windows), fall back to absolute
            link_source = str(source_path.absolute())
    else:
        link_source = str(source_path.absolute())

    # Create the symlink
    print(f"  Creating symlink: {target_path} -> {link_source}")
    os.symlink(link_source, target_path)


def create_lerobot_symlink_structure(
    source_dir: Path,
    target_dir: Path,
    relative: bool = True,
    skip_missing: bool = False
) -> None:
    """
    Create LeRobot-compatible directory structure with symbolic links.

    Source structure (e.g., /dataloader_test/fake_ori_data_001):
        ├── annotations/
        │   └── subtask_annotations.jsonl
        ├── data/ (max 1000 episodes per chunk)
        │   └── chunk-000 ... chunk-001 ... chunk-002/
        ├── eef_sim_data/
        │   └── chunk-000 ... chunk-001 ... chunk-002/
        ├── merged_data/ (max 1000 episodes per chunk)
        │   └── chunk-000 ... chunk-001 ... chunk-002/
        ├── state_action_data/
        │   └── chunk-000 ... chunk-001 ... chunk-002/
        ├── subtask_annotation_data/
        │   └── chunk-000 ... chunk-001 ... chunk-002/
        ├── meta/
        │   ├── eef_sim_info.json
        │   ├── episodes.jsonl
        │   ├── episodes_stats.jsonl
        │   ├── info.json
        │   ├── merged_episodes_stats.jsonl
        │   ├── merged_info.json
        │   ├── state_action_info.json
        │   ├── subtask_annotation_info.json
        │   └── tasks.jsonl
        └── videos/
            └── chunk-000/
                ├── observation.images.cam_high_rgb/
                ├── observation.images.cam_left_wrist_rgb/
                └── observation.images.cam_right_wrist_rgb/

    Target structure (LeRobot-compatible):
        ├── annotations # symlink -> annotations/
        ├── data # symlink -> merged_data/
        │   └── chunk-000
        │       ├── episode_000000.parquet
        │       └── episode_000001.parquet
        ├── meta
        │   ├── episodes.jsonl # symlink -> meta/episodes.jsonl
        │   ├── episodes_stats.jsonl # symlink -> meta/merged_episodes_stats.jsonl
        │   ├── info.json # symlink -> meta/merged_info.json
        │   └── tasks.jsonl # symlink -> meta/tasks.jsonl
        └── videos # symlink -> videos/
            └── chunk-000
                ├── observation.images.cam_high_rgb
                ├── observation.images.cam_left_wrist_rgb
                └── observation.images.cam_right_wrist_rgb

    Args:
        source_dir: Directory containing the actual data from your pipeline
        target_dir: Directory where LeRobot-compatible structure will be created
        relative: If True, create relative symlinks; otherwise use absolute paths
        skip_missing: If True, skip missing source files; otherwise raise error
    """
    print(f"\nCreating LeRobot dataset structure at: {target_dir}")
    print(f"Source data directory: {source_dir}\n")

    # Ensure target directory exists
    target_dir.mkdir(parents=True, exist_ok=True)

    # Define symlink mappings: (target_path_in_lerobot_structure, source_path_in_pipeline, is_folder)
    # Target uses LeRobot standard names, Source uses your pipeline names
    symlink_mappings = [
        # Folder-level symlinks
        ("annotations", "annotations", True),
        ("data", "merged_data", True),  # LeRobot 'data/' -> pipeline 'merged_data/'
        ("videos", "videos", True),

        # File-level symlinks in meta/
        ("meta/episodes.jsonl", "meta/episodes.jsonl", False),
        ("meta/episodes_stats.jsonl", "meta/merged_episodes_stats.jsonl", False),  # LeRobot standard name
        ("meta/info.json", "meta/merged_info.json", False),  # LeRobot 'info.json' -> pipeline 'merged_info.json'
        ("meta/tasks.jsonl", "meta/tasks.jsonl", False),
    ]

    # Create meta directory (without symlinking the entire folder)
    print(f"📁 Creating meta directory: {target_dir / 'meta'}")
    (target_dir / "meta").mkdir(exist_ok=True)

    # Create symlinks
    for target_rel, source_rel, is_folder in symlink_mappings:
        target_path = target_dir / target_rel
        source_path = source_dir / source_rel

        # Check if source exists
        if not source_path.exists():
            if skip_missing:
                print(f"⚠️  Skipping (source not found): {source_rel}")
                continue
            raise FileNotFoundError(f"Source path not found: {source_path}")

        # Verify type matches expectation
        if is_folder and not source_path.is_dir():
            print(f"⚠️  Warning: Expected folder but found file: {source_path}")
        elif not is_folder and not source_path.is_file():
            print(f"⚠️  Warning: Expected file but found folder: {source_path}")

        create_symlink(target_path, source_path, relative)

    print("\n✅ Symbolic link structure created successfully!")
    print("\n📋 Summary:")
    print(f"   Source (your pipeline data): {source_dir}")
    print(f"   Target (LeRobot structure):  {target_dir}")
    print("   The target directory now has the LeRobot standard structure with symlinks to your data.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create LeRobot dataset structure with symbolic links to actual data pipeline files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default target (creates 'symlinked_<source_name>' next to source)
  %(prog)s --source /path/to/source/data
  %(prog)s -s /path/to/source/data

  # Specify custom target directory
  %(prog)s --source /path/to/source/data --target /path/to/target/lerobot_dataset
  %(prog)s -s /path/to/source/data -t /path/to/target/lerobot_dataset

  # Create symlinks with absolute paths instead of relative
  %(prog)s -s /path/to/source/data --absolute

  # Skip missing source files during symlink creation instead of raising errors
  %(prog)s -s /path/to/source/data --symlink-skip-missing
        """
    )

    parser.add_argument(
        "-s", "--source",
        dest="source_dir",
        type=Path,
        required=True,
        help="Source directory containing your actual data pipeline files"
    )

    parser.add_argument(
        "-t", "--target",
        dest="target_dir",
        type=Path,
        default=None,
        help="Target directory where LeRobot-compatible structure will be created. "
             "If not specified, creates 'symlinked_<source_dir_name>' in the same parent directory as source_dir"
    )

    parser.add_argument(
        "--absolute",
        action="store_true",
        help="Create absolute symlinks instead of relative ones (default: relative)"
    )

    parser.add_argument(
        "--symlink-skip-missing",
        action="store_true",
        help="Skip missing source files during symlink creation instead of raising errors"
    )

    args = parser.parse_args()

    # Validate source directory exists
    if not args.source_dir.exists():
        parser.error(f"Source directory does not exist: {args.source_dir}")

    if not args.source_dir.is_dir():
        parser.error(f"Source path is not a directory: {args.source_dir}")

    # Resolve source directory to absolute path
    source_dir = args.source_dir.resolve()

    # Determine target directory
    if args.target_dir is None:
        # Default: create '<source_name>_symlink' in the same parent directory
        source_name = source_dir.name
        target_dir = source_dir.parent / f"{source_name}_symlink"
        print(f"No target directory specified. Using default: {target_dir}")
    else:
        target_dir = args.target_dir.resolve()

    # Create the symlink structure
    try:
        create_lerobot_symlink_structure(
            source_dir=source_dir,
            target_dir=target_dir,
            relative=not args.absolute,
            skip_missing=args.symlink_skip_missing
        )
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
