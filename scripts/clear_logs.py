import shutil
from pathlib import Path


def clear_logs() -> None:
    """
    Delete all log files and subfolders deeper than level 1 in the logs directory.
    Keep only the level 1 subfolders (direct children of logs/).
    """
    logs_dir = Path(__file__).parent.parent / "logs"

    if not logs_dir.exists():
        print(f"Logs directory does not exist: {logs_dir}")
        return

    print(f"Cleaning logs directory: {logs_dir}")
    print("-" * 60)

    deleted_files = 0
    deleted_folders = 0

    # Iterate through level 1 subfolders
    for level1_item in logs_dir.iterdir():
        if level1_item.is_dir():
            print(f"\nProcessing {level1_item.name}/")

            # Delete all contents of this level 1 folder
            for item in level1_item.iterdir():
                if item.is_file():
                    print(f"  Deleting file: {item.name}")
                    item.unlink()
                    deleted_files += 1
                elif item.is_dir():
                    print(f"  Deleting folder: {item.name}/")
                    shutil.rmtree(item)
                    deleted_folders += 1
        elif level1_item.is_file():
            # Delete files directly in logs/ directory
            print(f"Deleting file in logs/: {level1_item.name}")
            level1_item.unlink()
            deleted_files += 1

    print("\n" + "-" * 60)
    print(f"Done! Deleted {deleted_files} files and {deleted_folders} folders.")


if __name__ == "__main__":
    clear_logs()
