"""
RoboCoin Datasets Uploader
usage:
python -m robocoin.datasets.upload --config configs/upload.yaml
"""

import json
import uuid
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import draccus
from sqlalchemy.sql.expression import and_, or_
from tqdm import tqdm

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB, TaskStatus

from .constant import (
  COMMIT_MESSAGE_FILE,
  COMMIT_MSG_LABEL,
  COMMIT_UUID_LABEL,
  DS_PLATFORM_NAME,
  INIT_COMMIT_MSG,
  REMOTE_COMMIT_UUID_LABEL,
  UPLOAD_DATASET_ADDITIONAL_CHECK_STRUCTURE,
  DatasetsHubEnum,
)
from .local_datasets_util import LocalDsConfig, LocalDsUtil


@dataclass
class LocalDsUploadConfig(LocalDsConfig):
  """
  Configuration class for local dataset uploading.

  Attributes:
      hub_name (DatasetsHubEnum): Target hub platform for uploading datasets.
          Defaults to DatasetsHubEnum.HUGGINGFACE.
      token (str): Authentication token for the target hub platform. Defaults to empty string.
      namespace (str): Username/namespace on the target hub platform. If empty, uses DS_PLATFORM_NAME constant.
          Defaults to empty string.
      output_path (str): Path to the output directory for commit history files. Defaults to empty string.
      db_file_path (str): Path to the database file for dataset tracking. Defaults to empty string.
      batch_size (int): Number of datasets to upload in each batch. Defaults to 5.
      skip_missing (bool): Skip datasets with missing paths instead of aborting. Defaults to False.
      unified_repo_name (str): Name of the unified repository for batch uploads. Defaults to "robocoin-dataset".
  """

  hub_name: DatasetsHubEnum = DatasetsHubEnum.huggingface
  token: str = ""
  namespace: str = ""
  output_path: str = ""
  db_file_path: str = ""
  batch_size: int = 5
  skip_missing: bool = False
  unified_repo_name: str = "robocoin-dataset"


