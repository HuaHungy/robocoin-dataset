"""
RoboCoin Datasets Uploader
usage:
python -m robocoin.datasets.upload --config configs/upload.yaml
"""

import json
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import draccus
from sqlalchemy.sql.expression import and_
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
      output_path (str): Path to the output directory for commit history files. Defaults to empty string.
      db_file_path (str): Path to the database file for dataset tracking. Defaults to empty string.
      batch_size (int): Number of datasets to upload in each batch. Defaults to 5.
      skip_missing (bool): Skip datasets with missing paths instead of aborting. Defaults to False.
      unified_repo_name (str): Name of the unified repository for batch uploads. Defaults to "robocoin-dataset".
  """

  hub_name: DatasetsHubEnum = DatasetsHubEnum.huggingface
  token: str = ""
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

  def _should_upload(self, ds_name: str) -> tuple[bool, str]:
    """
    Determine if a dataset should be uploaded based on commit history.

    Args:
        ds_name (str): Name of the dataset.

    Returns:
        tuple[bool, str]: Whether to upload and the commit message.
    """
    should_upload = True
    commit_msg, commit_uuid = self._get_or_init_commit_msg(ds_name)
    _, commit_history_uuid = self._get_commit_history_msg(ds_name)
    if commit_history_uuid == "":
      should_upload = True
    else:
      should_upload = commit_uuid != commit_history_uuid
    return should_upload, commit_msg

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

    repo_id = f"{DS_PLATFORM_NAME}/{ds_name}"

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
        desc=f"Upload {DS_PLATFORM_NAME} datasets",
        bar_format="\033[32m{l_bar}{bar}\033[0m{r_bar}",
      ):
        self._upload_dataset(ds_name=ds_name, commit_msg=commit_msg)

  def _query_upload_ready_datasets(self, db: DatasetDatabase) -> list[DatasetDB]:
    """
    Query database for datasets that are ready to be uploaded.

    Criteria:
      - convert_path is not NULL
      - convert_status == COMPLETED
      - data_loader_detection_status == COMPLETED
      - Version is up-to-date: data_loader_detection_version_ps >= convert_version

    Args:
        db: Database instance.

    Returns:
        List of DatasetDB objects ready for upload.
    """
    with db.with_session() as session:
      query = session.query(DatasetDB).filter(
        and_(
          DatasetDB.convert_path != None,  # noqa: E711
          DatasetDB.convert_status == TaskStatus.COMPLETED,
          DatasetDB.data_loader_detection_status == TaskStatus.COMPLETED,
          DatasetDB.data_loader_detection_version_ps >= DatasetDB.convert_version,
        )
      )
      items = query.all()
      # Detach from session to avoid lazy loading issues
      return [session.merge(item) for item in items]

  def _filter_changed_datasets(self, datasets: list[DatasetDB], db: DatasetDatabase) -> list[DatasetDB]:
    """
    Filter datasets that have been changed since last upload.

    Checks if the dataset's convert_version is greater than the last uploaded version.

    Args:
        datasets: List of candidate datasets.
        db: Database instance.

    Returns:
        List of datasets that need to be uploaded.
    """
    changed = []
    upload_status_field = f"{self.config.hub_name}_upload_status"
    upload_version_ps_field = f"{self.config.hub_name}_upload_version_ps"

    for item in datasets:
      status = getattr(item, upload_status_field, None)
      uploaded_version_ps = getattr(item, upload_version_ps_field, 0) or 0

      # Upload if never uploaded OR version has changed
      if status is None or status != TaskStatus.COMPLETED or uploaded_version_ps < item.convert_version:
        changed.append(item)

    return changed

  def _validate_dataset_paths(self, datasets: list[DatasetDB], db: DatasetDatabase) -> tuple[list[DatasetDB], list[DatasetDB]]:
    """
    Validate that convert_path exists for each dataset.

    Args:
        datasets: List of datasets to validate.
        db: Database instance.

    Returns:
        Tuple of (valid_datasets, invalid_datasets).
    """
    valid = []
    invalid = []

    for item in datasets:
      convert_path = Path(item.convert_path).expanduser().absolute()
      if convert_path.exists():
        valid.append(item)
      else:
        invalid.append(item)
        self.logger.warning(
          f"⚠️  Dataset {item.dataset_uuid} has invalid convert_path: {item.convert_path} (does not exist)"
        )
        # Mark as FAILED in database
        self._mark_upload_failed(item.dataset_uuid, f"convert_path does not exist: {item.convert_path}", db)

    return valid, invalid

  def _mark_upload_failed(self, dataset_uuid: str, error_msg: str, db: DatasetDatabase) -> None:
    """
    Mark a dataset upload as FAILED in the database.

    Args:
        dataset_uuid: UUID of the dataset.
        error_msg: Error message to store.
        db: Database instance.
    """
    upload_status_field = f"{self.config.hub_name}_upload_status"
    upload_err_field = f"{self.config.hub_name}_upload_err_msg"

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
    upload_status_field = f"{self.config.hub_name}_upload_status"
    upload_version_field = f"{self.config.hub_name}_upload_version"
    upload_version_ps_field = f"{self.config.hub_name}_upload_version_ps"

    with db.with_session() as session:
      item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
      if item:
        setattr(item, upload_status_field, TaskStatus.COMPLETED)
        current_version = getattr(item, upload_version_field, 0) or 0
        setattr(item, upload_version_field, current_version + 1)
        setattr(item, upload_version_ps_field, item.convert_version)
        session.commit()

  def _create_staging_directory(self, datasets: list[DatasetDB]) -> Path:
    """
    Create a temporary staging directory and copy datasets into it.

    Args:
        datasets: List of datasets to stage.

    Returns:
        Path to the staging directory.
    """
    staging_dir = Path(tempfile.mkdtemp(prefix="robocoin_upload_"))
    self.logger.info(f"Created staging directory: {staging_dir}")

    for item in datasets:
      convert_path = Path(item.convert_path).expanduser().absolute()
      dataset_name = convert_path.name
      dest_path = staging_dir / dataset_name

      self.logger.info(f"Copying {convert_path} -> {dest_path}")
      shutil.copytree(convert_path, dest_path, symlinks=True)

    return staging_dir

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

  def _upload_batch_unified(self, datasets: list[DatasetDB], batch_num: int, total_batches: int, db: DatasetDatabase) -> None:
    """
    Upload a batch of datasets to a unified repository.

    Args:
        datasets: List of datasets in this batch.
        batch_num: Current batch number (1-indexed).
        total_batches: Total number of batches.
        db: Database instance.
    """
    staging_dir = None
    try:
      # Create staging directory
      staging_dir = self._create_staging_directory(datasets)

      # Generate commit message
      dataset_names = [Path(item.convert_path).name for item in datasets]
      commit_msg = f"Batch upload: {len(datasets)} datasets ({', '.join(dataset_names[:5])}"
      if len(dataset_names) > 5:
        commit_msg += f", and {len(dataset_names) - 5} more"
      commit_msg += ")"

      # Repository ID
      repo_id = f"{DS_PLATFORM_NAME}/{self.config.unified_repo_name}"

      self.logger.info(f"\n{'='*70}")
      self.logger.info(f"Uploading batch {batch_num}/{total_batches} to {repo_id}")
      self.logger.info(f"Datasets in this batch: {len(datasets)}")
      self.logger.info(f"{'='*70}\n")

      # Check for conflicts (only for first batch)
      if batch_num == 1:
        if not self._check_repo_conflict(repo_id):
          self.logger.warning("Upload cancelled by user")
          for item in datasets:
            self._mark_upload_failed(item.dataset_uuid, "Upload cancelled by user", db)
          return

      # Create repo if needed
      if not self.hub.repo_exists(repo_id=repo_id):
        self.logger.info(f"Creating repository {repo_id}")
        self.hub.create_repo(repo_id=repo_id)

      # Upload
      self.logger.info(f"Uploading {staging_dir} to {repo_id}...")
      commit_url = self.hub.upload_repo(staging_dir, repo_id, commit_msg)
      self.logger.info(f"✓ Upload successful: {commit_url}")

      # Update database status for all datasets in batch
      for item in datasets:
        dataset_name = Path(item.convert_path).name
        self.logger.info(f"  ✓ Uploaded: {dataset_name}")
        self._mark_upload_completed(item.dataset_uuid, db)

    except Exception as e:
      self.logger.error(f"Batch upload failed: {e}")
      for item in datasets:
        self._mark_upload_failed(item.dataset_uuid, str(e), db)
      raise

    finally:
      # Cleanup staging directory
      if staging_dir and staging_dir.exists():
        self.logger.info(f"Cleaning up staging directory: {staging_dir}")
        shutil.rmtree(staging_dir, ignore_errors=True)

  def upload_datasets_from_db(self) -> None:
    """
    Upload datasets from database in batches to a unified repository.

    This method:
    1. Connects to the database specified in config
    2. Queries for upload-ready datasets
    3. Filters for changed datasets
    4. Validates paths
    5. Uploads in batches
    6. Updates database status
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
    self.logger.info(f"Unified Repo: {DS_PLATFORM_NAME}/{self.config.unified_repo_name}")
    self.logger.info(f"Batch Size: {self.config.batch_size}")
    self.logger.info(f"Skip Missing: {self.config.skip_missing}")
    self.logger.info(f"{'='*70}\n")

    # Connect to database
    db = DatasetDatabase(db_path)

    # Step 1: Query upload-ready datasets
    self.logger.info("Step 1: Querying upload-ready datasets...")
    all_ready = self._query_upload_ready_datasets(db)
    self.logger.info(f"  Found {len(all_ready)} upload-ready datasets\n")

    if not all_ready:
      self.logger.info("✓ No datasets to upload")
      return

    # Step 2: Filter for changed datasets
    self.logger.info("Step 2: Filtering for changed datasets...")
    changed = self._filter_changed_datasets(all_ready, db)
    self.logger.info(f"  Found {len(changed)} changed datasets\n")

    if not changed:
      self.logger.info("✓ All datasets are up-to-date")
      return

    # Step 3: Validate paths
    self.logger.info("Step 3: Validating dataset paths...")
    valid, invalid = self._validate_dataset_paths(changed, db)
    self.logger.info(f"  Valid: {len(valid)}, Invalid: {len(invalid)}\n")

    if invalid:
      if not self.config.skip_missing:
        self.logger.error(f"❌ Found {len(invalid)} datasets with missing paths")
        self.logger.error("❌ Aborting upload (use --skip_missing=true to skip invalid datasets)")
        raise FileNotFoundError(f"{len(invalid)} datasets have missing convert_path")
      self.logger.warning(f"⚠️  Skipping {len(invalid)} datasets with missing paths")

    if not valid:
      self.logger.info("✓ No valid datasets to upload")
      return

    # Step 4: Upload in batches
    batch_size = self.config.batch_size
    total_batches = (len(valid) + batch_size - 1) // batch_size
    self.logger.info(f"Step 4: Uploading {len(valid)} datasets in {total_batches} batch(es)...\n")

    for i in range(0, len(valid), batch_size):
      batch = valid[i:i + batch_size]
      batch_num = (i // batch_size) + 1
      self._upload_batch_unified(batch, batch_num, total_batches, db)

    self.logger.info(f"\n{'='*70}")
    self.logger.info("✓ UPLOAD COMPLETE")
    self.logger.info(f"  Total datasets uploaded: {len(valid)}")
    if invalid:
      self.logger.info(f"  Datasets skipped: {len(invalid)}")
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
