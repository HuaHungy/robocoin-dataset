"""
RoboCoin Datasets Upload Utilities

This module provides utility classes and functions for uploading datasets to remote hubs.
It contains the business logic for dataset upload operations.
"""

import logging
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy.sql.expression import and_
from tqdm import tqdm

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB, TaskStatus

from .constant import (
  DS_PLATFORM_NAME,
  UPLOAD_DATASET_ADDITIONAL_CHECK_STRUCTURE,
  DatasetsHubEnum,
)
from .hub_upload_task import (
  _gen_one_dataset_upload_task,
  _mark_upload_completed,
  _mark_upload_failed,
  _sync_datasets_upload_status,
)
from .local_datasets_util import LocalDsConfig, LocalDsUtil

######## CONFIGURATION ########


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
      skip_missing (bool): Skip datasets with missing paths instead of aborting. Defaults to False.
      unified_repo_name (str): Name of the unified repository for batch uploads. Defaults to "robocoin-dataset".
  """

  hub_name: DatasetsHubEnum = DatasetsHubEnum.huggingface
  token: str = ""
  namespace: str = ""
  output_path: str = ""
  db_file_path: str = ""
  skip_missing: bool = False
  unified_repo_name: str = "robocoin-dataset"


def load_config_from_yaml(config_path: str | Path) -> dict:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to the YAML configuration file

    Returns:
        Dictionary containing configuration parameters

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is invalid YAML
    """
    config_file = Path(config_path)

    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_file, encoding="utf-8") as f:
        config_dict = yaml.safe_load(f)

    if not config_dict:
        raise ValueError(f"Empty or invalid configuration file: {config_path}")

    return config_dict


def create_upload_config(config_dict: dict) -> LocalDsUploadConfig:
    """
    Create LocalDsUploadConfig from configuration dictionary.

    Args:
        config_dict: Dictionary containing configuration parameters

    Returns:
        LocalDsUploadConfig instance

    Raises:
        ValueError: If required configuration parameters are missing
    """
    # Convert hub_name string to enum if needed
    hub_name = config_dict.get("hub_name", "huggingface")
    if isinstance(hub_name, str):
        try:
            hub_name = DatasetsHubEnum[hub_name.lower()]
        except KeyError:
            raise ValueError(f"Invalid hub_name: {hub_name}. Must be 'huggingface' or 'modelscope'")

    # Create config with all parameters
    return LocalDsUploadConfig(
        root_path=config_dict.get("root_path", ""),
        hub_name=hub_name,
        token=config_dict.get("token", ""),
        namespace=config_dict.get("namespace", ""),
        output_path=config_dict.get("output_path", ""),
        db_file_path=config_dict.get("db_file_path", ""),
        skip_missing=config_dict.get("skip_missing", False),
        unified_repo_name=config_dict.get("unified_repo_name", "robocoin-dataset"),
    )


