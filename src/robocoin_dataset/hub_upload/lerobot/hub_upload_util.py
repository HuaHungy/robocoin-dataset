"""
RoboCoin Datasets Uploader
usage:
python -m robocoin.datasets.upload --config configs/upload.yaml
"""

import random
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.sql.expression import and_, or_
from tqdm import tqdm

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB, DatasetHardLinkDB, TaskStatus

from .constant import (
  DS_PLATFORM_NAME,
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

  def _upload_dataset(self, hardlink: str, commit_msg: str = "", max_retries: int = 3) -> bool:
    """
    Upload a single dataset to the remote hub according to the hardlink.
    local function without db.

    Args:
        hardlink (str): Name of the hardlink folder to upload.
        point to the actural dataset folder.
        commit_msg (str): Commit message for the upload. Defaults to auto-generated message.
        max_retries (int): Maximum number of retry attempts. Defaults to 3.

    Returns:
        bool: if seccessful.
    """
    # Remove "_hardlink" suffix from ds_name for clean repository name
    repo_name = hardlink.removesuffix("_hardlink")

    log_prefix = f"dataset {repo_name}:"
    try:
      self.check_dataset_dir_valid(
        ds_name=hardlink, additional_check_list=UPLOAD_DATASET_ADDITIONAL_CHECK_STRUCTURE
      )
    except Exception as e:
      self.logger.error(f"{log_prefix} {e}")
      return False

    hardlink_path = self.root_path.joinpath(hardlink)
    if not hardlink_path.exists():
      raise FileNotFoundError(f"dataset path {hardlink_path} does not exist")

    # Ensure ds_name ends with "_hardlink"
    if not hardlink.endswith("_hardlink"):
      raise ValueError(f"{log_prefix} Dataset name must end with '_hardlink', got: {hardlink}")

    upload_path = hardlink_path
    self.logger.info(f"{log_prefix} Using hardlink folder: {upload_path}")

    # Repository ID uses clean name (without _hardlink suffix)
    repo_id = f"{self.namespace}/{repo_name}"

    # Generate commit message if not provided
    if not commit_msg:
      commit_msg = f"Upload dataset {repo_name}"

    # Retry logic with random delays
    for attempt in range(1, max_retries + 1):
      try:  # noqa: PERF203 - retry logic requires try-except in loop
        # Step 1: Check if repo exists
        repo_exists = self.hub.repo_exists(repo_id=repo_id)

        # Step 2: Create repo if it doesn't exist
        if not repo_exists:
          self.logger.info(
            f"{log_prefix} repo {repo_id} does not exists in {self.config.hub_name}, creating repo {repo_id}"
          )
          self.hub.create_repo(repo_id=repo_id)

        # Step 3: Upload files using hub's upload_repo method
        commit_url = self.hub.upload_repo(
          folder_path=upload_path,
          repo_id=repo_id,
          commit_msg=commit_msg
        )

        self.logger.info(f"{log_prefix} Upload successful. Commit: {commit_url}")
        return True

      except Exception as e:  # noqa: PERF203
        if attempt < max_retries:
          # Random delay between 5-15 seconds before retry
          delay = random.uniform(5, 15)
          self.logger.warning(
            f"{log_prefix} Upload interrupted (attempt {attempt}/{max_retries}): {e}. "
            f"Retrying in {delay:.1f} seconds..."
          )
          time.sleep(delay)
        else:
          self.logger.error(f"{log_prefix} Failed after {max_retries} attempts: {e}")
          return False

    return False

  def upload_datasets_from_db(self) -> None:
    """
    Upload datasets from database in batches.
    """
    # if db input
    if not self.config.db_file_path:
      self.logger.error("❌ db_file_path is not configured")
      raise ValueError("db_file_path must be specified in config or via --db_file_path")
    # if db exist
    db_path = Path(self.config.db_file_path).expanduser().absolute()
    if not db_path.exists():
      self.logger.error(f"❌ Database file not found: {db_path}")
      raise FileNotFoundError(f"Database file not found: {db_path}")

    # Print initial configuration
    self.logger.info(f"🚀 Starting upload: {self.config.hub_name.value}/{self.namespace} (DB: {db_path.name})")

    # Connect to database and store it as instance attribute for helper methods
    self.db = DatasetDatabase(db_path)

    # Step 1: Sync datasets upload status from database
    self.logger.info("📋 Syncing upload status from database...")
    self._sync_datasets_upload_status(self.db, retry_failed=False)

    # Count total datasets to upload
    upload_status_field = self._get_hub_field_prefix("upload_status")
    upload_status_col = getattr(DatasetDB, upload_status_field)
    with self.db.with_session() as session:
      total_count = session.query(DatasetDB).filter(
        and_(
          DatasetDB.visualize_check_status == TaskStatus.COMPLETED,
          upload_status_col == TaskStatus.PENDING,
        )
      ).count()

    if total_count == 0:
      self.logger.info("✓ No datasets to upload\n")
      return

    self.logger.info(f"✓ Found {total_count} dataset(s) to upload\n")

    # Step 2: Process datasets with progress bar
    uploaded_count = 0
    failed_count = 0
    skipped_count = 0

    # Store original root_path to restore later
    original_root_path = self.root_path

    # Create progress bar
    pbar = tqdm(
      total=total_count,
      desc="📤 Uploading datasets",
      unit="dataset",
      bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]"
    )

    try:
      while True:
        # Get next dataset to upload from database
        dataset_uuid, upload_path = self._gen_one_dataset_upload_task()
        if dataset_uuid is None:
          break

        # Query the dataset from database to get additional info
        with self.db.with_session() as session:
          item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
          if not item:
            self.logger.error(f"❌ Dataset {dataset_uuid} not found in database")
            pbar.update(1)
            continue

        dataset_name = item.dataset_name
        pbar.set_description(f"📤 {dataset_name[:40]:40s}")

        # Prepare hardlink (validates convert_path, queries DB, creates if needed, updates DB)
        from robocoin_dataset.hardlink.prepare_hardlink import prepare_hardlink_db

        convert_path = Path(item.convert_path).expanduser().absolute()

        try:
          with self.db.with_session() as session:
            hardlink_path = prepare_hardlink_db(
              source_path=convert_path,
              dataset_uuid=dataset_uuid,
              target_dir=None,
              db_session=session,
            )
        except Exception as e:
          error_msg = f"Failed to prepare hardlink: {e}"
          pbar.write(f"  ❌ {dataset_name}: {error_msg}")
          self._mark_upload_failed(dataset_uuid, error_msg, self.db)
          failed_count += 1
          pbar.update(1)
          if not self.config.skip_missing:
            pbar.close()
            self.logger.error("❌ Aborting upload (use --skip_missing=true to skip invalid datasets)")
            raise
          skipped_count += 1
          continue

        # Check repo conflict before uploading
        # Derive repo name from hardlink name (same as _upload_dataset does)
        repo_name = hardlink_path.name.removesuffix("_hardlink")
        repo_id = f"{self.namespace}/{repo_name}"
        if not self._check_repo_conflict(repo_id):
          pbar.write(f"  ⚠️  {dataset_name}: Skipped (user cancelled)")
          self._mark_upload_failed(item.dataset_uuid, "User cancelled upload due to repo conflict", self.db)
          skipped_count += 1
          pbar.update(1)
          continue

        # Upload the dataset by temporarily setting root_path to hardlink's parent
        try:
          # Temporarily set root_path to the parent of the hardlink directory
          # In order to bypass the definition of the parent type in LocalDsUtil.
          self.root_path = hardlink_path.parent

          # Upload from the already-validated hardlink folder
          # Pass the actual hardlink folder name (with _hardlink suffix)
          # _upload_dataset will automatically strip _hardlink for repo_id
          success = self._upload_dataset(
            hardlink=hardlink_path.name  # e.g., "realman_rmc_aidal_only_test_fix_hardlink"
          )

          if success:
            self._mark_upload_completed(item.dataset_uuid, self.db)
            uploaded_count += 1
            pbar.write(f"  ✓ {dataset_name}: Uploaded successfully")
          else:
            self._mark_upload_failed(item.dataset_uuid, "Upload failed", self.db)
            failed_count += 1
            pbar.write(f"  ❌ {dataset_name}: Upload failed")

        except Exception as e:
          error_msg = str(e)
          pbar.write(f"  ❌ {dataset_name}: {error_msg}")
          self._mark_upload_failed(item.dataset_uuid, error_msg, self.db)
          failed_count += 1

        finally:
          # Restore original root_path after each upload
          self.root_path = original_root_path
          pbar.update(1)

    finally:
      # Ensure root_path is restored
      self.root_path = original_root_path
      pbar.close()

    # Final summary
    summary_parts = [f"✅ Upload complete: {uploaded_count}/{total_count} successful"]
    if failed_count > 0:
      summary_parts.append(f"{failed_count} failed")
    if skipped_count > 0:
      summary_parts.append(f"{skipped_count} skipped")
    self.logger.info(", ".join(summary_parts))

  def _sync_datasets_upload_status(self, db: DatasetDatabase, retry_failed: bool = False) -> None:
    """
    Sync datasets upload status from database.
    Set PENDING and increment the version,
    sync the version_ps -> visualize_check_status.

    Args:
        db: Database instance.
        retry_failed: If True, retry failed uploads. Otherwise only process pending ones.
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
              upload_version_ps_col < DatasetDB.visualize_check_version,
            ),
          ),
        )
      )

      for item in query.all():
        setattr(item, upload_status_field, TaskStatus.PENDING)
        current_version = getattr(item, upload_version_field, 0) or 0
        setattr(item, upload_version_field, current_version + 1)
        setattr(item, upload_version_ps_field, item.visualize_check_version)
      session.commit()

  def _gen_one_dataset_upload_task(self) -> tuple[str | None, str | None]:
      """
      Generate one dataset upload task by finding a pending upload and marking it as PROCESSING.

      Returns:
          Tuple of (dataset_uuid, hardlink_path) if a task was found, (None, None) otherwise.
          hardlink_path is queried from the dataset_hard_link table.
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

          # Query hardlink_path from dataset_hard_link table
          hardlink_item = session.query(DatasetHardLinkDB).filter(
              DatasetHardLinkDB.dataset_uuid == item.dataset_uuid
          ).first()

          hardlink_path = hardlink_item.hard_link_path if hardlink_item else None

          return item.dataset_uuid, hardlink_path

  def _mark_upload_failed(self, dataset_uuid: str, error_msg: str, db: DatasetDatabase) -> None:

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
    self.logger.debug(f"Checking if repo exists: {repo_id}")
    repo_exists = self.hub.repo_exists(repo_id=repo_id)
    self.logger.debug(f"Repo exists result: {repo_exists}")

    if not repo_exists:
      return True

    # Use tqdm.write to avoid breaking progress bar if it exists
    tqdm.write(f"\n⚠️  Repository {repo_id} exists. Upload will overwrite existing files.")
    response = input("Proceed? (y/n): ").strip().lower()
    return response in ["y", "yes"]


if __name__ == "__main__":
  pass
