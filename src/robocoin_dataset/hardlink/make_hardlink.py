#!/usr/bin/env python3
"""
Script to create hard links from actual data pipeline structure to LeRobot dataset standard structure.

This script creates a LeRobot-compatible directory structure with hard links pointing to
the actual data files from your production pipeline.

NOTE: Hard links have important limitations compared to symbolic links:
  - Hard links can only be created for files, not directories
  - Hard links must be on the same filesystem as the source
  - For directories, this script recursively creates the structure and hard links all files

USAGE:
  # Use default target (creates '<source_name>_hardlink' next to source):
  python make_hardlink.py --source /path/to/your/pipeline/data
  python make_hardlink.py -s /path/to/your/pipeline/data

  # Specify custom target directory:
  python ./src/robocoin_dataset/hub_upload/hardlink/make_hardlink.py --source /path/to/your/pipeline/data --target /path/to/lerobot/dataset
  python ./src/robocoin_dataset/hub_upload/hardlink/make_hardlink.py -s /path/to/your/pipeline/data -t /path/to/lerobot/dataset
"""

import argparse
import json
import os
from pathlib import Path


def create_hardlink(target_path: Path, source_path: Path, relative: bool = True) -> None:
    """
    Create a hard link.

    Args:
        target_path: The path where the hardlink will be created
        source_path: The path that the hardlink will point to
        relative: Unused for hard links (kept for compatibility)

    Note: Hard links can only be created for files, not directories.
          Hard links must be on the same filesystem.
    """
    # Remove existing hardlink or file if it exists
    if target_path.exists() or target_path.is_symlink():
        print(f"  Removing existing: {target_path}")
        if target_path.is_dir() and not target_path.is_symlink():
            import shutil
            shutil.rmtree(target_path)
        else:
            target_path.unlink()

    # Ensure parent directory exists
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Create the hard link (hard links are always absolute at filesystem level)
    print(f"  Creating hardlink: {target_path} -> {source_path}")
    os.link(source_path, target_path)


def hardlink_directory_recursive(source_dir: Path, target_dir: Path) -> None:
    """
    Recursively create directory structure and hard link all files.

    Since hard links cannot be created for directories, this function:
    1. Creates the target directory structure
    2. Hard links all files within the directory tree

    Args:
        source_dir: Source directory to copy structure from
        target_dir: Target directory to create structure in
    """
    print(f"  Recursively hard linking directory: {source_dir} -> {target_dir}")

    # Create target directory
    target_dir.mkdir(parents=True, exist_ok=True)

    # Walk through source directory
    for item in source_dir.rglob('*'):
        # Calculate relative path from source_dir
        relative_path = item.relative_to(source_dir)
        target_item = target_dir / relative_path

        if item.is_dir():
            # Create directory in target
            target_item.mkdir(parents=True, exist_ok=True)
            print(f"    Created directory: {target_item}")
        else:
            # Create hard link for file
            if target_item.exists():
                target_item.unlink()
            target_item.parent.mkdir(parents=True, exist_ok=True)
            os.link(item, target_item)
            print(f"    Hard linked file: {target_item}")


def load_hardlink_config(config_path: Path | None = None) -> list[dict]:
    """
    Load hardlink configuration from JSON file.

    Args:
        config_path: Path to the configuration JSON file. If None, uses default config
                    file located next to this script.

    Returns:
        List of dictionaries with keys: 'target', 'source', 'type', 'is_folder', 'description'
        Example:
        [
            {
                'target': 'data',
                'source': 'merged_data',
                'type': 'folder',
                'is_folder': True,
                'description': 'LeRobot data directory'
            },
            ...
        ]
    """
    if config_path is None:
        # Default to config file in the same directory as this script
        script_dir = Path(__file__).parent
        config_path = script_dir / "hardlink_config.json"

    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}\n"
            f"Please create a hardlink_config.json file or specify a custom config path."
        )

    print(f"   Reading configuration from: {config_path}")

    with open(config_path) as f:
        config = json.load(f)

    mappings = []
    for idx, item in enumerate(config.get("mappings", []), 1):
        target = item.get("target")
        source = item.get("source")
        mapping_type = item.get("type")
        description = item.get("description", "")

        # Validate required fields
        if not target or not source or not mapping_type:
            raise ValueError(
                f"Invalid mapping entry #{idx}: {item}\n"
                f"Each mapping must have 'target', 'source', and 'type' fields."
            )

        # Validate mapping type
        if mapping_type.lower() not in ["folder", "file"]:
            raise ValueError(
                f"Invalid type '{mapping_type}' in mapping #{idx}\n"
                f"Type must be either 'folder' or 'file'."
            )

        is_folder = mapping_type.lower() == "folder"

        # Create mapping dictionary
        mapping = {
            "target": target,
            "source": source,
            "type": mapping_type,
            "is_folder": is_folder,
            "description": description
        }
        mappings.append(mapping)

    return mappings


