"""Prepare hardlink with database integration.

This module provides database operations for hardlink management:
- Query DB for existing hardlink paths
- Update DB with hardlink paths
- Coordinate between database and file system operations

For pure file system operations (validation, creation), see validate_hardlink.py
"""

from pathlib import Path

# Import file system operations from validate_hardlink module
from robocoin_dataset.hardlink.validate_hardlink import (
    create_or_validate_hardlinks,
    validate_source_for_lerobot,
)


def query_existing_hardlink(
    dataset_uuid: str,
    db_session: "object",
) -> Path | None:
    """Query existing hardlink path from database.

    Args:
        dataset_uuid: Dataset UUID for database lookup
        db_session: SQLAlchemy session for database operations

    Returns:
        Existing hardlink path if found, None otherwise
    """
    from robocoin_dataset.database.models import DatasetHardLinkDB

    record = (
        db_session.query(DatasetHardLinkDB)
        .filter(DatasetHardLinkDB.dataset_uuid == dataset_uuid)
        .first()
    )
    if record and record.hard_link_path:
        return Path(record.hard_link_path)
    return None


def update_hardlink_path(
    dataset_uuid: str,
    hardlink_path: Path,
    db_session: "object",
) -> None:
    """Update or create hardlink path in database.

    Args:
        dataset_uuid: Dataset UUID for database lookup
        hardlink_path: Path to hardlink directory
        db_session: SQLAlchemy session for database operations
    """
    from robocoin_dataset.database.models import DatasetHardLinkDB

    record = (
        db_session.query(DatasetHardLinkDB)
        .filter(DatasetHardLinkDB.dataset_uuid == dataset_uuid)
        .first()
    )
    if record:
        record.hard_link_path = str(hardlink_path.absolute())
    else:
        record = DatasetHardLinkDB(
            dataset_uuid=dataset_uuid,
            hard_link_path=str(hardlink_path.absolute()),
        )
        db_session.add(record)
    db_session.commit()


def prepare_hardlink_for_task(
    db: "object",
    dataset_uuid: str,
    convert_path: str | Path,
    hardlink_target_dir: Path | None = None,
) -> Path:
    """Prepare hardlink for a dataset task with optimized database access.

    This function implements the 4-step hardlink preparation workflow:
    1. Validate source files (fast, no DB)
    2. Query existing hardlink path (quick DB query)
    3. Create/validate hardlinks (SLOW - no DB lock)
    4. Update DB with hardlink path (quick DB update)

    Database sessions are kept short to avoid blocking other clients during
    the slow hardlink creation step. This is the recommended API for multi-client
    scenarios.

    Args:
        db: Database instance (must have .with_session() context manager)
        dataset_uuid: Dataset UUID for database lookup
        convert_path: Source dataset directory path
        hardlink_target_dir: Optional target directory for hardlinks

    Returns:
        Path to the hardlink directory

    Raises:
        FileNotFoundError: If source dataset missing required files
        Exception: If hardlink creation/validation fails
    """
    src = Path(convert_path)

    # Step 1: Validate source files (fast, no DB)
    validate_source_for_lerobot(src)

    # Step 2: Query existing hardlink path (quick DB query)
    with db.with_session() as session:
        existing_path = query_existing_hardlink(dataset_uuid, session)

    # Determine target path
    dst = existing_path or hardlink_target_dir or src.parent / f"{src.name}_hardlink"

    # Step 3: Create/validate hardlinks (SLOW - no DB lock)
    test_path = create_or_validate_hardlinks(src, dst)

    # Step 4: Update DB with hardlink path (quick DB update)
    with db.with_session() as session:
        update_hardlink_path(dataset_uuid, test_path, session)

    return test_path


def prepare_hardlink_db(
    source_path: str | Path,
    dataset_uuid: str,
    target_dir: Path | None = None,
    db_session: "object | None" = None,
) -> Path:
    """Prepare one record's hardlink(by uuid) with database (legacy single-session API).

    Complete workflow:
    1. Validate source has required files for LeRobotDataset
    2. Query DB for existing hardlink path
    3. Validate existing hardlink structure OR create new hardlinks
    4. Update DB with hardlink path

    Args:
        source_path: Source dataset directory
        dataset_uuid: Dataset UUID for database lookup
        target_dir: Target directory for hardlinks (optional)
        db_session: SQLAlchemy session for database operations (optional)

    Returns:
        Path to the hardlink directory

    Raises:
        FileNotFoundError: If source dataset missing required LeRobotDataset files

    Note:
        This is the legacy single-session API that holds the database lock during
        slow hardlink creation. For better performance in multi-client scenarios,
        use prepare_hardlink_for_task() instead, which uses multiple short sessions
        to avoid holding database locks during slow operations.
    """
    from robocoin_dataset.database.models import DatasetHardLinkDB

    src = Path(source_path)

    # Step 1: Validate source has required files (fail fast before hardlink creation)
    validate_source_for_lerobot(src)

    # Step 2: Query hardlink path from database
    existing_path = None
    if db_session:
        record = (
            db_session.query(DatasetHardLinkDB)
            .filter(DatasetHardLinkDB.dataset_uuid == dataset_uuid)
            .first()
        )
        if record and record.hard_link_path:
            existing_path = Path(record.hard_link_path)

    # Determine target path
    dst = existing_path or target_dir or src.parent / f"{src.name}_hardlink"

    # Step 3: Validate existing hardlinks or create new ones
    result_path = create_or_validate_hardlinks(src, dst)

    # Step 4: Save hardlink path to database
    if db_session:
        if record:
            record.hard_link_path = str(result_path.absolute())
        else:
            record = DatasetHardLinkDB(
                dataset_uuid=dataset_uuid,
                hard_link_path=str(result_path.absolute()),
            )
            db_session.add(record)
        db_session.commit()

    return result_path
