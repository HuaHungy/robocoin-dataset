"""Process existing hardlink paths and populate dataset_hard_link table.

This script:
1. Reads existing hardlink paths from a file (one per line)
2. Extracts dataset names by removing "_hardlink" suffix
3. Queries database to find dataset_uuid where convert_path ends with dataset_name
4. Inserts/updates dataset_hard_link table with dataset_uuid - hardlink_path mappings
5. Only writes valid hardlinks (paths that exist) to the database

Usage:
    # Normal mode: Add/update hardlinks from file
    python use_existing_hardlink.py --db /path/to/database.db [--hardlink-file /path/to/hardlinks.txt]

    # Cleanup mode: Delete invalid hardlink records from database
    python use_existing_hardlink.py --db /path/to/database.db --cleanup
"""

import argparse
import logging
from pathlib import Path

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB, DatasetHardLinkDB

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def read_hardlink_paths(file_path: Path) -> list[str]:
    """Read hardlink paths from file.

    Args:
        file_path: Path to file containing hardlink paths (one per line)

    Returns:
        List of hardlink paths
    """
    with open(file_path) as f:
        return [
            line.strip()
            for line in f
            if line.strip() and line.strip().startswith('/')  # Only lines that are absolute paths
        ]


def extract_dataset_names(hardlink_paths: list[str]) -> list[str]:
    """Extract dataset names by removing _hardlink suffix.

    Args:
        hardlink_paths: List of hardlink absolute paths

    Returns:
        List of dataset names (without _hardlink suffix)
    """
    dataset_names = []
    for path in hardlink_paths:
        path_obj = Path(path)
        name = path_obj.name

        # Remove _hardlink suffix
        if name.endswith("_hardlink"):
            dataset_name = name[:-len("_hardlink")]
            dataset_names.append(dataset_name)
        else:
            logger.warning(f"Path does not end with _hardlink suffix: {path}")
            dataset_names.append(name)

    return dataset_names


def query_dataset_uuids(
    db: DatasetDatabase,
    dataset_names: list[str]
) -> dict[str, str]:
    """Query database to find dataset_uuid for each dataset_name.

    Args:
        db: Database instance
        dataset_names: List of dataset names to query

    Returns:
        Dictionary mapping dataset_uuid to dataset_name_hardlink
    """
    uuid_to_hardlink_name = {}

    with db.with_session() as session:
        for dataset_name in dataset_names:
            # Query datasets where convert_path ends with dataset_name
            datasets = (
                session.query(DatasetDB.dataset_uuid, DatasetDB.convert_path)
                .filter(DatasetDB.convert_path.isnot(None))
                .all()
            )

            # Filter by checking if convert_path ends with dataset_name
            for uuid, convert_path in datasets:
                if convert_path and Path(convert_path).name == dataset_name:
                    hardlink_name = f"{dataset_name}_hardlink"
                    uuid_to_hardlink_name[uuid] = hardlink_name
                    logger.info(f"Found match: {uuid} -> {dataset_name}")
                    break
            else:
                logger.warning(f"No dataset found with convert_path ending in: {dataset_name}")

    return uuid_to_hardlink_name


def delete_invalid_hardlinks(db: DatasetDatabase) -> int:
    """Delete records from dataset_hard_link table where paths don't exist.

    Args:
        db: Database instance

    Returns:
        Number of records deleted
    """
    deleted = 0

    with db.with_session() as session:
        # Query all hardlink records
        records = session.query(DatasetHardLinkDB).all()

        logger.info(f"Checking {len(records)} hardlink records for validity...")

        for record in records:
            hardlink_path = record.hard_link_path

            # Check if path exists
            if not Path(hardlink_path).exists():
                logger.warning(
                    f"Deleting invalid hardlink record:\n"
                    f"  UUID: {record.dataset_uuid}\n"
                    f"  Path: {hardlink_path}"
                )
                session.delete(record)
                deleted += 1

        if deleted > 0:
            session.commit()
            logger.info(f"Deleted {deleted} invalid hardlink records")
        else:
            logger.info("No invalid hardlink records found")

    return deleted


