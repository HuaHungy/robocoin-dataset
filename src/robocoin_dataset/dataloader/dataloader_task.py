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
      - qced_repo_gen_status must be COMPLETED
      - data_loader_detection_status is NULL (never tested), PENDING, or COMPLETED but outdated

    WARNING: NULL data_loader_detection_status is ILLEGAL but handled for robustness.
    """
    from sqlalchemy.sql.expression import and_, or_

    from robocoin_dataset.database.models import DatasetDB, TaskStatus

    _logger = logger or logging.getLogger(__name__)
    _logger.debug("🔄 Syncing dataloader detection tasks...")

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
        _logger.debug("✅ No datasets need status update (all in sync)")
        return

    _logger.info(f"📝 Marking {len(items)} dataset(s) as PENDING for dataloader detection")
    for item in items:
        _logger.debug(f"  - {item.dataset_uuid}: {item.data_loader_detection_status} → PENDING")
        item.data_loader_detection_status = TaskStatus.PENDING
        item.data_loader_detection_version_ps = item.qced_repo_gen_version
        item.data_loader_detection_version = (item.data_loader_detection_version or 0) + 1

    session.commit()
    _logger.debug(f"✅ Sync complete: {len(items)} dataset(s) updated")


def _gen_one_dataloader_detection_task(
    session: "Session",
    logger: logging.Logger | None = None,
) -> tuple[str | None, Path | None]:
    """Claim one pending dataset and transition it to PROCESSING.

    This function validates that the hardlink path exists before claiming the task.
    If hardlink doesn't exist, raises FileNotFoundError.

    Returns:
        (dataset_uuid, hardlink_path) or (None, None) if no task available.

    Raises:
        FileNotFoundError: If hardlink path not found in database or doesn't exist on disk.
    """
    from robocoin_dataset.database.models import DatasetDB, TaskStatus

    _logger = logger or logging.getLogger(__name__)
    _logger.debug("🔍 Querying for pending dataloader detection tasks...")

    item = (
        session.query(DatasetDB)
        .filter(DatasetDB.qced_repo_gen_status == TaskStatus.COMPLETED)
        .filter(DatasetDB.data_loader_detection_status == TaskStatus.PENDING)
        .first()
    )
    if not item:
        _logger.debug("📭 No pending tasks found in database")
        return None, None

    # Query hardlink path before claiming task and validate
    from robocoin_dataset.database.models import DatasetHardLinkDB

    dataset_uuid = item.dataset_uuid
    _logger.debug(f"📦 Found pending dataset: {dataset_uuid}")

    try:
        _logger.debug(f"🔗 Validating hardlink for {dataset_uuid}...")
        hardlink_record = session.query(DatasetHardLinkDB).filter(
            DatasetHardLinkDB.dataset_uuid == dataset_uuid
        ).first()
        hardlink_path = Path(hardlink_record.hard_link_path) if hardlink_record and hardlink_record.hard_link_path else None

        if hardlink_path is None:
            _logger.error(f"❌ No hardlink record found in database for {dataset_uuid}")
            error = FileNotFoundError(
                f"No hardlink found in database for dataset {dataset_uuid}. "
                f"Hardlinks must be created before running dataloader detection."
            )
            error.dataset_uuid = dataset_uuid
            raise error

        _logger.debug(f"🔗 Hardlink path from DB: {hardlink_path}")

        # Verify hardlink path exists on disk
        if not hardlink_path.exists():
            _logger.error(f"❌ Hardlink path does not exist on disk: {hardlink_path}")
            error = FileNotFoundError(
                f"Hardlink path in database does not exist on disk: {hardlink_path}"
            )
            error.dataset_uuid = dataset_uuid
            raise error

        _logger.debug(f"✅ Hardlink validation passed: {hardlink_path}")
    except FileNotFoundError:
        # Re-raise FileNotFoundError as-is (now with dataset_uuid attribute)
        raise
    except Exception as e:
        # Wrap other exceptions as FileNotFoundError
        _logger.error(f"❌ Exception during hardlink validation for {dataset_uuid}: {e}")
        error = FileNotFoundError(
            f"Failed to retrieve or validate hardlink for dataset {dataset_uuid}: {e}"
        )
        error.dataset_uuid = dataset_uuid
        raise error from e

    # All validations passed - claim the task
    _logger.debug(f"🎯 Claiming task: {dataset_uuid} (PENDING → PROCESSING)")
    item.data_loader_detection_status = TaskStatus.PROCESSING
    session.commit()
    _logger.info(f"✅ Task claimed: {dataset_uuid} at {hardlink_path}")
    return dataset_uuid, hardlink_path


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