class LocalDsUploadUtil(LocalDsUtil):
  """
  Utility class for uploading local datasets to remote hubs.

  This class handles the process of validating local datasets, checking commit history,
  and uploading datasets to either Hugging Face or ModelScope platforms.

  Attributes:
      config (LocalDsUploadConfig): Configuration object for the uploader.
      hub: Hub-specific upload implementation (HuggingfaceUploadHub or ModelscopeUploadHub).
      logger: Logger instance for the uploader.
  """

  def __init__(self, config: LocalDsUploadConfig) -> None:
    """
    Initialize the uploader with configuration.

    Args:
        config (LocalDsUploadConfig): Configuration object for the uploader.

    Raises:
        ValueError: If the specified hub platform is not supported.
    """
    super().__init__(config)
    self.config = config

    # Determine namespace: use config.namespace if provided, otherwise fall back to DS_PLATFORM_NAME
    self.namespace = config.namespace if config.namespace else DS_PLATFORM_NAME

    if config.hub_name == DatasetsHubEnum.modelscope:
      from ..hubs.ms_hub import ModelscopeUploadHub

      self.hub = ModelscopeUploadHub(self.config.token)
    elif config.hub_name == DatasetsHubEnum.huggingface:
      from ..hubs.hf_hub import HuggingfaceUploadHub

      self.hub = HuggingfaceUploadHub(self.config.token)
    else:
      raise ValueError(f"hub {config.hub_name} is not supported.")
    pass

    self.logger = self.setup_logger(logger_name="UPLOAD_DATASETS")

  def _get_hub_field_prefix(self, field_suffix: str) -> str:
    """
    Get the correct field prefix for the hub, trying short version first, then long version.

    Args:
        field_suffix: The suffix of the field name (e.g., 'upload_status', 'upload_version').

    Returns:
        The full field name that exists in DatasetDB.

    Raises:
        AttributeError: If neither short nor long field name exists.
    """
    # Try short prefix first (ms/hf)
    short_prefix = "ms" if self.config.hub_name == DatasetsHubEnum.modelscope else "hf"
    short_field_name = f"{short_prefix}_{field_suffix}"

    if hasattr(DatasetDB, short_field_name):
      return short_field_name

    # Fall back to long prefix (modelscope/huggingface)
    long_prefix = "modelscope" if self.config.hub_name == DatasetsHubEnum.modelscope else "huggingface"
    long_field_name = f"{long_prefix}_{field_suffix}"

    if hasattr(DatasetDB, long_field_name):
      return long_field_name

    # Neither exists, raise error
    raise AttributeError(
      f"Neither '{short_field_name}' nor '{long_field_name}' field exists in DatasetDB"
    )

  @cached_property
  def output_path(self) -> Path:
    """
    Get the output path for commit history files with validation.

    Returns:
        Path: Absolute path to the output directory.

    Raises:
        ValueError: If output_path is not set in configuration.
    """
    if not self.config.output_path:
      raise ValueError("Output path is not set.")
    output_path = Path(self.config.output_path).expanduser().absolute()
    if not output_path.exists():
      output_path.mkdir(parents=True, exist_ok=True)
    return output_path

  def _commit_msg_exists(self, ds_name: str) -> bool:
    """
    Check if commit message file exists for a dataset.

    Args:
        ds_name (str): Name of the dataset.

    Returns:
        bool: True if commit message file exists, False otherwise.
    """
    return self.root_path.joinpath(ds_name, COMMIT_MESSAGE_FILE).exists()

  def _get_or_init_commit_msg(self, ds_name: str) -> tuple[str, str]:
    """
    Get existing commit message or initialize a new one.

    Args:
        ds_name (str): Name of the dataset.

    Returns:
        tuple[str, str]: Commit message and commit UUID.

    Raises:
        JSONDecodeError: If commit message file contains invalid JSON.
        OSError: If there are file I/O errors.
    """
    commit_msg_file_path = self.root_path.joinpath(ds_name).joinpath(COMMIT_MESSAGE_FILE)
    commit_msg = INIT_COMMIT_MSG
    commit_uuid = uuid.uuid4()
    try:
      if self._commit_msg_exists(ds_name):
        with open(commit_msg_file_path, encoding="utf-8") as f:
          data = json.load(f)
          commit_msg = data.get(COMMIT_MSG_LABEL)
          commit_uuid = data.get(COMMIT_UUID_LABEL)
      else:
        with open(commit_msg_file_path, "w+", encoding="utf-8") as f:
          commit_msg = INIT_COMMIT_MSG
          commit_uuid = str(uuid.uuid4())
          json_data = {COMMIT_MSG_LABEL: commit_msg, COMMIT_UUID_LABEL: commit_uuid}
          json.dump(json_data, f, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, OSError) as e:
      raise e

    return commit_msg, commit_uuid

  def _commit_msg_history_file_path(self, ds_name: str) -> Path:
    """
    Get the path to the commit history file for a dataset.

    Args:
        ds_name (str): Name of the dataset.

    Returns:
        Path: Path to the commit history file.
    """
    return self.output_path.joinpath(f"{self.config.hub_name}", f"{ds_name}.json")

  def _get_commit_history_msg(self, ds_name: str) -> tuple[str, str]:
    """
    Get commit history message for a dataset.

    Args:
        ds_name (str): Name of the dataset.

    Returns:
        tuple[str, str]: Commit history message and commit history UUID.
    """
    commit_history_msg = ""
    commit_history_uuid = ""
    commit_msg_history_file_path = self._commit_msg_history_file_path(ds_name)
    if commit_msg_history_file_path.exists():
      with open(commit_msg_history_file_path, encoding="utf-8") as f:
        data = json.load(f)
        commit_history_msg = data.get(COMMIT_MSG_LABEL)
        commit_history_uuid = data.get(COMMIT_UUID_LABEL)

    return commit_history_msg, commit_history_uuid

  def _update_commit_history_msg(self, ds_name: str, remote_commit_uuid: str) -> None:
    """
    Update commit history message file with remote commit information.

    Args:
        ds_name (str): Name of the dataset.
        remote_commit_uuid (str): UUID of the remote commit.
    """
    commit_msg, commit_uuid = self._get_or_init_commit_msg(ds_name)
    commit_msg_history_file_path = self._commit_msg_history_file_path(ds_name)
    commit_msg_history_dir = commit_msg_history_file_path.parent
    commit_msg_history_dir.mkdir(parents=True, exist_ok=True)

    with open(commit_msg_history_file_path, "w+", encoding="utf-8") as f:
      json_data = {
        COMMIT_MSG_LABEL: commit_msg,
        COMMIT_UUID_LABEL: commit_uuid,
        REMOTE_COMMIT_UUID_LABEL: remote_commit_uuid,
      }
      json.dump(json_data, f, indent=2, ensure_ascii=False)

  def _upload_dataset(self, ds_name: str, commit_msg: str) -> bool:
    """
    Upload a single dataset to the remote hub.

    Args:
        ds_name (str): Name of the dataset to upload.
        commit_msg (str): Commit message for the upload.

    Returns:
        bool: True if upload was successful, False otherwise.
    """
    log_prefix = f"dataset {ds_name}:"
    try:
      self.check_dataset_dir_valid(
        ds_name=ds_name, additional_check_list=UPLOAD_DATASET_ADDITIONAL_CHECK_STRUCTURE
      )
    except Exception as e:
      self.logger.error(f"{log_prefix} {e}")
      return False

    ds_path = self.root_path.joinpath(ds_name)
    if not ds_path.exists():
      raise FileNotFoundError(f"dataset path {ds_path} does not exist")

    repo_id = f"{self.namespace}/{ds_name}"

    try:
      if not self.hub.repo_exists(repo_id=repo_id):
        self.logger.info(
          f"{log_prefix} repo {repo_id} does not exists in {self.config.hub_name}, creating repo {repo_id}"
        )
        self.hub.create_repo(repo_id=repo_id)

      commit_url: str = self.hub.upload_repo(ds_path, repo_id, commit_msg)
      remote_commit_uuid = commit_url.split("/")[-1]
      self.logger.info(
        f"{log_prefix} repo {repo_id} has been uploaded successfully, commit_url is: {commit_url}"
      )

      self._update_commit_history_msg(ds_name, remote_commit_uuid)
      return True

    except Exception as e:
      self.logger.error(f"{log_prefix} {e}")

    return False

  def upload_datasets(self) -> None:
    """
    Upload all datasets that need to be updated.

    This method validates datasets, checks which ones need to be uploaded based on
    commit history, and performs the upload process for each dataset.
    """
    datasets_to_update: dict[str, str] = {}
    self.check_root_path_valid()

    ds_names = self.get_root_path_subdirs()
    valid_ds_names: list[str] = []
    for ds_name in ds_names:
      try:
        self.check_dataset_dir_valid(
          ds_name, additional_check_list=UPLOAD_DATASET_ADDITIONAL_CHECK_STRUCTURE
        )
        valid_ds_names.append(ds_name)
        should_upload, commit_msg = self._should_upload(ds_name=ds_name)
        if should_upload:
          datasets_to_update[ds_name] = commit_msg
      except Exception as e:  # noqa: PERF203
        self.logger.error(f"{ds_name} is not valid, error: {e}")

    self.logger.info(
      f"found {len(valid_ds_names)} in path {self.root_path}, {len(datasets_to_update)} datasets need to update."
    )

    if datasets_to_update:
      for ds_name, commit_msg in tqdm(
        datasets_to_update.items(),
        desc=f"Upload {self.namespace} datasets",
        bar_format="\033[32m{l_bar}{bar}\033[0m{r_bar}",
      ):
        self._upload_dataset(ds_name=ds_name, commit_msg=commit_msg)

  def _sync_datasets_upload_status(self, db: DatasetDatabase, retry_failed: bool = False) -> list[DatasetDB]:
    """
    Sync datasets upload status from database.
    Set all ds need uploading to PENDING and increment the version,
    sync the version_ps to the visualize_check_status.

    Args:
        db: Database instance.
        retry_failed: If True, retry failed uploads. Otherwise only process pending ones.

    Returns:
        List of datasets that need to be uploaded.
    """
    # Get correct field names (tries ms/hf first, then modelscope/huggingface)
    upload_status_field = self._get_hub_field_prefix("upload_status")
    upload_version_field = self._get_hub_field_prefix("upload_version")
    upload_version_ps_field = self._get_hub_field_prefix("upload_version_ps")

    # Get column objects for dynamic field names
    upload_status_col = getattr(DatasetDB, upload_status_field)
    upload_version_ps_col = getattr(DatasetDB, upload_version_ps_field)

    with db.with_session() as session:
      if retry_failed:
        status_list = [
          TaskStatus.FAILED,
          TaskStatus.PENDING,
        ]
      else:
        status_list = [TaskStatus.PENDING]

      query = session.query(DatasetDB).filter(
        and_(
          DatasetDB.visualize_check_status == TaskStatus.COMPLETED,
          or_(
            upload_status_col.in_(status_list),
            and_(
              upload_status_col == TaskStatus.COMPLETED,
              upload_version_ps_col < DatasetDB.visualize_check_status,
            ),
          ),
        )
      )

      for item in query.all():
        setattr(item, upload_status_field, TaskStatus.PENDING)
        current_version = getattr(item, upload_version_field, 0) or 0
        setattr(item, upload_version_field, current_version + 1)
        setattr(item, upload_version_ps_field, item.visualize_check_status)
      session.commit()

      # items = query.all()
      # # Detach from session to avoid lazy loading issues
      # return [session.merge(item) for item in items]

  def _gen_one_dataset_upload_task(self) -> tuple[str, str]:
      """
      Generate one dataset upload task by finding a pending upload and marking it as PROCESSING.

      Returns:
          Tuple of (dataset_uuid, upload_path) if a task was found, (None, None) otherwise.
          upload_path is the convert_path with _hardlink suffix.
      """
      # Get correct field names (tries ms/hf first, then modelscope/huggingface)
      upload_status_field = self._get_hub_field_prefix("upload_status")

      # Get column objects for dynamic field names
      upload_status_col = getattr(DatasetDB, upload_status_field)

      with self.db.with_session() as session:
          query = session.query(DatasetDB).filter(
              and_(
                  DatasetDB.visualize_check_status == TaskStatus.COMPLETED,
                  upload_status_col == TaskStatus.PENDING,
              )
          )
          item = query.first()
          if not item:
              return None, None

          setattr(item, upload_status_field, TaskStatus.PROCESSING)
          session.commit()

          # Generate upload_path as convert_path with _hardlink suffix
          upload_path = f"{item.convert_path}_hardlink"

          return item.dataset_uuid, upload_path

  def _validate_dataset_paths(self, datasets: list[DatasetDB], db: DatasetDatabase) -> tuple[list[DatasetDB], list[DatasetDB]]:
    """
    Validate that convert_path and convert_path_hardlink exist and are valid for each dataset.

    Args:
        datasets: List of datasets to validate.
        db: Database instance.

    Returns:
        Tuple of (valid_datasets, invalid_datasets).
    """
    valid = []
    invalid = []

    for item in datasets:
      # Check if convert_path exists
      convert_path = Path(item.convert_path).expanduser().absolute()
      if not convert_path.exists():
        invalid.append(item)
        error_msg = f"convert_path does not exist: {item.convert_path}"
        self.logger.warning(f"⚠️  Dataset {item.dataset_uuid}: {error_msg}")
        self._mark_upload_failed(item.dataset_uuid, error_msg, db)
        continue

      if not convert_path.is_dir():
        invalid.append(item)
        error_msg = f"convert_path is not a directory: {item.convert_path}"
        self.logger.warning(f"⚠️  Dataset {item.dataset_uuid}: {error_msg}")
        self._mark_upload_failed(item.dataset_uuid, error_msg, db)
        continue

      # Check if <convert_path>_hardlink exists
      hardlink_path = Path(f"{item.convert_path}_hardlink").expanduser().absolute()
      if not hardlink_path.exists():
        invalid.append(item)
        error_msg = f"hardlink path does not exist: {hardlink_path}"
        self.logger.warning(f"⚠️  Dataset {item.dataset_uuid}: {error_msg}")
        self._mark_upload_failed(item.dataset_uuid, error_msg, db)
        continue

      if not hardlink_path.is_dir():
        invalid.append(item)
        error_msg = f"hardlink path is not a directory: {hardlink_path}"
        self.logger.warning(f"⚠️  Dataset {item.dataset_uuid}: {error_msg}")
        self._mark_upload_failed(item.dataset_uuid, error_msg, db)
        continue

      # Check if hardlink directory is valid (not empty)
      try:
        if not any(hardlink_path.iterdir()):
          invalid.append(item)
          error_msg = f"hardlink path is empty: {hardlink_path}"
          self.logger.warning(f"⚠️  Dataset {item.dataset_uuid}: {error_msg}")
          self._mark_upload_failed(item.dataset_uuid, error_msg, db)
          continue
      except PermissionError as e:
        invalid.append(item)
        error_msg = f"cannot access hardlink path: {hardlink_path} - {e}"
        self.logger.warning(f"⚠️  Dataset {item.dataset_uuid}: {error_msg}")
        self._mark_upload_failed(item.dataset_uuid, error_msg, db)
        continue

      # All checks passed
      valid.append(item)

    return valid, invalid

  def _mark_upload_failed(self, dataset_uuid: str, error_msg: str, db: DatasetDatabase) -> None:
    """
    Mark a dataset upload as FAILED in the database.

    Args:
        dataset_uuid: UUID of the dataset.
        error_msg: Error message to store.
        db: Database instance.
    """
    # Get correct field names (tries ms/hf first, then modelscope/huggingface)
    upload_status_field = self._get_hub_field_prefix("upload_status")
    upload_err_field = self._get_hub_field_prefix("upload_err_msg")

    with db.with_session() as session:
      item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
      if item:
        setattr(item, upload_status_field, TaskStatus.FAILED)
        setattr(item, upload_err_field, error_msg)
        session.commit()

  def _mark_upload_completed(self, dataset_uuid: str, db: DatasetDatabase) -> None:
    """
    Mark a dataset upload as COMPLETED in the database.

    Args:
        dataset_uuid: UUID of the dataset.
        db: Database instance.
    """
    # Get correct field names (tries ms/hf first, then modelscope/huggingface)
    upload_status_field = self._get_hub_field_prefix("upload_status")

    with db.with_session() as session:
      item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
      if item:
        setattr(item, upload_status_field, TaskStatus.COMPLETED)
        session.commit()

  def _check_repo_conflict(self, repo_id: str) -> bool:
    """
    Check if repository exists and prompt user for confirmation.

    Args:
        repo_id: Repository identifier.

    Returns:
        True if user confirms to proceed, False otherwise.
    """
    if not self.hub.repo_exists(repo_id=repo_id):
      return True

    print("\n" + "⚠️ " * 35)
    print(f"WARNING: Repository {repo_id} already exists on {self.config.hub_name}")
    print("⚠️ " * 35)
    print("\nThe upload will perform an UPSERT operation:")
    print("  • Remote files not in this upload will be KEPT")
    print("  • Local files not on remote will be UPLOADED")
    print("  • Files existing in both locations will be OVERWRITTEN by local versions")
    print("\nEach overwritten file will generate a warning message.\n")

    response = input(f"Proceed with upload to {repo_id}? (y/n): ").strip().lower()
    return response in ["y", "yes"]

  def upload_datasets_from_db(self) -> None:
    """
    Upload datasets from database in batches.

    This method uses _sync_datasets_upload_status, _gen_one_dataset_upload_task,
    _validate_dataset_paths, _mark_upload_failed, _mark_upload_completed, and
    _check_repo_conflict functions, and calls _upload_dataset as its core implementation.
    """
    # Validate database path
    if not self.config.db_file_path:
      self.logger.error("❌ db_file_path is not configured")
      raise ValueError("db_file_path must be specified in config or via --db_file_path")

    db_path = Path(self.config.db_file_path).expanduser().absolute()
    if not db_path.exists():
      self.logger.error(f"❌ Database file not found: {db_path}")
      raise FileNotFoundError(f"Database file not found: {db_path}")

    self.logger.info(f"\n{'='*70}")
    self.logger.info("DATABASE-DRIVEN UPLOAD")
    self.logger.info(f"{'='*70}")
    self.logger.info(f"Database: {db_path}")
    self.logger.info(f"Target Hub: {self.config.hub_name}")
    self.logger.info(f"Namespace: {self.namespace}")
    self.logger.info(f"Batch Size: {self.config.batch_size}")
    self.logger.info(f"Skip Missing: {self.config.skip_missing}")
    self.logger.info(f"{'='*70}\n")

    # Connect to database and store it as instance attribute for helper methods
    self.db = DatasetDatabase(db_path)

    # Step 1: Sync datasets upload status from database
    self.logger.info("Step 1: Syncing upload status from database...")
    self._sync_datasets_upload_status(self.db, retry_failed=False)
    self.logger.info("  Upload status synced\n")

    # Step 2: Process datasets one by one from database
    self.logger.info("Step 2: Processing datasets from database...\n")

    uploaded_count = 0
    failed_count = 0

    # Store original root_path to restore later
    original_root_path = self.root_path

    try:
      while True:
        # Get next dataset to upload from database
        dataset_uuid, upload_path = self._gen_one_dataset_upload_task()
        if dataset_uuid is None:
          self.logger.info("✓ No more datasets to upload")
          break

        # Query the dataset from database to get additional info
        with self.db.with_session() as session:
          item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
          if not item:
            self.logger.error(f"❌ Dataset {dataset_uuid} not found in database")
            continue

        dataset_name = item.dataset_name

        # Validate paths for this dataset
        valid, invalid = self._validate_dataset_paths([item], self.db)

        if invalid:
          failed_count += 1
          if not self.config.skip_missing:
            self.logger.error(f"❌ Dataset {dataset_name} has missing paths")
            self.logger.error("❌ Aborting upload (use --skip_missing=true to skip invalid datasets)")
            raise FileNotFoundError(f"Dataset {dataset_name} has missing convert_path")
          self.logger.warning(f"⚠️  Skipping {dataset_name} with missing paths")
          continue

        # Get the hardlink path directly from convert_path
        hardlink_path = Path(f"{item.convert_path}_hardlink").expanduser().absolute()

        # Check repo conflict before uploading
        repo_id = f"{self.namespace}/{dataset_name}"
        if not self._check_repo_conflict(repo_id):
          self.logger.warning(f"⚠️  Skipping {dataset_name} due to user cancellation")
          self._mark_upload_failed(item.dataset_uuid, "User cancelled upload due to repo conflict", self.db)
          failed_count += 1
          continue

        # Get or initialize commit message from the hardlink dataset path
        commit_msg_file_path = hardlink_path / COMMIT_MESSAGE_FILE

        if commit_msg_file_path.exists():
          try:
            with open(commit_msg_file_path, encoding="utf-8") as f:
              data = json.load(f)
              commit_msg = data.get(COMMIT_MSG_LABEL, INIT_COMMIT_MSG)
          except (json.JSONDecodeError, OSError) as e:
            self.logger.warning(f"⚠️  Failed to read commit message for {dataset_name}: {e}")
            commit_msg = INIT_COMMIT_MSG
        else:
          commit_msg = INIT_COMMIT_MSG
          commit_uuid = str(uuid.uuid4())
          try:
            commit_msg_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(commit_msg_file_path, "w+", encoding="utf-8") as f:
              json_data = {COMMIT_MSG_LABEL: commit_msg, COMMIT_UUID_LABEL: commit_uuid}
              json.dump(json_data, f, indent=2, ensure_ascii=False)
          except (OSError, PermissionError) as e:
            self.logger.warning(f"⚠️  Failed to create commit message for {dataset_name}: {e}")

        self.logger.info(f"📤 Uploading {dataset_name} from {hardlink_path}")

        # Upload the dataset by temporarily setting root_path to hardlink's parent
        try:
          # Temporarily set root_path to the parent of the hardlink directory
          self.root_path = hardlink_path.parent

          # Use the hardlink directory name for upload
          success = self._upload_dataset(ds_name=hardlink_path.name, commit_msg=commit_msg)

          if success:
            self._mark_upload_completed(item.dataset_uuid, self.db)
            uploaded_count += 1
            self.logger.info(f"✓ Successfully uploaded {dataset_name}\n")
          else:
            self._mark_upload_failed(item.dataset_uuid, "Upload failed", self.db)
            failed_count += 1
            self.logger.error(f"❌ Failed to upload {dataset_name}\n")

        except Exception as e:
          error_msg = str(e)
          self.logger.error(f"❌ Error uploading {dataset_name}: {error_msg}\n")
          self._mark_upload_failed(item.dataset_uuid, error_msg, self.db)
          failed_count += 1

        finally:
          # Restore original root_path after each upload
          self.root_path = original_root_path

    finally:
      # Ensure root_path is restored
      self.root_path = original_root_path

    # Final summary
    self.logger.info(f"\n{'='*70}")
    self.logger.info("✓ UPLOAD COMPLETE")
    self.logger.info(f"  Total datasets uploaded: {uploaded_count}")
    if failed_count > 0:
      self.logger.info(f"  Datasets failed: {failed_count}")
    self.logger.info(f"{'='*70}\n")

  pass


if __name__ == "__main__":
  """
    Main entry point for the dataset uploader.

    Parses command line configuration and runs the upload process.
    """
  config = draccus.parse(LocalDsUploadConfig)
  uploader = LocalDsUploadUtil(config)
  uploader.upload_datasets()
  pass
