#!/usr/bin/env python3
"""Reset data_loader_detection_status to PENDING for all datasets.

This script resets the data_loader_detection_status field in the datasets table
to PENDING for all records in the specified database.
And only reset the qced_repo_gen_status to COMPLETED which has non-empty<dataset_uuid, hard_link_path>
pair in the dataset_hard_link table.

Usage:
    python scripts/dataloader/reset_for_tst.py --db path/to/database.db
"""

import argparse
import logging
import sys
from pathlib import Path

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB, DatasetHardLinkDB, TaskStatus

logger = logging.getLogger(__name__)


def reset_dataloader_detection_status(db_file: Path) -> int:
    """Reset all data_loader_detection_status to PENDING and qced_repo_gen_status to COMPLETED for datasets with hard links.

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
                return 0

            # Get dataset_uuids that have hard links (non-empty hard_link_path)
            hard_link_uuids = set(
                session.query(DatasetHardLinkDB.dataset_uuid)
                .filter(DatasetHardLinkDB.hard_link_path.isnot(None))
                .filter(DatasetHardLinkDB.hard_link_path != "")
                .distinct()
                .all()
            )
            hard_link_uuids = {uuid[0] for uuid in hard_link_uuids}

            logger.info(f"Found {len(hard_link_uuids)} datasets with hard links")

            # Reset status for all datasets
            updated_count = 0
            qced_repo_gen_updated_count = 0
            for dataset in datasets:
                # Always reset data_loader_detection_status to PENDING
                dataset.data_loader_detection_status = TaskStatus.PENDING
                dataset.data_loader_detection_err_msg = None
                updated_count += 1

                # Reset qced_repo_gen_status to COMPLETED only for datasets with hard links
                if dataset.dataset_uuid in hard_link_uuids:
                    dataset.qced_repo_gen_status = TaskStatus.COMPLETED
                    qced_repo_gen_updated_count += 1

            # Commit changes
            session.commit()

            logger.info(
                f"Successfully reset {updated_count} datasets' data_loader_detection_status to PENDING"
            )
            logger.info(
                f"Successfully reset {qced_repo_gen_updated_count} datasets' qced_repo_gen_status to COMPLETED"
            )

            return 0

    except Exception as e:
        logger.exception(f"Failed to reset dataloader detection status: {e}")
        return 1


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Reset data_loader_detection_status to PENDING for all datasets and qced_repo_gen_status to COMPLETED for datasets with hard links"
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
        return 2

    if not db_file.is_file():
        logger.error(f"Not a file: {db_file}")
        return 2

    logger.info(f"Resetting dataloader detection status and qced_repo_gen status in: {db_file}")

    return reset_dataloader_detection_status(db_file)


if __name__ == "__main__":
    sys.exit(main())
