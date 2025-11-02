#!/usr/bin/env python3
"""Clear or reset a target SQLite DB to an unwritten state.

Two modes:
1) file (default): remove the DB file entirely.
2) truncate: delete all rows from the 'datasets' table ONLY (no schema change).

Examples:
  python scripts/database_transfer/clear_target_db.py \
    --db /home/rogerspyke/projects/robocoin-dataset/examples/database_transfer_test/datasets_new.db

  python scripts/database_transfer/clear_target_db.py \
    --db /abs/path/to/examples/database_transfer_test/dataset_new.db \
    --mode truncate
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

LOGGER = logging.getLogger("clear_target_db")


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clear/reset a target SQLite DB for testing")
    parser.add_argument("--db", type=Path, required=True, help="Path to SQLite DB file to clear/reset")
    parser.add_argument(
        "--mode",
        choices=["file", "truncate"],
        default="file",
        help="file=delete the DB file; truncate=DELETE FROM datasets",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    return parser.parse_args(argv)


def _delete_file(db_path: Path) -> None:
    if db_path.exists():
        LOGGER.info("[RESET] Removing DB file: %s", db_path)
        os.remove(db_path)
    else:
        LOGGER.info("[RESET] DB file not found (already clean): %s", db_path)


def _truncate_datasets(db_path: Path) -> None:
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        LOGGER.info("[RESET] Deleting all rows from 'datasets' in: %s", db_path)
        conn.execute(text("DELETE FROM datasets"))


def main() -> None:
    args = parse_args(sys.argv[1:])
    _setup_logging(args.verbose)

    db_path = Path(args.db).expanduser().absolute()
    if args.mode == "file":
        _delete_file(db_path)
    else:
        _truncate_datasets(db_path)
    LOGGER.info("[DONE] Reset complete: %s (mode=%s)", db_path, args.mode)


if __name__ == "__main__":
    main()
