#!/usr/bin/env python3
"""
Script to delete all log files in logs/ directory while preserving folder structure.
"""
from pathlib import Path


def clear_logs(logs_dir: str = "logs") -> None:
    """
    Delete all files in the logs directory recursively, keeping folders intact.

    Args:
        logs_dir: Path to the logs directory (default: "logs")
    """
    logs_path = Path(logs_dir)

    if not logs_path.exists():
        print(f"Directory '{logs_dir}' does not exist.")
        return

    if not logs_path.is_dir():
        print(f"'{logs_dir}' is not a directory.")
        return

    deleted_count = 0
    error_count = 0

    # Walk through all files recursively
    for file_path in logs_path.rglob('*'):
        if file_path.is_file():
            try:
                file_path.unlink()
                print(f"Deleted: {file_path}")
                deleted_count += 1
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")
                error_count += 1

    print("\nSummary:")
    print(f"  Files deleted: {deleted_count}")
    print(f"  Errors: {error_count}")
    print("  Folders preserved (not deleted)")


if __name__ == "__main__":
    import sys

    # Allow custom logs directory as command line argument
    logs_directory = sys.argv[1] if len(sys.argv) > 1 else "logs"

    print(f"Clearing all files in '{logs_directory}' directory...")
    print("=" * 60)

    clear_logs(logs_directory)
