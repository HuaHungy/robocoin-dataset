"""Server component for distributed dataloader detection tasks.

This module provides the server-side orchestration for:
- Task distribution to multiple clients
- Hardlink validation before task assignment
- Database updates based on client results
"""

import logging
from pathlib import Path

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB
from robocoin_dataset.dataloader.dataloader_task_management import (
    _gen_one_dataloader_detection_task,
    _mark_task_completed,
    _mark_task_failed,
    _sync_dataloader_detection_tasks,
)
from robocoin_dataset.distribution_computation.constant import (
    DATASET_UUID,
    TASK_FAILED,
    TASK_RESULT_CONTENT,
    TASK_RESULT_STATUS,
)
from robocoin_dataset.distribution_computation.task_server import TaskServer
from robocoin_dataset.format_converter.tolerobot.constant import LEFORMAT_PATH

TASK_CATEGORY = "dataloader_detection"


class DataloaderDbServer(TaskServer):
    """Task distribution server for dataloader detection."""

    def __init__(
        self,
        db_file_path: str | Path,
        summary_logger: logging.Logger,
        host: str = "0.0.0.0",
        port: int = 2100,
        heartbeat_interval: float = 30.0,
        timeout: float = 15.0,
        logger: logging.Logger | None = None,
        episodes: str = "all",
        sample_ratio: float = 0.1,
        batch_size: int = 32,
        num_workers: int = 0,
    ) -> None:
        super().__init__(
            logger=logger,
            host=host,
            port=port,
            heartbeat_interval=heartbeat_interval,
            timeout=timeout,
        )

        if not db_file_path:
            raise ValueError("db_file_path is required and cannot be None or empty")

        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()

        if not self.db_file_path.exists():
            raise FileNotFoundError(f"Database file not found: {self.db_file_path}")
        if not self.db_file_path.is_file():
            raise ValueError(f"Database path is not a file: {self.db_file_path}")

        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)
        self.summary_logger = summary_logger

        # Store detection configuration
        self.episodes = episodes
        self.sample_ratio = sample_ratio
        self.batch_size = batch_size
        self.num_workers = num_workers

    def get_task_category(self) -> str:
        return TASK_CATEGORY

    def generate_task_content(self) -> dict | None:
        # Retry loop: continue until we find a valid task or run out of tasks
        # This ensures that hardlink preparation failures don't stop processing
        max_retries = 100  # Safety limit to prevent infinite loops
        attempt = 0

        while attempt < max_retries:
            attempt += 1

            # Step 1: Sync and claim task (with DB session, includes hardlink validation)
            try:
                with self.db.with_session() as session:
                    # pre-sync queue (only on first attempt to avoid redundant syncs)
                    if attempt == 1:
                        _sync_dataloader_detection_tasks(session, logger=self.logger)

                    # claim one (validates hardlink exists)
                    dataset_uuid, hardlink_path = _gen_one_dataloader_detection_task(session)
                    if dataset_uuid is None:
                        return None

                self.logger.info(f"Using existing hardlink for client: {hardlink_path}")

                # Success! Return the task
                return {
                    DATASET_UUID: dataset_uuid,
                    LEFORMAT_PATH: str(hardlink_path),  # Send hardlink path to client
                    "episodes": self.episodes,
                    "sample_ratio": self.sample_ratio,
                    "batch_size": self.batch_size,
                    "num_workers": self.num_workers,
                }

            except FileNotFoundError as e:
                # Task was already claimed, so we have dataset_uuid
                err_msg = f"Hardlink assertion failed: {e}"
                self.logger.error(f"❌ {dataset_uuid}: {err_msg}")

                # Mark task as failed in database
                with self.db.with_session() as session:
                    _mark_task_failed(session, dataset_uuid, err_msg)

                # Log to summary
                self.summary_logger.info(f"❌ {dataset_uuid}: {err_msg}")

                # Continue to next iteration to try another task
                self.logger.info("Attempting to fetch next task...")
                continue

        # Safety: should never reach here unless we hit max_retries
        self.logger.warning(f"Reached max retry limit ({max_retries}) in generate_task_content")
        return None

    def handle_task_result(self, task_content: dict, task_result_content: dict) -> None:
        """Handle task result from client and update database."""
        dataset_uuid = task_content.get(DATASET_UUID)
        # Client execution state: did the client process crash/throw exception?
        client_execution_status = task_result_content.get(TASK_RESULT_STATUS)

        with self.db.with_session() as session:
            # Check if dataset exists before updating
            item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
            if item is None:
                self.logger.error(f"Dataset {dataset_uuid} not found in dataset DB.")
                return

            # Level 1: Check if client crashed (process-level failure)
            if client_execution_status == TASK_FAILED:
                error_message = task_result_content.get("err_msg", "Client execution failed")
                _mark_task_failed(session, dataset_uuid, error_message)
                self.summary_logger.info(f"❌ {dataset_uuid}: {error_message}")
                self.logger.info(
                    f"Marked {item.convert_path} dataloader detection as FAILED: {error_message}"
                )
                return

            # Level 2: Client executed successfully, check dataset validation result (business-level)
            dataset_validation_result = task_result_content.get(TASK_RESULT_CONTENT, {})
            dataset_validation_passed = dataset_validation_result.get("success", False)

            if dataset_validation_passed:
                _mark_task_completed(session, dataset_uuid)
                # Log to summary
                result = task_result_content.get(TASK_RESULT_CONTENT, {})
                self.summary_logger.info(
                    f"✅ {dataset_uuid}: {result.get('total_frames_sampled', 0)} frames, "
                    f"{result.get('total_time_s', 0):.2f}s, "
                    f"{len(result.get('episodes_tested', []))} episodes, "
                    f"backend={result.get('backend', 'unknown')}"
                )
                self.logger.info(f"Marked {item.convert_path} dataloader detection as COMPLETED")
            else:
                error_message = dataset_validation_result.get("error_summary", "Dataset validation failed")
                _mark_task_failed(session, dataset_uuid, error_message)
                self.summary_logger.info(f"❌ {dataset_uuid}: {error_message}")
                self.logger.info(
                    f"Marked {item.convert_path} dataloader detection as FAILED: {error_message}"
                )


__all__ = [
    "DataloaderDbServer",
    "TASK_CATEGORY",
]