def upsert_hardlink_records(
    db: DatasetDatabase,
    uuid_to_hardlink_name: dict[str, str],
    hardlink_paths: list[str]
) -> tuple[int, int, int, int]:
    """Insert or update dataset_hard_link table records.

    Args:
        db: Database instance
        uuid_to_hardlink_name: Dictionary mapping dataset_uuid to hardlink_name
        hardlink_paths: List of hardlink absolute paths

    Returns:
        Tuple of (inserted_count, updated_count, skipped_count, failed_count)
    """
    # Create mapping from hardlink_name to full path
    name_to_path = {}
    for path in hardlink_paths:
        path_obj = Path(path)
        name = path_obj.name
        name_to_path[name] = path

    inserted = 0
    updated = 0
    skipped = 0
    failed = 0

    with db.with_session() as session:
        for dataset_uuid, hardlink_name in uuid_to_hardlink_name.items():
            try:
                # Get the full hardlink path
                hardlink_path = name_to_path.get(hardlink_name)

                if not hardlink_path:
                    logger.error(f"No hardlink path found for: {hardlink_name}")
                    failed += 1
                    continue

                # Check if path exists - skip if not valid
                if not Path(hardlink_path).exists():
                    logger.warning(f"Hardlink path does not exist, skipping: {hardlink_path}")
                    skipped += 1
                    continue

                # Query existing record
                record = (
                    session.query(DatasetHardLinkDB)
                    .filter(DatasetHardLinkDB.dataset_uuid == dataset_uuid)
                    .first()
                )

                if record:
                    # Update existing record
                    old_path = record.hard_link_path
                    record.hard_link_path = hardlink_path
                    logger.info(
                        f"Updated: {dataset_uuid}\n"
                        f"  Old: {old_path}\n"
                        f"  New: {hardlink_path}"
                    )
                    updated += 1
                else:
                    # Insert new record
                    record = DatasetHardLinkDB(
                        dataset_uuid=dataset_uuid,
                        hard_link_path=hardlink_path,
                    )
                    session.add(record)
                    logger.info(f"Inserted: {dataset_uuid} -> {hardlink_path}")
                    inserted += 1

                session.commit()

            except Exception as e:
                session.rollback()
                logger.error(f"Failed to process {dataset_uuid}: {e}", exc_info=True)
                failed += 1

    return inserted, updated, skipped, failed


def process_existing_hardlinks(
    db_path: str | Path,
    hardlink_file: str | Path | None = None
) -> None:
    """Main processing function.

    Args:
        db_path: Path to the database file
        hardlink_file: Path to file containing hardlink paths (default: this script file)
    """
    db_path = Path(db_path).expanduser().absolute()

    # If no hardlink file specified, use this script file
    if hardlink_file is None:
        hardlink_file = Path(__file__).absolute()
    else:
        hardlink_file = Path(hardlink_file).expanduser().absolute()

    # Validate inputs
    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")

    if not hardlink_file.exists():
        raise FileNotFoundError(f"Hardlink file not found: {hardlink_file}")

    logger.info(f"Reading hardlink paths from: {hardlink_file}")
    logger.info(f"Database: {db_path}")

    # Initialize database
    db = DatasetDatabase(db_path)

    # Step 1: Read hardlink paths
    hardlink_paths = read_hardlink_paths(hardlink_file)
    logger.info(f"Found {len(hardlink_paths)} hardlink paths")

    if not hardlink_paths:
        logger.warning("No hardlink paths found in file")
        return

    # Step 2: Extract dataset names (remove _hardlink suffix)
    dataset_names = extract_dataset_names(hardlink_paths)
    logger.info(f"Extracted {len(dataset_names)} dataset names")

    # Step 3: Query database for dataset_uuid matching dataset_names
    uuid_to_hardlink_name = query_dataset_uuids(db, dataset_names)
    logger.info(f"Found {len(uuid_to_hardlink_name)} matching datasets in database")

    if not uuid_to_hardlink_name:
        logger.warning("No matching datasets found in database")
        return

    # Step 4: Insert/update dataset_hard_link table
    inserted, updated, skipped, failed = upsert_hardlink_records(
        db, uuid_to_hardlink_name, hardlink_paths
    )

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total hardlink paths:     {len(hardlink_paths)}")
    logger.info(f"Dataset names extracted:  {len(dataset_names)}")
    logger.info(f"Datasets matched:         {len(uuid_to_hardlink_name)}")
    logger.info(f"Records inserted:         {inserted}")
    logger.info(f"Records updated:          {updated}")
    logger.info(f"Skipped (invalid path):   {skipped}")
    logger.info(f"Failed:                   {failed}")
    logger.info("=" * 80)


