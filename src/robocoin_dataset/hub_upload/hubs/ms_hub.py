import logging
import warnings
from pathlib import Path

from modelscope.hub.api import HubApi  # noqa: E402

from robocoin_dataset.hub_upload.constant import (  # noqa: E402
    DEFAULT_UPLOAD_ALLOW_PATTERNS,
    DEFAULT_UPLOAD_IGNORE_PATTERNS,
    MODELSCOPE_BUG_EXCEPTON_MSG,
)

from .abstract_hub import (  # noqa: E402
    AbstractUploadHub,
)
from .batch_upload import BatchUploadMixin  # noqa: E402

warnings.filterwarnings("ignore", message="pkg_resources is deprecated as an API")


class ModelscopeUploadHub(AbstractUploadHub, BatchUploadMixin):
    """
    Implementation of AbstractUploadHub for ModelScope dataset uploads.

    This class provides functionality to upload datasets to ModelScope Hub,
    including repository creation and file uploading with commit messages.
    Handles a known bug in ModelScope API by catching specific exception messages.

    Attributes:
        hub (HubApi): ModelScope API client instance.
    """

    from modelscope.hub.api import HubApi

    def __init__(self, token: str) -> None:
        """
        Initialize the ModelScope upload hub with authentication token.

        Args:
            token (str): Authentication token for ModelScope API.
        """
        super().__init__(token)
        self.hub = HubApi()

    def repo_exists(self, repo_id: str) -> bool:
        """
        Check if a dataset repository exists on ModelScope Hub.

        Args:
            repo_id (str): Identifier of the repository to check.

        Returns:
            bool: True if repository exists, False otherwise.
        """
        try:
            return self.hub.repo_exists(repo_id=repo_id, token=self.token, repo_type="dataset")
        except Exception as e:
            print(f"⚠️  Warning: Could not check if repo {repo_id} exists: {e}")
            return False

    def create_repo(self, repo_id: str) -> None:
        """
        Create a new dataset repository on ModelScope Hub.

        If the repository already exists, this method does nothing due to exist_ok=True.

        Args:
            repo_id (str): Identifier for the new repository.
        """
        if not self.repo_exists(repo_id=repo_id):
            self.hub.create_repo(
                repo_id=repo_id,
                token=self.token,
                repo_type="dataset",
                exist_ok=True,
            )

    def upload_repo(self, folder_path: Path, repo_id: str, commit_msg: str) -> str:
        """
        Upload a local folder to a ModelScope dataset repository.

        Uses batched upload to split large folders into manageable chunks for reliability.

        Args:
            folder_path (Path): Path to the local folder to upload.
            repo_id (str): Identifier of the target repository.
            commit_msg (str): Commit message for the upload.

        Returns:
            str: URL of the commit on ModelScope Hub, or success message if known bug occurs.

        Raises:
            Exception: If upload fails for any reason other than the known ModelScope bug.
        """
        return self.upload_repo_batched(
            folder_path=folder_path,
            repo_id=repo_id,
            commit_msg=commit_msg,
        )

    def upload_repo_batched(self, folder_path: Path, repo_id: str, commit_msg: str) -> str:
        """
        Upload a folder in batches for better reliability with large datasets.

        Splits files into batches of 500MB or 1000 files (whichever comes first),
        then uploads each batch separately.

        Args:
            folder_path: Path to folder to upload
            repo_id: Repository identifier
            commit_msg: Base commit message

        Returns:
            Success message or URL of the final commit
        """
        logger = logging.getLogger(__name__)

        # Get all files to upload
        files = self.get_files_to_upload(
            folder_path,
            DEFAULT_UPLOAD_ALLOW_PATTERNS,
            DEFAULT_UPLOAD_IGNORE_PATTERNS
        )

        # Split into batches (500MB or 1000 files per batch)
        batches = self.split_into_batches(files, max_batch_size_mb=500, max_files_per_batch=1000)

        # Upload each batch
        final_result = ""
        for i, batch in enumerate(batches, 1):
            file_count, total_size = self.calculate_batch_stats(batch)
            logger.info(
                f"Uploading batch {i}/{len(batches)}: "
                f"{file_count} files, {self.format_size(total_size)}"
            )

            batch_commit_msg = f"{commit_msg} (batch {i}/{len(batches)})"

            try:
                for file_path in batch:
                    path_in_repo = str(file_path.relative_to(folder_path))
                    self.hub.upload_file(
                        path_or_fileobj=str(file_path),
                        path_in_repo=path_in_repo,
                        repo_id=repo_id,
                        repo_type="dataset",
                        token=self.token,
                        commit_message=batch_commit_msg,
                    )

                logger.info(f"✓ Batch {i}/{len(batches)} completed")

            except Exception as e:
                if str(e) == MODELSCOPE_BUG_EXCEPTON_MSG:
                    final_result = f"Exception captured when Modelscope upload dataset {repo_id}, but the repo has been uploaded successfully."
                else:
                    raise e

        logger.info(f"✅ All {len(batches)} batches uploaded successfully")
        return final_result if final_result else f"Uploaded {len(batches)} batches successfully"
