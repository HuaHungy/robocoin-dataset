#!/usr/bin/env python3
"""Reset upload status for testing.

This script prepares the database for upload testing by:
1. Setting visualize_check_status = COMPLETED ONLY for datasets where data_merge_status = COMPLETED
   (ensures only merged datasets are eligible for upload)
2. Resetting both ModelScope and HuggingFace upload statuses to PENDING (for all datasets)

Usage:
    python scripts/hub_upload/reset_for_upload_tst.py --db path/to/database.db
"""

import argparse
import logging
import sys
from pathlib import Path

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB, TaskStatus

logger = logging.getLogger(__name__)


def reset_upload_status(db_file: Path) -> int:
    """Reset upload status for both ModelScope and HuggingFace.

    CRITICAL: Only sets visualize_check_status = COMPLETED for datasets where
    data_merge_status = COMPLETED (ensures only merged datasets are eligible).
    Always sets all upload statuses to PENDING.

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
            visualize_set_count = 0

            for dataset in datasets:
                # CRITICAL: Only set visualize_check_status = COMPLETED if data_merge_status = COMPLETED
                # This ensures only merged datasets are eligible for upload
                if dataset.data_merge_status == TaskStatus.COMPLETED:
                    dataset.visualize_check_status = TaskStatus.COMPLETED
                    visualize_set_count += 1

                # Always reset both upload statuses to PENDING
                dataset.ms_upload_status = TaskStatus.PENDING
                dataset.hf_upload_status = TaskStatus.PENDING

                updated_count += 1

            # Commit changes
            session.commit()

            logger.info(f"Successfully reset {updated_count} datasets for upload testing")
            print(f"✅ Successfully reset {updated_count} datasets:", file=sys.stderr)
            print(f"   - visualize_check_status → COMPLETED (for {visualize_set_count} datasets with data_merge_status=COMPLETED)", file=sys.stderr)
            print("   - ms_upload_status → PENDING (all datasets)", file=sys.stderr)
            print("   - hf_upload_status → PENDING (all datasets)", file=sys.stderr)

            return 0

    except Exception as e:
        logger.error(f"Failed to reset upload status: {e}", exc_info=True)
        print(f"❌ Failed to reset upload status: {e}", file=sys.stderr)
        return 1


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Reset upload status for testing (sets visualize_check_status=COMPLETED for merged datasets, upload_status=PENDING for all)"
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

    logger.info(f"Resetting upload status in: {db_file}")
    print(f"🔄 Resetting upload status in: {db_file}", file=sys.stderr)

    return reset_upload_status(db_file)


if __name__ == "__main__":
    sys.exit(main())
