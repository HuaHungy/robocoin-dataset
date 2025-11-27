"""
RoboCoin Datasets Upload Utilities

This module provides utility classes and functions for uploading datasets to remote hubs.
It contains the business logic for dataset upload operations.
"""

import random
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

import yaml
from tqdm import tqdm

from robocoin_dataset.hub_upload.gen_file.gen_info import gen_info
from robocoin_dataset.hub_upload.gen_file.gen_readme import gen_readme
from robocoin_dataset.prepare_metadata.metadata_collect import create_unified_metadata
from robocoin_dataset.prepare_metadata.unified_metadata_def import UnifiedMetadata

from .constant import (
    DatasetsHubEnum,
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
        namespace (str): Username/namespace on the target hub platform.
        output_path (str): Path to the output directory for commit history files. Defaults to empty string.
        db_file_path (str): Path to the database file for dataset tracking. Defaults to empty string.
        skip_missing (bool): Skip datasets with missing paths instead of aborting.
        force_overwrite (bool): Force overwrite existing repositories without prompting. Defaults to False.
    """

    hub_name: DatasetsHubEnum = DatasetsHubEnum.huggingface
    token: str = ""
    namespace: str = ""
    output_path: str = ""
    db_file_path: str = ""
    skip_missing: bool = True
    force_overwrite: bool = False


def load_config_from_yaml(config_path: str | Path) -> dict:
    """
    Load configuration from YAML file.

    Returns:
        Dictionary containing configuration parameters
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

    return LocalDsUploadConfig(
        root_path=config_dict.get("root_path") or None,
        hub_name=hub_name,
        token=config_dict.get("token", ""),
        namespace=config_dict.get("namespace", ""),
        output_path=config_dict.get("output_path", ""),
        db_file_path=config_dict.get("db_file_path", ""),
        skip_missing=config_dict.get("skip_missing", True),
        force_overwrite=config_dict.get("force_overwrite", False),
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
        self.namespace = config.namespace
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


    def _do_upload(
        self, hardlink_path: Path, commit_msg: str = "", max_retries: int = 3
    ) -> tuple[bool, str]:
        """
        Upload a single dataset to the remote hub.
        local function without db: just upload the dataset to the remote hub.

        Args:
            hardlink_path (Path): Path to the hardlink folder to upload.
            commit_msg (str): Commit message for the upload. Defaults to auto-generated message.
            max_retries (int): Maximum number of retry attempts. Defaults to 3.
        Returns: tuple[bool, str]: (success status, error message if failed)
        """

        # Extract dataset name from hardlink path
        dataset_name = hardlink_path.name.removesuffix("_qced_hardlink").removesuffix("_hardlink")

        # Validate dataset structure using shared validation from LocalDsUtil
        # TODO: we no longer use root_path but keep it for compatibility.
        # here we just skip the validation of the dataset structure.
        # ORI code:
        # try:
        #     self.check_dataset_dir_valid(
        #         ds_name=hardlink_path.name,
        #         additional_check_list=[README_FILE],  # Upload requires README.md
        #     )
        # except Exception as e:
        #     tb = traceback.format_exc()
        #     error_msg = f"Validation failed: {e}\n\nFull traceback:\n{tb}"
        #     self.logger.debug(f"{dataset_name}: {error_msg}")
        #     return False, error_msg
        # if not hardlink_path.exists():
        #     raise FileNotFoundError(f"dataset path {hardlink_path} does not exist")

        upload_path = hardlink_path
        self.logger.debug(f"{dataset_name}: Using {upload_path}")

        # Repository ID uses clean name (without _hardlink suffix)
        repo_id = f"{self.namespace}/{dataset_name}"

        # Generate commit message if not provided
        if not commit_msg:
            commit_msg = f"Upload dataset {dataset_name}"

        # Retry logic with random delays
        for attempt in range(1, max_retries + 1):
            try:  # noqa: PERF203 - retry logic requires try-except in loop
                if not self.hub.repo_exists(repo_id=repo_id):
                    self.logger.debug(f"{dataset_name}: repo not exists, creating repo {repo_id}")
                    self.hub.create_repo(repo_id=repo_id)

                ### UPLOAD: CALL API ###
                commit_url = self.hub.upload_repo(
                    folder_path=upload_path,
                    repo_id=repo_id,
                    commit_msg=commit_msg,
                    logger=self.logger,
                )

                self.logger.debug(f"{dataset_name}: {commit_url}")
                return True, ""

            except Exception as e:  # noqa: PERF203
                if attempt < max_retries:
                    # Random delay before retry
                    delay = random.uniform(2, 10)
                    self.logger.debug(
                        f"{dataset_name}: Retry {attempt}/{max_retries} in {delay:.1f}s: {e}"
                    )
                    # Countdown display
                    for remaining in range(int(delay), 0, -1):
                        print(f"\r  ⏳ {remaining}s...   ", end="", flush=True)
                        time.sleep(1)
                    # Sleep remaining fractional seconds
                    time.sleep(delay - int(delay))
                    print("\r" + " " * 20 + "\r", end="", flush=True)  # Clear the countdown line
                else:
                    tb = traceback.format_exc()
                    error_msg = f"Failed after {max_retries} attempts: {e}\n\nFull traceback:\n{tb}"
                    self.logger.debug(f"{dataset_name}: {error_msg}")
                    return False, error_msg

        return False, "Upload failed with unknown error"

    def _upload_one_dataset(self, hardlink_path: Path) -> tuple[bool, str]:
        """
        Upload a dataset to the hub with YAML and README generation.
        is an enhanced version of _upload_one_dataset in LocalDsUtil.

        Args:
            hardlink_path: Path to the hardlink directory

        Returns:
            tuple[bool, str]: (success status, error message if failed or empty string if success)
        """
        # Start timing for this dataset
        dataset_start_time = time.time()

        dataset_name = hardlink_path.name.removesuffix("_qced_hardlink").removesuffix("_hardlink")

        # Define output path for intermediate YAML file
        output_path = Path(self.config.output_path or "./dataset_info").expanduser().absolute()
        output_path.mkdir(parents=True, exist_ok=True)

        # Step 2: Build aggregated metadata from database + local files
        tqdm.write("    🧩 Collecting unified metadata...")
        self.logger.info(f"{dataset_name}: Collecting unified metadata...")
        try:
            if not self.config.db_file_path:
                raise ValueError("db_file_path is required for unified metadata collection")
            metadata = create_unified_metadata(
                hardlink_path=hardlink_path,
                db_file_path=self.config.db_file_path,
                dataset_uuid=None,
            )
        except Exception as e:  # noqa: PERF203
            tb = traceback.format_exc()
            error_msg = f"Unified metadata collection failed: {e}\n\nFull traceback:\n{tb}"
            tqdm.write(f"      ❌ Unified metadata collection failed: {e}")
            self.logger.error(f"{dataset_name}: {error_msg}")
            return False, error_msg

        # Step 3: Generate README file for this dataset using unified metadata
        tqdm.write("    📝 Generating README from unified metadata...")
        self.logger.info(f"{dataset_name}: Generating README from unified metadata...")
        readme_success, readme_error = self._generate_readme_for_dataset(
            hardlink_path,
            output_path,
            metadata,
        )
        if not readme_success:
            return False, readme_error

        # Step 4: Execute upload
        tqdm.write("    ⬆️  Uploading to hub (this may take several minutes for large datasets)...")
        self.logger.info(f"{dataset_name}: Uploading to hub...")
        result = self._do_upload(hardlink_path)

        # Calculate elapsed time for this dataset
        dataset_elapsed = time.time() - dataset_start_time

        if result[0]:  # success
            tqdm.write(f"    ✅ Upload completed successfully! (took {dataset_elapsed:.1f}s)")
            self.logger.info(f"{dataset_name}: Upload completed in {dataset_elapsed:.2f}s")
        else:
            self.logger.info(f"{dataset_name}: Upload failed after {dataset_elapsed:.2f}s")

        return result

    def _generate_yaml_for_dataset(
        self,
        hardlink_path: Path,
        output_path: Path,
    ) -> tuple[bool, str]:
        return gen_info(hardlink_path, output_path, self.logger)

    def _generate_readme_for_dataset(
        self,
        hardlink_path: Path,
        dataset_info_root_path: Path,
        metadata: UnifiedMetadata,
    ) -> tuple[bool, str]:
        return gen_readme(hardlink_path, dataset_info_root_path, self.logger, metadata=metadata)

    # def _check_repo_conflict(self, repo_id: str, timeout: float = 5.0) -> bool:
    #     """
    #     Check if repository exists and prompt user for confirmation.

    #     Args:
    #         repo_id: Repository identifier.
    #         timeout: Timeout in seconds for user input (default: 5.0)

    #     Returns:
    #         True if user confirms to proceed, False otherwise.
    #     """
    #     self.logger.debug(f"Checking repo: {repo_id}")
    #     repo_exists = self.hub.repo_exists(repo_id=repo_id)
    #     self.logger.debug(f"Exists: {repo_exists}")

    #     if not repo_exists:
    #         return True

    #     # Repo exists - check force_overwrite flag
    #     if self.config.force_overwrite:
    #         self.logger.debug(f"{repo_id}: Force overwrite enabled")
    #         return True

    #     # Prompt user for confirmation with timeout
    #     tqdm.write("")  # Blank line for spacing
    #     tqdm.write(f"⚠️  Repository already exists: {repo_id}")
    #     tqdm.write(f"   Overwrite? (y/n) [default: y in {timeout}s]: ", end="")
    #     sys.stdout.flush()

    #     # Use select for timeout input
    #     try:
    #         # Check if stdin has input ready within timeout
    #         ready, _, _ = select.select([sys.stdin], [], [], timeout)

    #         if ready:
    #             # Input available
    #             response = sys.stdin.readline().strip().lower()
    #             if response in ["y", "yes", ""]:
    #                 return True
    #             if response in ["n", "no"]:
    #                 return False
    #             tqdm.write("   Invalid input, defaulting to 'yes'")
    #             return True
    #         # Timeout - default to yes
    #         tqdm.write("   (timeout - defaulting to 'yes')")
    #         return True

    #     except (OSError, ValueError):
    #         # select not supported (e.g., Windows) or other issues
    #         # Fall back to regular input
    #         try:
    #             response = input().strip().lower()
    #             return response in ["y", "yes", ""]
    #         except (EOFError, KeyboardInterrupt):
    #             # No input or Ctrl+C - default to no
    #             return False


if __name__ == "__main__":
    pass
