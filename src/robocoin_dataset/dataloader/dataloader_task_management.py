import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _sync_dataloader_detection_tasks(
    session: "Session",
    logger: logging.Logger | None = None,
) -> None:
    """Mark datasets requiring dataloader detection as pending and align versions.

    Trigger rules (STRICT REQUIREMENTS):
      - data_merge_status must be COMPLETED
      - convert_status must be COMPLETED
      - data_loader_detection_status is NULL (never tested), PENDING, or COMPLETED but outdated

    WARNING: NULL data_loader_detection_status is ILLEGAL but handled for robustness.
    """
    from sqlalchemy.sql.expression import and_, or_

    from robocoin_dataset.database.models import DatasetDB, TaskStatus

    _logger = logger or logging.getLogger(__name__)

    query = session.query(DatasetDB).filter(
        and_(
            DatasetDB.data_merge_status == TaskStatus.COMPLETED,
            or_(
                # NEW: Match records that have never been tested (NULL status)
                DatasetDB.data_loader_detection_status == None,  # noqa: E711
                # Match records explicitly marked as PENDING
                DatasetDB.data_loader_detection_status == TaskStatus.PENDING,
                # Match records that were COMPLETED but are now outdated
                and_(
                    DatasetDB.data_loader_detection_status == TaskStatus.COMPLETED,
                    DatasetDB.data_loader_detection_version_ps < DatasetDB.data_merge_version,
                ),
            ),
        )
    )

    items = query.all()
    if not items:
        return

    # Separate NULL status records and warn about them
    null_status_items = []
    valid_items = []

    for item in items:
        if item.data_loader_detection_status is None:
            null_status_items.append(item)
        else:
            valid_items.append(item)

        item.data_loader_detection_status = TaskStatus.PENDING
        item.data_loader_detection_version_ps = item.data_merge_version
        item.data_loader_detection_version = (item.data_loader_detection_version or 0) + 1

    # Log warnings for NULL status records
    if null_status_items:
        _logger.warning(
            f"⚠️  Found {len(null_status_items)} dataset(s) with NULL data_loader_detection_status. "
            f"This is ILLEGAL - status should be initialized. Treating as PENDING for robustness."
        )
        for item in null_status_items:
            _logger.warning(
                f"   ⚠️  Dataset {item.dataset_uuid} has NULL data_loader_detection_status "
                f"(convert_path: {item.convert_path})"
            )

    if valid_items:
        _logger.info(f"Marked {len(valid_items)} dataset(s) as PENDING for dataloader detection")

    session.commit()


def _gen_one_dataloader_detection_task(session: "Session") -> tuple[str | None, Path | None]:
    """Claim one pending dataset and transition it to PROCESSING.

    This function validates that the hardlink path exists before claiming the task.
    If hardlink doesn't exist, raises FileNotFoundError.

    Returns:
        (dataset_uuid, hardlink_path) or (None, None) if no task available.

    Raises:
        FileNotFoundError: If hardlink path not found in database or doesn't exist on disk.
    """
    from robocoin_dataset.database.models import DatasetDB, TaskStatus
    from robocoin_dataset.hardlink.prepare_hardlink import query_existing_hardlink

    item = (
        session.query(DatasetDB)
        .filter(DatasetDB.data_merge_status == TaskStatus.COMPLETED)
        .filter(DatasetDB.data_loader_detection_status == TaskStatus.PENDING)
        .first()
    )
    if not item:
        return None, None

    # Query and validate hardlink path before claiming task
    hardlink_path = query_existing_hardlink(item.dataset_uuid, session)

    if hardlink_path is None:
        raise FileNotFoundError(
            f"No hardlink found in database for dataset {item.dataset_uuid}. "
            f"Hardlinks must be created before running dataloader detection."
        )

    # Verify hardlink path exists on disk
    if not hardlink_path.exists():
        raise FileNotFoundError(
            f"Hardlink path in database does not exist on disk: {hardlink_path}"
        )

    # All validations passed - claim the task
    item.data_loader_detection_status = TaskStatus.PROCESSING
    session.commit()
    return item.dataset_uuid, hardlink_path


def _mark_task_completed(session: "Session", dataset_uuid: str) -> None:
    """Mark a dataloader detection task as completed.

    Args:
        session: Database session
        dataset_uuid: UUID of the dataset to mark as completed
    """
    from robocoin_dataset.database.models import DatasetDB, TaskStatus

    item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
    if item:
        item.data_loader_detection_status = TaskStatus.COMPLETED
        item.data_loader_detection_err_msg = None
        session.commit()


def _mark_task_failed(session: "Session", dataset_uuid: str, error_message: str) -> None:
    """Mark a dataloader detection task as failed with error message.

    Args:
        session: Database session
        dataset_uuid: UUID of the dataset to mark as failed
        error_message: Error message describing the failure
    """
    from robocoin_dataset.database.models import DatasetDB, TaskStatus

    item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
    if item:
        item.data_loader_detection_status = TaskStatus.FAILED
        item.data_loader_detection_err_msg = error_message
        session.commit()


__all__ = [
    "_sync_dataloader_detection_tasks",
    "_gen_one_dataloader_detection_task",
    "_mark_task_completed",
    "_mark_task_failed",
]
