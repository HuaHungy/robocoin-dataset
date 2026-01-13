"""
Database Repository Name Update Script
======================================

This script updates the 'convert_path' in the 'datasets' table and the 'hard_link_path'
in the 'dataset_hard_link' table within the SQLite database. It sanitizes the
folder names in these paths while optionally preserving or removing
_hardlink/_qced_hardlink suffixes.

Usage:
    python scripts/hub_upload/update_db_repo_names.py --db-path db/datasets_new.db
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# Add the project root to sys.path to allow importing from robocoin_dataset
project_root = Path(__file__).resolve().parents[3]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from robocoin_dataset.hub_upload.repo_name_util import (  # noqa: E402
    process_folder_name,
    process_repo_name,
)


def update_db(db_path: str, preserve_suffix: bool = True) -> None:
    """
    Update convert_path in 'datasets' table and hard_link_path in 'dataset_hard_link' table.

    Args:
        db_path: Path to the SQLite database.
        preserve_suffix: Whether to preserve _hardlink/_qced_hardlink suffixes in DB paths.
                         If True, it uses process_folder_name. If False, it uses process_repo_name.
    """
    db_file = Path(db_path).expanduser().absolute()
    if not db_file.exists():
        print(f"Error: Database file not found at {db_file}")
        return

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    process_func = process_folder_name if preserve_suffix else process_repo_name

    # Update datasets table
    print("Updating 'datasets' table 'convert_path' column...")
    cursor.execute("SELECT id, convert_path FROM datasets")
    rows = cursor.fetchall()
    updated_datasets = 0
    for row_id, convert_path in rows:
        if convert_path:
            p = Path(convert_path)
            # Only modify the name part
            new_name = process_func(p.name)
            if new_name != p.name:
                new_path = str(p.parent / new_name)
                cursor.execute("UPDATE datasets SET convert_path = ? WHERE id = ?", (new_path, row_id))
                updated_datasets += 1

    # Update dataset_hard_link table
    print("Updating 'dataset_hard_link' table 'hard_link_path' column...")
    cursor.execute("SELECT id, hard_link_path FROM dataset_hard_link")
    rows = cursor.fetchall()
    updated_hardlinks = 0
    for row_id, hard_link_path in rows:
        if hard_link_path:
            p = Path(hard_link_path)
            new_name = process_func(p.name)
            if new_name != p.name:
                new_path = str(p.parent / new_name)
                cursor.execute("UPDATE dataset_hard_link SET hard_link_path = ? WHERE id = ?", (new_path, row_id))
                updated_hardlinks += 1

    conn.commit()
    conn.close()
    print(f"Finished. Updated {updated_datasets} datasets and {updated_hardlinks} hardlinks.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update repo names in database.")
    parser.add_argument("--db-path", type=str, default="db/datasets_new.db", help="Path to SQLite database")
    parser.add_argument("--remove-suffix", action="store_true", help="Remove _hardlink and _qced_hardlink suffixes from DB paths")
    args = parser.parse_args()

    # Default to preserving suffix in DB as it usually refers to local folders
    update_db(args.db_path, preserve_suffix=not args.remove_suffix)
