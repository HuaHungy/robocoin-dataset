import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from robocoin_dataset.database.database import DatasetDatabase
    from robocoin_dataset.database.models import DatasetDB


######## TASK MANAGEMENT ########


def _sync_page_sync_status(
    db: "DatasetDatabase",
    session: "Session",
    logger: logging.Logger | None = None,
) -> None:
  '''Sync: mark PENDING if the record need to be page_synced
  I: Database. O: None, change PENDING directly.(version ++ and sync also)
  '''

  from sqlalchemy.sql.expression import and_, or_

  from robocoin_dataset.database.models import DatasetDB, TaskStatus

  hf_prefix, ms_prefix = _get_hub_field_prefix(DatasetDB)
  _logger = logger or logging.getLogger(__name__)

  # Build dynamic field names
  ms_upload_status_field = f"{ms_prefix}_upload_status"
  hf_upload_status_field = f"{hf_prefix}_upload_status"
  ms_upload_version_field = f"{ms_prefix}_upload_version"
  hf_upload_version_field = f"{hf_prefix}_upload_version"

  # Query datasets that need page sync
  query = session.query(DatasetDB).filter(
    and_(
        getattr(DatasetDB, ms_upload_status_field) == TaskStatus.COMPLETED,
        getattr(DatasetDB, hf_upload_status_field) == TaskStatus.COMPLETED, # and: must two.
        or_(
            DatasetDB.dataset_info_sync_status == TaskStatus.PENDING,
            and_( # or: if one
                DatasetDB.dataset_info_sync_status == TaskStatus.COMPLETED,
                DatasetDB.dataset_info_sync_version_ps < getattr(DatasetDB, ms_upload_version_field),
                DatasetDB.dataset_info_sync_version_ps < getattr(DatasetDB, hf_upload_version_field),
            ),
        ),
    ),
  )

  items = query.all()
  if not items:
    _logger.debug("No datasets found for page sync")
    return

  _logger.info(f"Found {len(items)} datasets to sync page info")

  # Update status to PENDING for found items
  for item in items:
      item.dataset_info_sync_status = TaskStatus.PENDING

      # Set dataset_info_sync_version_ps to min of ms and hf upload versions
      ms_version = getattr(item, ms_upload_version_field) if hasattr(item, ms_upload_version_field) else 0
      hf_version = getattr(item, hf_upload_version_field) if hasattr(item, hf_upload_version_field) else 0
      item.dataset_info_sync_version_ps = min(ms_version, hf_version)

      # Increment dataset_info_sync_version
      current_version = item.dataset_info_sync_version if hasattr(item, 'dataset_info_sync_version') and item.dataset_info_sync_version else 0
      item.dataset_info_sync_version = current_version + 1

      _logger.debug(f"Marked dataset {item.dataset_uuid} as PENDING for page sync")

  session.commit()
  _logger.info(f"Successfully marked {len(items)} datasets as PENDING")