def main() -> int:
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Process existing hardlink paths and populate database"
    )
    parser.add_argument(
        "--db",
        type=str,
        required=True,
        help="Path to the database file",
    )
    parser.add_argument(
        "--hardlink-file",
        type=str,
        default=None,
        help="Path to file containing hardlink paths (default: this script file)",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete invalid hardlink records from database (where paths don't exist)",
    )

    args = parser.parse_args()

    try:
        # If cleanup mode, delete invalid records
        if args.cleanup:
            db_path = Path(args.db).expanduser().absolute()
            if not db_path.exists():
                raise FileNotFoundError(f"Database file not found: {db_path}")

            logger.info(f"Running cleanup mode on database: {db_path}")
            db = DatasetDatabase(db_path)
            deleted = delete_invalid_hardlinks(db)

            logger.info("\n" + "=" * 80)
            logger.info("CLEANUP SUMMARY")
            logger.info("=" * 80)
            logger.info(f"Records deleted: {deleted}")
            logger.info("=" * 80)
        else:
            # Normal mode: process hardlinks
            process_existing_hardlinks(
                db_path=args.db,
                hardlink_file=args.hardlink_file
            )
    except Exception as e:
        logger.error(f"Script failed: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    exit(main())


# Below are the existing hardlink paths (one per line)
# These will be read by the script when --hardlink-file is not specified
"""
/mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_basket_storage_peach_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/unitree_g1_basket_storage_apple_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/unitree_g1_receive_drink_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/unitree_g1_basket_storage_peach_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/unitree_g1_stack_bowls_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/unitree_g1_plate_storage_rabbit_doll_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/unitree_g1_bowl_storage_bread_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/unitree_g1_navigation_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/unitree_g1_food_storage_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/galaxea_r1_lite_stack_baskets_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/galaxea_r1_lite_peach_storage_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/galaxea_r1_lite_build_blocks_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/galaxea_r1_lite_move_the_position_of_the_coffee_capsule_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/galaxea_r1_lite_move_the_position_of_the_black_marker_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/galaxea_r1_lite_move_the_position_of_the_soda_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/galaxea_r1_lite_move_the_position_of_the_triangle_bread_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/galaxea_r1_lite_move_the_position_of_the_spoon_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/galaxea_r1_lite_move_the_position_of_the_rubiks_cube_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/galaxea_r1_lite_move_the_position_of_the_milk_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/galaxea_r1_lite_move_the_position_of_the_peeler_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/galaxea_r1_lite_move_the_position_of_the_brush_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/galaxea_r1_lite_move_the_position_of_the_long_bread_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/galaxea_r1_lite_move_the_position_of_the_orange_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/galaxea_r1_lite_move_the_position_of_the_apple_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/galaxea_r1_lite_move_the_position_of_the_glass_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/galaxea_r1_lite_move_the_position_of_the_duck_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/galaxea_r1_lite_move_the_position_of_the_pen_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_fruit_storage_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/galaxea_r1_lite_move_the_position_of_the_cookie_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_place_the_fruits_repeatedly_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_pour_coffee_beans_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_food_storage_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_stack_baskets_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_basket_storage_long_bread_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_basket_storage_egg_yolk_pastry_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_basket_storage_orange_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_get_water_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_place_test_tube_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_clean_table_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_food_packaging_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_organise_the_document_bag_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_fold_shorts_hardlink
/mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_plate_storage_hardlink
"""
