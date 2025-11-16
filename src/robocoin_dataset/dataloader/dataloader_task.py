import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _sync_dataloader_detection_tasks(
    session: "Session",
    logger: logging.Logger | None = None,
) -> None:
    """Mark PENDING for:

    Trigger rules (STRICT REQUIREMENTS):
      - qced_repo_gen_status must be COMPLETED
      - data_loader_detection_status is PENDING, or COMPLETED but outdated
    """
    from sqlalchemy.sql.expression import and_, or_

    from robocoin_dataset.database.models import DatasetDB, TaskStatus

    _logger = logger or logging.getLogger(__name__)

    query = session.query(DatasetDB).filter(
        and_(
            DatasetDB.qced_repo_gen_status == TaskStatus.COMPLETED,
            or_(
                DatasetDB.data_loader_detection_status == TaskStatus.PENDING,
                and_(
                    DatasetDB.data_loader_detection_status == TaskStatus.COMPLETED,
                    DatasetDB.data_loader_detection_version_ps < DatasetDB.qced_repo_gen_version,
                ),
            ),
        ),
    )

    items = query.all()
    if not items:
        _logger.debug("No datasets found for dataloader detection")
        return

    if items:
        _logger.debug(f"Marked {len(items)} dataset(s) as PENDING for dataloader detection")

    for item in items:
        item.data_loader_detection_status = TaskStatus.PENDING
        item.data_loader_detection_version_ps = item.qced_repo_gen_version
        item.data_loader_detection_version = (item.data_loader_detection_version or 0) + 1

    session.commit()


def _gen_one_dataloader_detection_task(session: "Session") -> tuple[str | None, Path | None]:
    """
    Claim one pending dataset and transition it to PROCESSING,
    check if the hardlink path exists in db and disk.
    if True, return the dataset_uuid and hardlink_path, else None.

    Returns:
        (dataset_uuid, hardlink_path) or (None, None) if no task available.
        (dataset_uuid, None) == err: no valid hardlink path in db.

    Raises:
        NO raise since raise kills uuid and cannot update task status.
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

    # Claim the task (transition to PROCESSING) avoiding picking up by other workers
    item.data_loader_detection_status = TaskStatus.PROCESSING
    session.commit()

    # Get hardlink path from db
    hardlink_record = session.query(DatasetHardLinkDB).filter(
        DatasetHardLinkDB.dataset_uuid == item.dataset_uuid
    ).first()

    # Verify hardlink path exists on db
    if not hardlink_record or not hardlink_record.hard_link_path:
        return item.dataset_uuid, None

    hardlink_path = Path(hardlink_record.hard_link_path)

    return item.dataset_uuid, hardlink_path


def _mark_task_completed(session: "Session", dataset_uuid: str) -> None:
    """
    Mark a dataloader detection task as completed in session
    identify by uuid.
    """
    from robocoin_dataset.database.models import DatasetDB, TaskStatus

    item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
    if item:
        item.data_loader_detection_status = TaskStatus.COMPLETED
        item.data_loader_detection_err_msg = None
        session.commit()


def _mark_task_failed(session: "Session", dataset_uuid: str, error_message: str) -> None:
    """
    Mark a dataloader detection task as failed in session
    identify by uuid, and set error message.
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