def _gen_one_page_sync_task(session: "Session") -> tuple[str | None, str | None, str | None]:
  '''Mark first PENDING -> PROCESSING, and return the yaml_path, hardlink_path, and dataset_uuid
  I: Database session.
  O: yaml_path, -> read the metadata.
  hardlink_path, -> the dataset in lerobot foramt.
  dataset_uuid -> to identify which record should be COMPLETED or FAILED.
  '''

  from sqlalchemy.sql.expression import and_

  from robocoin_dataset.database.models import DatasetDB, DatasetHardLinkDB, TaskStatus

  _logger = logging.getLogger(__name__)

  hf_prefix, ms_prefix = _get_hub_field_prefix(DatasetDB)
  ms_upload_status_field = f"{ms_prefix}_upload_status"
  hf_upload_status_field = f"{hf_prefix}_upload_status"

  _logger.debug("Querying for PENDING tasks...")
  query = session.query(DatasetDB).filter(
      and_(
          DatasetDB.dataset_info_sync_status == TaskStatus.PENDING,
          getattr(DatasetDB, ms_upload_status_field) == TaskStatus.COMPLETED,
          getattr(DatasetDB, hf_upload_status_field) == TaskStatus.COMPLETED,
      )
  )

  item = query.first()
  if not item:
      _logger.debug("No PENDING tasks found")
      return None, None, None

  _logger.debug("Found PENDING task, marking as PROCESSING...")
  item.dataset_info_sync_status = TaskStatus.PROCESSING
  session.commit()

  # Get dataset_uuid
  dataset_uuid = item.dataset_uuid if hasattr(item, 'dataset_uuid') and item.dataset_uuid else None
  _logger.debug(f"Dataset UUID: {dataset_uuid}")

  # Get yaml path from dataset
  yaml_path = item.yaml_file_path if hasattr(item, 'yaml_file_path') and item.yaml_file_path else None
  _logger.debug(f"YAML path: {yaml_path}")

  # Get hardlink path from dataset_hard_link table using dataset_uuid
  try:
      _logger.debug(f"Querying hardlink path for dataset_uuid: {dataset_uuid}")
      hardlink_record = session.query(DatasetHardLinkDB).filter(
          DatasetHardLinkDB.dataset_uuid == dataset_uuid
      ).first()
      hardlink_path = Path(hardlink_record.hard_link_path) if hardlink_record and hardlink_record.hard_link_path else None

      if hardlink_path is None:
          raise FileNotFoundError(
              f"No hardlink found in database for dataset {dataset_uuid}. "
              f"Hardlinks must be created before running page sync."
          )

      # Verify hardlink path exists on disk
      if not hardlink_path.exists():
          raise FileNotFoundError(
              f"Hardlink path in database does not exist on disk: {hardlink_path}"
          )
  except FileNotFoundError:
      # Re-raise FileNotFoundError as-is
      raise
  except Exception as e:
      # Wrap other exceptions as FileNotFoundError
      raise FileNotFoundError(
          f"Failed to retrieve or validate hardlink for dataset {dataset_uuid}: {e}"
      ) from e

  return yaml_path, hardlink_path, dataset_uuid


def _mark_task_completed(session: "Session", dataset_uuid: str) -> None:
  """
  Mark the specific task as COMPLETED using dataset_uuid.
  """
  from robocoin_dataset.database.models import DatasetDB, TaskStatus

  query = session.query(DatasetDB).filter(
      DatasetDB.dataset_uuid == dataset_uuid
  )
  item = query.first()

  if item:
      item.dataset_info_sync_status = TaskStatus.COMPLETED
      session.commit()
      logging.getLogger(__name__).info(f"Marked dataset {dataset_uuid} as COMPLETED")

def _mark_task_failed(session: "Session", dataset_uuid: str) -> None:
  """
  Mark the specific task as FAILED using dataset_uuid.
  """
  from robocoin_dataset.database.models import DatasetDB, TaskStatus

  query = session.query(DatasetDB).filter(
      DatasetDB.dataset_uuid == dataset_uuid
  )
  item = query.first()

  if item:
      item.dataset_info_sync_status = TaskStatus.FAILED
      session.commit()
      logging.getLogger(__name__).error(f"Marked dataset {dataset_uuid} as FAILED")

def _get_hub_field_prefix(dataset_table: "type[DatasetDB]") -> tuple[str, str]:
    '''Return the correct field prefixes for both HuggingFace and ModelScope hubs,
    trying short versions first (hf/ms), then long versions (huggingface/modelscope).'''
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


def _get_dataset_name(session: "Session") -> str | None:
  """
  Get dataset name from a PROCESSING status record.
  This is for the page script compatibility.
  """
  from pathlib import Path

  from robocoin_dataset.database.models import DatasetDB, TaskStatus

  _logger = logging.getLogger(__name__)

  _logger.debug("Querying for PROCESSING task to get dataset name...")
  query = session.query(DatasetDB).filter(
      DatasetDB.dataset_info_sync_status == TaskStatus.PROCESSING
  )
  item = query.first()

  if not item:
      _logger.warning("No PROCESSING task found when trying to get dataset name")
      return None

  if not hasattr(item, 'convert_path') or not item.convert_path:
      _logger.warning("PROCESSING task found but convert_path is missing or empty")
      return None

  # Get the basename (ending) of the convert_path as dataset_name
  dataset_name = Path(item.convert_path).name
  _logger.debug(f"Retrieved dataset name: {dataset_name}")
  return dataset_name
