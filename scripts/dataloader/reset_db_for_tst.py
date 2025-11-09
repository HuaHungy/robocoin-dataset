#!/usr/bin/env python3
"""Reset data_loader_detection_status to PENDING for all datasets.

This script resets the data_loader_detection_status field in the datasets table
to PENDING for all records in the specified database.

Usage:
    python scripts/dataloader/reset_for_tst.py --db path/to/database.db
"""

import argparse
import logging
import sys
from pathlib import Path

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB, TaskStatus

logger = logging.getLogger(__name__)


def reset_dataloader_detection_status(db_file: Path) -> int:
    """Reset all data_loader_detection_status to PENDING.

    Args:
        db_file: Path to the SQLite database

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        db = DatasetDatabase(db_file)

        with db.with_session() as session:
            # Query all datasets
            datasets = session.query(DatasetDB).all()

            if not datasets:
                logger.warning("No datasets found in database")
                print("⚠️  No datasets found in database", file=sys.stderr)
                return 0

            # Reset status for all datasets
            updated_count = 0
            for dataset in datasets:
                dataset.data_loader_detection_status = TaskStatus.PENDING
                updated_count += 1

            # Commit changes
            session.commit()

            logger.info(f"Successfully reset {updated_count} datasets to PENDING")
            print(f"✅ Successfully reset {updated_count} datasets to PENDING", file=sys.stderr)

            return 0

    except Exception as e:
        logger.error(f"Failed to reset dataloader detection status: {e}", exc_info=True)
        print(f"❌ Failed to reset dataloader detection status: {e}", file=sys.stderr)
        return 1


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Reset data_loader_detection_status to PENDING for all datasets"
    )
    parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="Path to SQLite database",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Validate database path
    db_file = args.db.expanduser().absolute()

    if not db_file.exists():
        logger.error(f"Database not found: {db_file}")
        print(f"❌ Database not found: {db_file}", file=sys.stderr)
        return 2

    if not db_file.is_file():
        logger.error(f"Not a file: {db_file}")
        print(f"❌ Not a file: {db_file}", file=sys.stderr)
        return 2

    logger.info(f"Resetting dataloader detection status in: {db_file}")
    print(f"🔄 Resetting dataloader detection status in: {db_file}", file=sys.stderr)

    return reset_dataloader_detection_status(db_file)


if __name__ == "__main__":
    sys.exit(main())
