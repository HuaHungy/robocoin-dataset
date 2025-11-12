#!/usr/bin/env python3
"""Reset data_loader_detection_status to PENDING and set qced_repo_gen_status for datasets with hardlinks.

This script:
- Resets data_loader_detection_status to PENDING for ALL datasets
- Sets qced_repo_gen_status to COMPLETED for datasets that have a hardlink record with valid hard_link_path

Usage:
    python scripts/dataloader/reset_db_for_load_tst.py --db path/to/database.db
"""

import argparse
import logging
import sys
from pathlib import Path

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB, DatasetHardLinkDB, TaskStatus

logger = logging.getLogger(__name__)


def reset_dataloader_detection_status(db_file: Path) -> int:
    """Reset all data_loader_detection_status to PENDING and set qced_repo_gen_status to COMPLETED for datasets with hardlinks.

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
                logger.info("⚠️  No datasets found in database")
                return 0

            # Reset status for all datasets
            updated_count = 0
            qced_updated_count = 0

            for dataset in datasets:
                # Always set data_loader_detection_status to PENDING
                dataset.data_loader_detection_status = TaskStatus.PENDING
                updated_count += 1

                # Check if dataset has a hardlink record with valid path
                hardlink_record = session.query(DatasetHardLinkDB).filter(
                    DatasetHardLinkDB.dataset_uuid == dataset.dataset_uuid
                ).first()

                if hardlink_record and hardlink_record.hard_link_path:
                    dataset.qced_repo_gen_status = TaskStatus.COMPLETED
                    qced_updated_count += 1

            # Commit changes
            session.commit()

            logger.info(f"Successfully reset {updated_count} datasets to PENDING for data_loader_detection_status")
            logger.info(f"Successfully set {qced_updated_count} datasets to COMPLETED for qced_repo_gen_status (with hardlinks)")
            logger.info(f"✅ Successfully reset {updated_count} datasets to PENDING for data_loader_detection_status")
            logger.info(f"✅ Successfully set {qced_updated_count} datasets to COMPLETED for qced_repo_gen_status (with hardlinks)")

            return 0

    except Exception as e:
        logger.error(f"Failed to reset dataloader detection status: {e}", exc_info=True)
        logger.error(f"❌ Failed to reset dataloader detection status: {e}")
        return 1


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Reset data_loader_detection_status to PENDING for all datasets and set qced_repo_gen_status to COMPLETED for datasets with hardlinks"
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
        logger.error(f"❌ Database not found: {db_file}")
        return 2

    if not db_file.is_file():
        logger.error(f"Not a file: {db_file}")
        logger.error(f"❌ Not a file: {db_file}")
        return 2

    logger.info(f"Resetting dataloader detection status in: {db_file}")
    logger.info(f"🔄 Resetting dataloader detection status in: {db_file}")

    return reset_dataloader_detection_status(db_file)


if __name__ == "__main__":
    sys.exit(main())
