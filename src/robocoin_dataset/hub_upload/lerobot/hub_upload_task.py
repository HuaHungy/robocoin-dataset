"""Task management functions for hub upload operations."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:

    from robocoin_dataset.database.database import DatasetDatabase
    from robocoin_dataset.database.models import DatasetDB
    from robocoin_dataset.hub_upload.constant import DatasetsHubEnum


def _get_hub_field_prefix(hub_name_enum: "DatasetsHubEnum", dataset_table: "type[DatasetDB]", field_suffix: str) -> str:
    """
    Return the correct field prefix for the hub,
    trying short version first, then long version.

    Args:
        hub_name_enum: The hub name enum (DatasetsHubEnum.modelscope or DatasetsHubEnum.huggingface)
        dataset_table: The DatasetDB table class
        field_suffix: The field suffix (e.g., "upload_status", "upload_version")

    Returns:
        The field name with correct prefix

    Raises:
        AttributeError: If neither short nor long field name exists
    """
    from ..constant import DatasetsHubEnum

    # Try short prefix first (ms/hf)
    short_prefix = "ms" if hub_name_enum == DatasetsHubEnum.modelscope else "hf"
    short_field_name = f"{short_prefix}_{field_suffix}"
    if hasattr(dataset_table, short_field_name):
        return short_field_name

    # Fall back to long prefix (modelscope/huggingface)
    long_prefix = "modelscope" if hub_name_enum == DatasetsHubEnum.modelscope else "huggingface"
    long_field_name = f"{long_prefix}_{field_suffix}"
    if hasattr(dataset_table, long_field_name):
        return long_field_name

    # Neither exists, raise error
    raise AttributeError(
        f"Neither '{short_field_name}' nor '{long_field_name}' field exists in DatasetDB"
    )


def _sync_datasets_upload_status(
    db: "DatasetDatabase",
    hub_name_enum: "DatasetsHubEnum",
    logger: logging.Logger | None = None,
    retry_failed: bool = False
) -> None:
    """
    Sync datasets upload status from database.
    Set PENDING and increment the version,
    sync the version_ps -> visualize_check_status.

    Args:
        db: Database instance.
        hub_name_enum: The hub name enum (DatasetsHubEnum.modelscope or DatasetsHubEnum.huggingface)
        logger: Logger instance
        retry_failed: If True, retry failed uploads. Otherwise only process pending ones.
    """
    from sqlalchemy.sql.expression import and_, or_

    from robocoin_dataset.database.models import DatasetDB, TaskStatus

    _logger = logger or logging.getLogger(__name__)

    # Get correct field names (tries ms/hf first, then modelscope/huggingface)
    upload_status_field = _get_hub_field_prefix(hub_name_enum, DatasetDB, "upload_status")
    upload_version_ps_field = _get_hub_field_prefix(hub_name_enum, DatasetDB, "upload_version_ps")

    # Get column objects for dynamic field names
    upload_status_col = getattr(DatasetDB, upload_status_field)
    upload_version_ps_col = getattr(DatasetDB, upload_version_ps_field)

    with db.with_session() as session:

        query = session.query(DatasetDB).filter(
            and_(
                DatasetDB.visualize_check_status == TaskStatus.COMPLETED,
                or_(
                    upload_status_col == TaskStatus.PENDING,
                    and_(
                        upload_status_col == TaskStatus.COMPLETED,
                        upload_version_ps_col < DatasetDB.visualize_check_version,
                    ),
                ),
            )
        )

        items = query.all()
        if not items:
            _logger.debug("No datasets found for upload sync")
            return

        _logger.debug(f"Found {len(items)} datasets to sync for upload")

        for item in items:
            setattr(item, upload_status_field, TaskStatus.PENDING)
        session.commit()


def _gen_one_dataset_upload_task(
    db: "DatasetDatabase",
    hub_name_enum: "DatasetsHubEnum",
    logger: logging.Logger | None = None,
    skip_missing: bool = False
) -> tuple[str | None, Path | None]:
    """
    Generate one dataset upload task by finding a pending upload, marking it as PROCESSING,
    and validating the hardlink path.

    Args:
        db: Database instance
        hub_name_enum: The hub name enum (DatasetsHubEnum.modelscope or DatasetsHubEnum.huggingface)
        logger: Logger instance
        skip_missing: If True, skip missing hardlinks instead of raising error

    Returns:
        Tuple of (dataset_uuid, hardlink_path) if valid task found, (None, None) otherwise.
        hardlink_path is a validated Path object.

    Raises:
        FileNotFoundError: If hardlink is missing and skip_missing is False
    """
    from sqlalchemy.sql.expression import and_

    from robocoin_dataset.database.models import DatasetDB, DatasetHardLinkDB, TaskStatus

    _logger = logger or logging.getLogger(__name__)

    # Get correct field names (tries ms/hf first, then modelscope/huggingface)
    upload_status_field = _get_hub_field_prefix(hub_name_enum, DatasetDB, "upload_status")

    # Get column objects for dynamic field names
    upload_status_col = getattr(DatasetDB, upload_status_field)
    upload_version_field = _get_hub_field_prefix(hub_name_enum, DatasetDB, "upload_version")
    upload_version_ps_field = _get_hub_field_prefix(hub_name_enum, DatasetDB, "upload_version_ps")

    with db.with_session() as session:
        query = session.query(DatasetDB).filter(
            and_(
                DatasetDB.visualize_check_status == TaskStatus.COMPLETED,
                upload_status_col == TaskStatus.PENDING,
            )
        )
        item = query.first()
        if not item:
            return None, None

        dataset_uuid = item.dataset_uuid

        setattr(item, upload_status_field, TaskStatus.PROCESSING)
        current_version = getattr(item, upload_version_field, 0) or 0
        setattr(item, upload_version_field, current_version + 1)
        setattr(item, upload_version_ps_field, item.visualize_check_version)
        session.commit()

        # Query hardlink_path from dataset_hard_link table
        hardlink_item = session.query(DatasetHardLinkDB).filter(
            DatasetHardLinkDB.dataset_uuid == dataset_uuid
        ).first()

        hardlink_path_str = hardlink_item.hard_link_path if hardlink_item else None

    # Validate hardlink path exists in database
    if hardlink_path_str is None:
        error_msg = f"No hardlink found in database for dataset {dataset_uuid}"
        _logger.error(f"❌ {error_msg}")
        _mark_upload_failed(db, dataset_uuid, error_msg, hub_name_enum, logger)
        if not skip_missing:
            raise FileNotFoundError(f"{error_msg}. Hardlinks must be created before uploading.")
        return None, None

    hardlink_path = Path(hardlink_path_str)

    # Validate hardlink path exists on disk
    if not hardlink_path.exists():
        error_msg = f"Hardlink path does not exist on disk: {hardlink_path}"
        _logger.error(f"❌ {error_msg}")
        _mark_upload_failed(db, dataset_uuid, error_msg, hub_name_enum, logger)
        if not skip_missing:
            raise FileNotFoundError(error_msg)
        return None, None

    return dataset_uuid, hardlink_path


def _mark_upload_failed(
    db: "DatasetDatabase",
    dataset_uuid: str,
    error_msg: str,
    hub_name_enum: "DatasetsHubEnum",
    logger: logging.Logger | None = None
) -> None:
    """
    Mark upload task as failed with error message.

    Args:
        db: Database instance
        dataset_uuid: UUID of the dataset to mark as failed
        error_msg: Error message describing the failure
        hub_name_enum: The hub name enum (DatasetsHubEnum.modelscope or DatasetsHubEnum.huggingface)
        logger: Logger instance
    """
    from robocoin_dataset.database.models import DatasetDB

    _logger = logger or logging.getLogger(__name__)

    # Get correct field names (tries ms/hf first, then modelscope/huggingface)
    upload_status_field = _get_hub_field_prefix(hub_name_enum, DatasetDB, "upload_status")
    upload_err_field = _get_hub_field_prefix(hub_name_enum, DatasetDB, "upload_err_msg")

    with db.with_session() as session:
        item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
        if item:
            from robocoin_dataset.database.models import TaskStatus
            setattr(item, upload_status_field, TaskStatus.FAILED)
            setattr(item, upload_err_field, error_msg)
            session.commit()
            _logger.debug(f"Marked dataset {dataset_uuid} as FAILED: {error_msg}")


def _mark_upload_completed(
    db: "DatasetDatabase",
    dataset_uuid: str,
    hub_name_enum: "DatasetsHubEnum",
    logger: logging.Logger | None = None
) -> None:
    """
    Mark upload task as completed.

    Args:
        db: Database instance
        dataset_uuid: UUID of the dataset to mark as completed
        hub_name_enum: The hub name enum (DatasetsHubEnum.modelscope or DatasetsHubEnum.huggingface)
        logger: Logger instance
    """
    from robocoin_dataset.database.models import DatasetDB

    _logger = logger or logging.getLogger(__name__)

    # Get correct field names (tries ms/hf first, then modelscope/huggingface)
    upload_status_field = _get_hub_field_prefix(hub_name_enum, DatasetDB, "upload_status")

    with db.with_session() as session:
        item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
        if item:
            from robocoin_dataset.database.models import TaskStatus
            setattr(item, upload_status_field, TaskStatus.COMPLETED)
            session.commit()
            _logger.debug(f"Marked dataset {dataset_uuid} as COMPLETED")


__all__ = [
    "_get_hub_field_prefix",
    "_sync_datasets_upload_status",
    "_gen_one_dataset_upload_task",
    "_mark_upload_failed",
    "_mark_upload_completed",
]
