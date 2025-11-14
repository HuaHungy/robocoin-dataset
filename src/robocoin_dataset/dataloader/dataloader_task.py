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
            DatasetDB.qced_repo_gen_status == TaskStatus.COMPLETED,
            or_(
                # Match records explicitly marked as PENDING
                DatasetDB.data_loader_detection_status == TaskStatus.PENDING,
                # Match records that were COMPLETED but are now outdated
                and_(
                    DatasetDB.data_loader_detection_status == TaskStatus.COMPLETED,
                    DatasetDB.data_loader_detection_version_ps < DatasetDB.qced_repo_gen_version,
                ),
            ),
        )
    )

    items = query.all()
    if not items:
        return

    if items:
        _logger.debug(f"Marked {len(items)} dataset(s) as PENDING for dataloader detection")

    for item in items:
        item.data_loader_detection_status = TaskStatus.PENDING
        item.data_loader_detection_version_ps = item.qced_repo_gen_version
        item.data_loader_detection_version = (item.data_loader_detection_version or 0) + 1

    session.commit()


def _gen_one_dataloader_detection_task(session: "Session") -> tuple[str | None, Path | None]:
    """Claim one pending dataset and transition it to PROCESSING, then get hardlink path.

    Returns:
        (dataset_uuid, hardlink_path) or (None, None) if no task available.

    Raises:
        Any exception that occurs during task claiming or hardlink validation.
    """
    from robocoin_dataset.database.models import DatasetDB, DatasetHardLinkDB, TaskStatus

    item = (
        session.query(DatasetDB)
        .filter(DatasetDB.qced_repo_gen_status == TaskStatus.COMPLETED)
        .filter(DatasetDB.data_loader_detection_status == TaskStatus.PENDING)
        .first()
    )
    if not item:
        return None, None

    # Claim the task (transition to PROCESSING) so it won't be picked up by other workers
    item.data_loader_detection_status = TaskStatus.PROCESSING
    session.commit()

    # Get and validate hardlink path
    hardlink_record = session.query(DatasetHardLinkDB).filter(
        DatasetHardLinkDB.dataset_uuid == item.dataset_uuid
    ).first()

    if not hardlink_record or not hardlink_record.hard_link_path:
        raise FileNotFoundError(
            f"No hardlink found in database for dataset {item.dataset_uuid}. "
            f"Hardlinks must be created before running dataloader detection."
        )

    hardlink_path = Path(hardlink_record.hard_link_path)

    # Verify hardlink path exists on disk
    if not hardlink_path.exists():
        raise FileNotFoundError(
            f"Hardlink path in database does not exist on disk: {hardlink_path}"
        )

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

    try:
        item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
        if item:
            item.data_loader_detection_status = TaskStatus.FAILED
            item.data_loader_detection_err_msg = error_message
            session.commit()
    except Exception as e:
        raise RuntimeError(f"Failed to mark task as failed: {e}") from e


__all__ = [
    "_sync_dataloader_detection_tasks",
    "_gen_one_dataloader_detection_task",
    "_mark_task_completed",
    "_mark_task_failed",
]
