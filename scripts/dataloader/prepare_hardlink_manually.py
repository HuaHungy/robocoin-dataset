"""Manually prepare hardlinks for all datasets with completed data merge status.

This script:
1. Queries all datasets where data_merge_status is COMPLETED
2. Checks if each dataset has a hardlink in the dataset_hard_link table
3. Creates hardlinks for datasets that don't have one (using convert_path's ending + "_hardlink" as name)
4. Updates the database with the hardlink path

Safety features:
- Only creates hardlinks within the specified dst-path directory
- Prevents hardlinking from within dst-path (no recursive hardlinks)
- Validates all paths to ensure operations stay within dst-path

Usage:
    python prepare_hardlink_manually.py --dst-path /path/to/hardlinks --db /path/to/database.db
"""

import argparse
import logging
from pathlib import Path

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB, DatasetHardLinkDB, TaskStatus
from robocoin_dataset.hardlink.prepare_hardlink import prepare_hardlink_for_task

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_completed_datasets(db: DatasetDatabase) -> list[tuple[str, str]]:
    """Query all datasets with COMPLETED data_merge_status.

    Args:
        db: Database instance

    Returns:
        List of tuples (dataset_uuid, convert_path)
    """
    with db.with_session() as session:
        datasets = (
            session.query(DatasetDB.dataset_uuid, DatasetDB.convert_path)
            .filter(DatasetDB.data_merge_status == TaskStatus.COMPLETED)
            .filter(DatasetDB.convert_path.isnot(None))
            .all()
        )
        return [(uuid, path) for uuid, path in datasets]


def check_hardlink_exists(db: DatasetDatabase, dataset_uuid: str) -> bool:
    """Check if dataset has a hardlink in dataset_hard_link table.

    Args:
        db: Database instance
        dataset_uuid: UUID of the dataset

    Returns:
        True if hardlink exists, False otherwise
    """
    with db.with_session() as session:
        record = (
            session.query(DatasetHardLinkDB)
            .filter(DatasetHardLinkDB.dataset_uuid == dataset_uuid)
            .first()
        )
        return record is not None and record.hard_link_path is not None


def manual_prepare_hardlink(dst_path: str | Path, db_path: str | Path) -> None:
    """Prepare hardlinks for all datasets with completed data merge status.

    This function:
    1. Queries all datasets where data_merge_status is COMPLETED
    2. Saves their dataset_uuid and convert_path
    3. Loops through the list:
       a. Gets one uuid and convert_path
       b. Checks if hardlink exists in dataset_hard_link table
       c. If yes, skips; if no, creates hardlink and updates database
       d. Removes uuid from list
    4. Continues until list is empty

    Args:
        dst_path: Directory where all hardlinks will be stored
        db_path: Path to the database file

    Returns:
        None
    """
    dst_path = Path(dst_path).expanduser().absolute()
    db_path = Path(db_path).expanduser().absolute()

    # Validate inputs
    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")

    dst_path.mkdir(parents=True, exist_ok=True)

    # Safety check: ensure dst_path is a directory
    if not dst_path.is_dir():
        raise ValueError(f"dst_path must be a directory: {dst_path}")

    # Initialize database
    db = DatasetDatabase(db_path)
    logger.info(f"Connected to database: {db_path}")

    # Step 1 & 2: Query all datasets with COMPLETED data_merge_status
    datasets = get_completed_datasets(db)
    logger.info(f"Found {len(datasets)} datasets with COMPLETED data_merge_status")

    if not datasets:
        logger.info("No datasets to process. Exiting.")
        return

    # Step 3: Loop through list
    total = len(datasets)
    processed = 0
    skipped = 0
    created = 0
    failed = 0

    for idx, (dataset_uuid, convert_path) in enumerate(datasets, 1):
        logger.info(f"\n[{idx}/{total}] Processing dataset: {dataset_uuid}")

        try:
            # (2) Check if hardlink exists in dataset_hard_link table
            if check_hardlink_exists(db, dataset_uuid):
                logger.info(f"  ✓ Hardlink already exists for {dataset_uuid}, skipping")
                skipped += 1
                continue

            # (3) Create hardlink if it doesn't exist
            logger.info(f"  Creating hardlink for {dataset_uuid}")
            convert_path_obj = Path(convert_path).absolute()

            if not convert_path_obj.exists():
                logger.error(f"  ✗ Convert path does not exist: {convert_path}")
                failed += 1
                continue

            # Safety check: Ensure convert_path is not inside dst_path
            # (to avoid hardlinking a hardlink)
            try:
                convert_path_obj.relative_to(dst_path)
                logger.error(
                    f"  ✗ Convert path is inside dst_path. "
                    f"Cannot hardlink from within destination: {convert_path}"
                )
                failed += 1
                continue
            except ValueError:
                # This is expected - convert_path should NOT be relative to dst_path
                pass

            # Determine target directory for this dataset
            # Use convert_path's ending + "_hardlink" as the name
            dataset_name = convert_path_obj.name
            dataset_hardlink_dir = dst_path / f"{dataset_name}_hardlink"

            # Safety check: Ensure hardlink path is within dst_path
            try:
                dataset_hardlink_dir.absolute().relative_to(dst_path)
            except ValueError:
                logger.error(
                    f"  ✗ Computed hardlink path is outside dst_path: {dataset_hardlink_dir}"
                )
                failed += 1
                continue

            # Use prepare_hardlink_for_task to create hardlink and update database
            hardlink_path = prepare_hardlink_for_task(
                db=db,
                dataset_uuid=dataset_uuid,
                convert_path=convert_path,
                hardlink_target_dir=dataset_hardlink_dir,
            )

            logger.info(f"  ✓ Hardlink created successfully at: {hardlink_path}")
            created += 1

        except Exception as e:
            logger.error(f"  ✗ Failed to process {dataset_uuid}: {e}", exc_info=True)
            failed += 1

        processed += 1

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total datasets found:    {total}")
    logger.info(f"Processed:               {processed}")
    logger.info(f"Hardlinks created:       {created}")
    logger.info(f"Skipped (already exist): {skipped}")
    logger.info(f"Failed:                  {failed}")
    logger.info("=" * 80)


def main() -> int:
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Prepare hardlinks for all datasets with completed data merge status"
    )
    parser.add_argument(
        "--dst-path",
        type=str,
        required=True,
        help="Directory where all hardlinks will be stored",
    )
    parser.add_argument(
        "--db",
        type=str,
        required=True,
        help="Path to the database file",
    )

    args = parser.parse_args()

    try:
        manual_prepare_hardlink(dst_path=args.dst_path, db_path=args.db)
    except Exception as e:
        logger.error(f"Script failed: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