def create_lerobot_hardlink_structure(
    source_dir: Path,
    target_dir: Path,
    relative: bool = True,
    skip_missing: bool = False,
    config_path: Path | None = None
) -> None:
    """
    Create LeRobot-compatible directory structure with hard links.

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
        ├── annotations # directory with hard linked files -> annotations/
        ├── data # directory with hard linked files -> merged_data/
        │   └── chunk-000
        │       ├── episode_000000.parquet
        │       └── episode_000001.parquet
        ├── meta
        │   ├── episodes.jsonl # hardlink -> meta/episodes.jsonl
        │   ├── episodes_stats.jsonl # hardlink -> meta/merged_episodes_stats.jsonl
        │   ├── info.json # hardlink -> meta/merged_info.json
        │   └── tasks.jsonl # hardlink -> meta/tasks.jsonl
        └── videos # directory with hard linked files -> videos/
            └── chunk-000
                ├── observation.images.cam_high_rgb
                ├── observation.images.cam_left_wrist_rgb
                └── observation.images.cam_right_wrist_rgb

    Args:
        source_dir: Directory containing the actual data from your pipeline
        target_dir: Directory where LeRobot-compatible structure will be created
        relative: Unused for hard links (kept for compatibility)
        skip_missing: If True, skip missing source files; otherwise raise error
        config_path: Path to custom configuration JSON file. If None, uses default config.
    """
    print(f"\nCreating LeRobot dataset structure at: {target_dir}")
    print(f"Source data directory: {source_dir}\n")

    # Ensure target directory exists
    target_dir.mkdir(parents=True, exist_ok=True)

    # Load hardlink mappings from configuration file
    print("📋 Loading hardlink configuration...")
    hardlink_mappings = load_hardlink_config(config_path)
    print(f"   Found {len(hardlink_mappings)} mapping(s) in configuration\n")

    # Create meta directory (without hardlinking the entire folder)
    print(f"📁 Creating meta directory: {target_dir / 'meta'}")
    (target_dir / "meta").mkdir(exist_ok=True)

    # Create hardlinks using configuration
    for idx, mapping in enumerate(hardlink_mappings, 1):
        target_rel = mapping["target"]
        source_rel = mapping["source"]
        is_folder = mapping["is_folder"]
        description = mapping.get("description", "")

        target_path = target_dir / target_rel
        source_path = source_dir / source_rel

        # Display mapping info
        mapping_type_emoji = "📁" if is_folder else "📄"
        print(f"\n{mapping_type_emoji} Mapping #{idx}: {target_rel}")
        print(f"   Source: {source_rel}")
        if description:
            print(f"   Info: {description}")

        # Check if source exists
        if not source_path.exists():
            if skip_missing:
                print(f"   ⚠️  Skipping (source not found): {source_path}")
                continue
            raise FileNotFoundError(
                f"Source path not found for mapping #{idx}:\n"
                f"  Expected: {source_path}\n"
                f"  Mapping: {target_rel} -> {source_rel}"
            )

        # Handle directories vs files differently for hard links
        if is_folder:
            if not source_path.is_dir():
                print(f"   ⚠️  Warning: Expected folder but found file: {source_path}")
            else:
                # Recursively create directory structure and hardlink all files
                print("   Creating directory structure and linking files...")
                hardlink_directory_recursive(source_path, target_path)
        else:
            if not source_path.is_file():
                print(f"   ⚠️  Warning: Expected file but found folder: {source_path}")
            else:
                # Create hard link for single file
                print("   Creating file hardlink...")
                create_hardlink(target_path, source_path, relative)

    print("\n✅ Hard link structure created successfully!")
    print("\n📋 Summary:")
    print(f"   Source (your pipeline data): {source_dir}")
    print(f"   Target (LeRobot structure):  {target_dir}")
    print("   The target directory now has the LeRobot standard structure with hard links to your data.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create LeRobot dataset structure with hard links to actual data pipeline files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default target (creates 'hardlinked_<source_name>' next to source)
  %(prog)s --source /path/to/source/data
  %(prog)s -s /path/to/source/data

  # Specify custom target directory
  %(prog)s --source /path/to/source/data --target /path/to/target/lerobot_dataset
  %(prog)s -s /path/to/source/data -t /path/to/target/lerobot_dataset

  # Skip missing source files during hardlink creation instead of raising errors
  %(prog)s -s /path/to/source/data --hardlink-skip-missing

  # Use a custom configuration file
  %(prog)s -s /path/to/source/data -c /path/to/custom_config.json

Note: Hard links require source and target to be on the same filesystem.
      Hard links cannot be created for directories (files within directories are hard linked instead).
      The default configuration file is 'hardlink_config.json' located next to this script.
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
             "If not specified, creates 'hardlinked_<source_dir_name>' in the same parent directory as source_dir"
    )

    parser.add_argument(
        "--hardlink-skip-missing",
        action="store_true",
        help="Skip missing source files during hardlink creation instead of raising errors"
    )

    parser.add_argument(
        "-c", "--config",
        dest="config_path",
        type=Path,
        default=None,
        help="Path to custom hardlink configuration JSON file. "
             "If not specified, uses 'hardlink_config.json' in the same directory as this script"
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
        # Default: create '<source_name>_hardlink' in the same parent directory
        source_name = source_dir.name
        target_dir = source_dir.parent / f"{source_name}_hardlink"
        print(f"No target directory specified. Using default: {target_dir}")
    else:
        target_dir = args.target_dir.resolve()

    # Validate config file if specified
    if args.config_path is not None:
        if not args.config_path.exists():
            parser.error(f"Configuration file does not exist: {args.config_path}")
        config_path = args.config_path.resolve()
    else:
        config_path = None

    # Create the hardlink structure
    try:
        create_lerobot_hardlink_structure(
            source_dir=source_dir,
            target_dir=target_dir,
            relative=True,  # Unused for hard links, kept for compatibility
            skip_missing=args.hardlink_skip_missing,
            config_path=config_path
        )
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
