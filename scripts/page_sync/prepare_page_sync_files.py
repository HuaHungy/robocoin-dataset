#!/usr/bin/env python3
"""
CLI Script for Page Sync - Construct Assets

Main entrance point for syncing dataset information to the page project.
This script extracts YAML files and compressed videos from the database
and organizes them into the page project's assets directory.
"""

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync dataset information to page project - construct assets (YAML files and videos)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with required arguments
  python scripts/page_sync/construct_assets.py \\
    --db-path db/datasets_new.db \\
    --target-dir /path/to/page-project

  # With custom video size and debug logging
  python scripts/page_sync/construct_assets.py \\
    --db-path db/datasets_new.db \\
    --target-dir /path/to/page-project \\
    --target-size-kb 1000 \\
    --log-level DEBUG

Output Structure:
  target-dir/
    assets/
      dataset_info/
        {dataset_name}.yml
        ...
      videos/
        {dataset_name}.mp4
        ...
        """,
    )

    parser.add_argument(
        "--db-path",
        type=str,
        required=True,
        help="Path to the SQLite database file (e.g., db/datasets_new.db)",
    )

    parser.add_argument(
        "--target-dir",
        type=str,
        required=True,
        help="Root directory of the page project where assets will be created",
    )

    parser.add_argument(
        "--target-size-kb",
        type=int,
        default=512,
        help="Target size for compressed videos in KB (default: 500)",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    # Validate paths
    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"Error: Database file not found: {args.db_path}", file=sys.stderr)
        sys.exit(1)

    target_dir = Path(args.target_dir)
    if not target_dir.exists():
        print(f"Error: Target directory not found: {args.target_dir}", file=sys.stderr)
        print("Please create the directory first or check the path.", file=sys.stderr)
        sys.exit(1)

    # Import and run the main function
    from robocoin_dataset.page_sync.page_sync import main as page_sync_main

    print("Starting page sync operation...")
    print(f"  Database: {args.db_path}")
    print(f"  Target: {args.target_dir}")
    print(f"  Video size: {args.target_size_kb} KB")
    print(f"  Log level: {args.log_level}")
    print()

    try:
        page_sync_main(
            db_path=str(db_path.absolute()),
            target_dir=str(target_dir.absolute()),
            target_size_kb=args.target_size_kb,
            log_level=args.log_level,
        )
        print("\n✓ Page sync completed successfully!")
    except KeyboardInterrupt:
        print("\n✗ Operation cancelled by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"\n✗ Error during page sync: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