######## UPLOAD UTILITY CLASS ########


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

    # Determine namespace: use config.namespace if provided,
    # otherwise fall back to DS_PLATFORM_NAME
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

  def _upload_one_dataset(self, hardlink: str, commit_msg: str = "", max_retries: int = 3) -> bool:
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

    repo_name = hardlink.removesuffix("_hardlink")
    # Remove "_hardlink" suffix from ds_name for clean repository name
    try:
      self.check_dataset_dir_valid(
        ds_name=hardlink, additional_check_list=UPLOAD_DATASET_ADDITIONAL_CHECK_STRUCTURE
      )
    except Exception as e:
      self.logger.debug(f"{repo_name}: {e}")
      return False

    hardlink_path = self.root_path.joinpath(hardlink)
    if not hardlink_path.exists():
      raise FileNotFoundError(f"dataset path {hardlink_path} does not exist")

    upload_path = hardlink_path
    self.logger.debug(f"{repo_name}: Using {upload_path}")

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
          self.logger.debug(f"{repo_name}: Creating repo {repo_id}")
          self.hub.create_repo(repo_id=repo_id)

        # Step 3: Upload files using hub's upload_repo method
        commit_url = self.hub.upload_repo(
          folder_path=upload_path,
          repo_id=repo_id,
          commit_msg=commit_msg
        )

        self.logger.debug(f"{repo_name}: {commit_url}")
        return True

      except Exception as e:  # noqa: PERF203
        if attempt < max_retries:
          # Random delay before retry
          delay = random.uniform(2, 10)
          self.logger.debug(f"{repo_name}: Retry {attempt}/{max_retries} in {delay:.1f}s: {e}")
          # Countdown display
          for remaining in range(int(delay), 0, -1):
            print(f"\r  ⏳ {remaining}s...   ", end="", flush=True)
            time.sleep(1)
          # Sleep remaining fractional seconds
          time.sleep(delay - int(delay))
          print("\r" + " " * 20 + "\r", end="", flush=True)  # Clear the countdown line
        else:
          self.logger.debug(f"{repo_name}: Failed after {max_retries} attempts: {e}")
          return False

    return False

  def _validate_and_resolve_db_path(self) -> Path:
    """
    Validate and resolve the database file path from config and CLI arguments.
    Automatically reads from YAML config if not explicitly provided.

    Returns:
        Path: Resolved and validated database path.
    """
    # Handle "default" keyword or empty to read from YAML config
    if self.config.db_file_path.lower() in ["default", "", "null", "none"]:
      config_file = None
      for i, arg in enumerate(sys.argv):
        if arg in ["--config", "-c"] and i + 1 < len(sys.argv):
          config_file = sys.argv[i + 1]
          break

      if config_file and Path(config_file).exists():
        with open(config_file) as f:
          yaml_config = yaml.safe_load(f)
          yaml_db_path = yaml_config.get('db_file_path', '')
          if yaml_db_path and yaml_db_path.lower() not in ["null", "none", ""]:
            self.config.db_file_path = yaml_db_path
            self.logger.debug(f"Using db_file_path from config: {yaml_db_path}")
          else:
            self.logger.error(f"❌ No db_file_path in {config_file}")
            raise ValueError("db_file_path not found in config")
      else:
        self.logger.error("❌ No config file found")
        raise FileNotFoundError("Config file required")

    # Validate path exists on filesystem
    db_path = Path(self.config.db_file_path).expanduser().absolute()
    if not db_path.exists():
      self.logger.error(f"❌ Database file not found: {db_path}")
      raise FileNotFoundError(f"Database file not found: {db_path}")

    return db_path

  def upload_datasets_from_db(self) -> None:
    """
    Upload datasets from database one-by-one.
    """
    # Validate and resolve database path
    db_path = self._validate_and_resolve_db_path()

    # Print initial configuration
    self.logger.info(f"🚀 Upload: {self.config.hub_name.value}/{self.namespace}")

    # Connect to database and store it as instance attribute for helper methods
    self.db = DatasetDatabase(db_path)

    # Store original root_path to restore later
    original_root_path = self.root_path

    # Process datasets with progress bar
    uploaded_count = 0
    failed_count = 0
    skipped_count = 0

    # Create progress bar (will be updated after first sync)
    pbar = tqdm(
      desc="📤 Uploading",
      unit="ds",
      bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]"
    )

    try:
      while True:
        # Sync datasets upload status from database
        _sync_datasets_upload_status(self.db, self.config.hub_name, self.logger, retry_failed=False)

        # Count remaining datasets to upload
        from .hub_upload_task import _get_hub_field_prefix
        upload_status_field = _get_hub_field_prefix(self.config.hub_name, DatasetDB, "upload_status")
        upload_status_col = getattr(DatasetDB, upload_status_field)
        with self.db.with_session() as session:
          pending_count = session.query(DatasetDB).filter(
            and_(
              DatasetDB.visualize_check_status == TaskStatus.COMPLETED,
              upload_status_col == TaskStatus.PENDING,
            )
          ).count()

        if pending_count == 0:
          break

        # Update progress bar total if needed
        if pbar.total is None or pbar.total != pending_count + uploaded_count + failed_count + skipped_count:
          pbar.total = pending_count + uploaded_count + failed_count + skipped_count

        # Get next dataset to upload from database (with validation)
        try:
          dataset_uuid, hardlink_path = _gen_one_dataset_upload_task(
            self.db, self.config.hub_name, self.logger, self.config.skip_missing
          )
        except FileNotFoundError:
          # Error was raised and not skipped
          pbar.close()
          raise

        if dataset_uuid is None or hardlink_path is None:
          # No more tasks
          break

        # Get dataset name for logging
        dataset_name = hardlink_path.name.removesuffix("_hardlink")
        pbar.set_description(f"📤 {dataset_name[:30]:30s}")

        # Check repo conflict
        repo_name = hardlink_path.name.removesuffix("_hardlink")
        repo_id = f"{self.namespace}/{repo_name}"
        if not self._check_repo_conflict(repo_id):
          self.logger.debug(f"{dataset_name}: Skipped (user cancelled)")
          _mark_upload_failed(self.db, dataset_uuid, "User cancelled", self.config.hub_name, self.logger)
          skipped_count += 1
          pbar.update(1)
          continue

        # Upload dataset with temporary root_path change
        success = self._upload_one_dataset_in_changed_root(hardlink_path, original_root_path)

        # Handle result
        if success:
          _mark_upload_completed(self.db, dataset_uuid, self.config.hub_name, self.logger)
          uploaded_count += 1
          self.logger.debug(f"{dataset_name}: Uploaded")
        else:
          _mark_upload_failed(self.db, dataset_uuid, "Upload failed", self.config.hub_name, self.logger)
          failed_count += 1
          self.logger.debug(f"{dataset_name}: Failed")

        pbar.update(1)

    finally:
      # Ensure root_path is restored and progress bar is closed
      self.root_path = original_root_path
      pbar.close()

    # Final summary
    total_processed = uploaded_count + failed_count + skipped_count
    if total_processed == 0:
      self.logger.info("No datasets to upload")
      return

    status = f"✅ {uploaded_count}/{total_processed}"
    if failed_count > 0:
      status += f" | ❌ {failed_count}"
    if skipped_count > 0:
      status += f" | ⏭️  {skipped_count}"
    self.logger.info(status)

  def _upload_one_dataset_in_changed_root(self, hardlink_path: Path, original_root_path: Path) -> bool:
    """
    Upload a dataset with temporarily changed root_path.

    Args:
        hardlink_path: Path to the hardlink directory
        original_root_path: Original root_path to restore after upload

    Returns:
        True if upload succeeded, False otherwise
    """
    try:
      # Temporarily change root_path to hardlink's parent
      self.root_path = hardlink_path.parent

      # Execute upload
      return self._upload_one_dataset(hardlink=hardlink_path.name)

    finally:
      # Always restore original root_path
      self.root_path = original_root_path

  def _check_repo_conflict(self, repo_id: str) -> bool:
    """
    Check if repository exists and prompt user for confirmation.

    Args:
        repo_id: Repository identifier.

    Returns:
        True if user confirms to proceed, False otherwise.
    """
    self.logger.debug(f"Checking repo: {repo_id}")
    repo_exists = self.hub.repo_exists(repo_id=repo_id)
    self.logger.debug(f"Exists: {repo_exists}")

    if not repo_exists:
      return True

    # Use tqdm.write to avoid breaking progress bar if it exists
    tqdm.write(f"\n⚠️  {repo_id} exists. Overwrite? (y/n): ", end="")
    response = input().strip().lower()
    return response in ["y", "yes"]


######## HIGH-LEVEL ORCHESTRATION ########


def upload_datasets(config: LocalDsUploadConfig, logger: logging.Logger | None = None) -> None:
    """
    Upload datasets to remote hub using database management.

    This is the main business logic function that orchestrates the upload process.

    Args:
        config: Upload configuration
        logger: Logger instance (optional)
    """
    _logger = logger or logging.getLogger(__name__)

    try:
        # Initialize uploader
        _logger.info("Initializing uploader...")
        uploader = LocalDsUploadUtil(config)

        # Start upload process
        _logger.info("Starting upload process...")
        uploader.upload_datasets_from_db()

        _logger.info("✅ Upload process completed successfully")

    except KeyboardInterrupt:
        _logger.warning("\n⚠️  Upload interrupted by user")
        raise
    except Exception as e:
        _logger.error(f"❌ Upload failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
  pass
