#!/usr/bin/env python3
"""Reset hub upload statuses to COMPLETED and dataset_info_sync_status to PENDING.

This script resets the hub upload statuses (HuggingFace and ModelScope) to COMPLETED
and dataset_info_sync_status to PENDING for all records in the specified database.

Usage:
    python scripts/page_sync/reset_db_for_page_tst.py --db path/to/database.db
"""

import argparse
import logging
import sys
from pathlib import Path

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB, DatasetHardLinkDB, TaskStatus

logger = logging.getLogger(__name__)


def _get_hub_field_prefix(dataset_table: type[DatasetDB]) -> tuple[str, str]:
    """Return the correct field prefixes for both HuggingFace and ModelScope hubs.

    Tries short versions first (hf/ms), then long versions (huggingface/modelscope).
    """
    if hasattr(dataset_table, "hf_upload_status"):
        hf_prefix = "hf"
    elif hasattr(dataset_table, "huggingface_upload_status"):
        hf_prefix = "huggingface"
    else:
        raise AttributeError(
            "Neither 'hf_upload_status' nor 'huggingface_upload_status' field exists in dataset table"
        )

    if hasattr(dataset_table, "ms_upload_status"):
        ms_prefix = "ms"
    elif hasattr(dataset_table, "modelscope_upload_status"):
        ms_prefix = "modelscope"
    else:
        raise AttributeError(
            "Neither 'ms_upload_status' nor 'modelscope_upload_status' field exists in dataset table"
        )

    return hf_prefix, ms_prefix


def reset_hub_and_sync_status(db_file: Path) -> int:
    """Reset all hub upload statuses to COMPLETED and dataset_info_sync_status to PENDING.

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

            # Get hub field prefixes
            hf_prefix, ms_prefix = _get_hub_field_prefix(DatasetDB)
            hf_status_field = f"{hf_prefix}_upload_status"
            ms_status_field = f"{ms_prefix}_upload_status"

            # Reset status for all datasets
            updated_count = 0
            completed_count = 0
            pending_count = 0

            for dataset in datasets:
                # Check if dataset has hard_link_path
                hard_link = session.query(DatasetHardLinkDB).filter(
                    DatasetHardLinkDB.dataset_uuid == dataset.dataset_uuid
                ).first()

                # Set hub statuses based on hard_link_path existence
                if hard_link and hard_link.hard_link_path:
                    # Has hard_link_path: set to COMPLETED
                    setattr(dataset, hf_status_field, TaskStatus.COMPLETED)
                    setattr(dataset, ms_status_field, TaskStatus.COMPLETED)
                    completed_count += 1
                else:
                    # No hard_link_path: set to PENDING
                    setattr(dataset, hf_status_field, TaskStatus.PENDING)
                    setattr(dataset, ms_status_field, TaskStatus.PENDING)
                    pending_count += 1

                # Always set dataset_info_sync_status to PENDING
                dataset.dataset_info_sync_status = TaskStatus.PENDING
                updated_count += 1

            # Commit changes
            session.commit()

            logger.info(f"Successfully reset {updated_count} datasets: {completed_count} with hard_link → COMPLETED, {pending_count} without → PENDING")
            print(f"✅ Successfully reset {updated_count} datasets:", file=sys.stderr)
            print(f"   - {completed_count} datasets with hard_link_path:", file=sys.stderr)
            print(f"     • {hf_status_field} → COMPLETED", file=sys.stderr)
            print(f"     • {ms_status_field} → COMPLETED", file=sys.stderr)
            print(f"   - {pending_count} datasets without hard_link_path:", file=sys.stderr)
            print(f"     • {hf_status_field} → PENDING", file=sys.stderr)
            print(f"     • {ms_status_field} → PENDING", file=sys.stderr)
            print("   - All datasets: dataset_info_sync_status → PENDING", file=sys.stderr)

            return 0

    except Exception as e:
        logger.error(f"Failed to reset hub and sync status: {e}", exc_info=True)
        print(f"❌ Failed to reset hub and sync status: {e}", file=sys.stderr)
        return 1


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Reset hub upload statuses to COMPLETED and dataset_info_sync_status to PENDING for all datasets"
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

    logger.info(f"Resetting hub and sync status in: {db_file}")
    print(f"🔄 Resetting hub and sync status in: {db_file}", file=sys.stderr)

    return reset_hub_and_sync_status(db_file)


if __name__ == "__main__":
    sys.exit(main())
