"""Prepare hardlink with database integration.

This module provides database-integrated hardlink management:
- Query DB for existing hardlink paths
- Validate existing hardlinks
- Create new hardlinks if needed
- Update DB with hardlink paths
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def prepare_hardlink_db(
    source_path: str | Path,
    dataset_uuid: str,
    target_dir: Path | None = None,
    db_session: "object | None" = None,
) -> Path:
    """Prepare one record's hardlink(by uuid) with database.

    Queries DB for existing hardlink path:
    checks if structure exists (NO-> creates hardlinks, saves to DB).

    Args:
        source_path: Source dataset directory
        dataset_uuid: Dataset UUID for database lookup
        target_dir: Target directory for hardlinks (optional)
        db_session: SQLAlchemy session for database operations (optional)

    Returns:
        Path to the hardlink directory
    """
    from robocoin_dataset.database.models import DatasetHardLinkDB

    src = Path(source_path)

    # Query hardlink path from database
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

    # Validate and create hardlinks (local operation)
    result_path = _prepare_hardlinks(src, dst)

    # Save hardlink path to database
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


def _prepare_hardlinks(src: Path, dst: Path) -> Path:
    """Local function: check if hardlink structure exists or create new hardlinks.
    return the valid hardlink path of one src folder.
    Args:
        src: Source dataset directory
        dst: Target directory for hardlinks

    Returns:
        Path to the hardlink directory
    """
    from robocoin_dataset.hardlink.make_hardlink import (
        RepoHardLinkCorresp,
        create_hardlinks_from_correspondence,
    )
    from robocoin_dataset.hardlink.validate_hardlink import validate_hardlink

    hardlink_corresp = RepoHardLinkCorresp()

    # Check if hardlink structure exists -> Create if needed
    if dst.exists():
        try:
            if validate_hardlink(src, dst, hardlink_corresp):
                logger.info(f"Reusing existing hardlink structure: {dst}")
                return dst
        except Exception:
            pass

    # Create hardlinks
    logger.info(f"Creating hardlinks: {src} → {dst}")
    create_hardlinks_from_correspondence(src, dst, hardlink_corresp)
    logger.info(f"Hardlinks created successfully: {dst}")

    return dst
