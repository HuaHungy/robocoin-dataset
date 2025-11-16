"""Server component for distributed dataloader detection tasks.

This module provides the server-side orchestration for:
- Task distribution to multiple clients
- Hardlink validation before task assignment
- Database updates based on client results
"""

import logging
import traceback
from pathlib import Path

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB
from robocoin_dataset.dataloader.dataloader_task import (
    _gen_one_dataloader_detection_task,
    _mark_task_completed,
    _mark_task_failed,
    _sync_dataloader_detection_tasks,
)
from robocoin_dataset.distribution_computation.constant import DATASET_UUID
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

        # Track aggregated statistics
        self.total_frames_processed = 0
        self.total_detection_time = 0.0
        self.datasets_succeeded = 0
        self.datasets_failed = 0

    def get_task_category(self) -> str:
        return TASK_CATEGORY

    def generate_task_content(self) -> dict | None:
        while True:
            dataset_uuid = None  # Initialize to avoid NameError in exception handlers

            # Step 1: Sync and claim task (with DB session, includes hardlink validation)
            try:
                with self.db.with_session() as session:
                    # Always resync the queue before attempting to claim a task
                    _sync_dataloader_detection_tasks(session, logger=self.logger)

                    # claim one (validates hardlink exists)
                    dataset_uuid, hardlink_path = _gen_one_dataloader_detection_task(session)
                    if dataset_uuid is None:
                        break

                if hardlink_path is None:
                    raise FileNotFoundError(f"No hard_link_path found for dataset {dataset_uuid}")

                if not hardlink_path.exists():
                    raise FileNotFoundError(f"No such hardlink found in {hardlink_path}")

                self.logger.debug(f"Using existing hardlink for client: {hardlink_path}")

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
                # Task was claimed before validation, so dataset_uuid is always set
                err_msg = f"Hardlink assertion failed: {e}\n{traceback.format_exc()}"
                self.logger.exception(f"❌ {dataset_uuid}: {err_msg}")
                # Mark task as failed in database
                with self.db.with_session() as session:
                    _mark_task_failed(session, dataset_uuid, err_msg)
                # Log to summary
                self.summary_logger.debug(f"❌ {dataset_uuid}: {err_msg}")
                self.datasets_failed += 1
                # Continue to next iteration to try another task
                self.logger.debug("Attempting to fetch next task...")
                continue
            except Exception as e:
                # Catch any unexpected exceptions during task generation/claiming
                if dataset_uuid:
                    err_msg = f"Unexpected error during task generation: {e}\n{traceback.format_exc()}"
                    self.logger.exception(f"❌ {dataset_uuid}: {err_msg}")
                    with self.db.with_session() as session:
                        _mark_task_failed(session, dataset_uuid, err_msg)
                    self.summary_logger.debug(f"❌ {dataset_uuid}: {err_msg}")
                    self.datasets_failed += 1
                else:
                    self.logger.exception(f"❌ Unexpected error before task claimed: {e}")
                # Continue to next iteration to try another task
                self.logger.debug("Attempting to fetch next task...")
                continue

        return None

    def handle_task_result(self, task_content: dict, task_result_content: dict) -> None:
        """Handle task result from client and update database."""
        dataset_uuid = task_content.get(DATASET_UUID)
        dataset_validation_result = task_result_content or {}
        dataset_validation_passed = dataset_validation_result.get("success", False)

        with self.db.with_session() as session:
            # Check if dataset exists before updating
            item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
            if item is None:
                self.logger.error(f"Dataset {dataset_uuid} not found in dataset DB.")
                return

            if dataset_validation_passed:
                _mark_task_completed(session, dataset_uuid)
                # Log to summary
                result = dataset_validation_result

                # Track aggregated statistics
                self.total_frames_processed += result.get('total_frames_sampled', 0)
                self.total_detection_time += result.get('total_time_s', 0)
                self.datasets_succeeded += 1

                # Calculate current average time per frame
                avg_time_per_frame = (
                    self.total_detection_time / self.total_frames_processed
                    if self.total_frames_processed > 0
                    else 0.0
                )

                self.summary_logger.debug(
                    f"✅ {dataset_uuid}: {result.get('total_frames_sampled', 0)} frames, "
                    f"{result.get('total_time_s', 0):.2f}s, "
                    f"{len(result.get('episodes_tested', []))} episodes, "
                    f"backend={result.get('backend', 'unknown')}"
                )

                # Log cumulative statistics
                total_datasets = self.datasets_succeeded + self.datasets_failed
                self.summary_logger.debug(
                    f"📊 Cumulative: {total_datasets} datasets "
                    f"({self.datasets_succeeded} ✅, {self.datasets_failed} ❌), "
                    f"{self.total_frames_processed} frames, "
                    f"{self.total_detection_time:.2f}s total, "
                    f"{avg_time_per_frame*1000:.1f}ms/frame avg"
                )

                self.logger.debug(f"Marked {item.convert_path} dataloader detection as COMPLETED")
            else:
                error_message = dataset_validation_result.get("error_message") or "Dataset validation failed"
                _mark_task_failed(session, dataset_uuid, error_message)
                self.datasets_failed += 1

                # Calculate current average time per frame
                avg_time_per_frame = (
                    self.total_detection_time / self.total_frames_processed
                    if self.total_frames_processed > 0
                    else 0.0
                )

                self.summary_logger.debug(f"❌ {dataset_uuid}: {error_message}")

                # Log cumulative statistics
                total_datasets = self.datasets_succeeded + self.datasets_failed
                self.summary_logger.debug(
                    f"📊 Cumulative: {total_datasets} datasets "
                    f"({self.datasets_succeeded} ✅, {self.datasets_failed} ❌), "
                    f"{self.total_frames_processed} frames, "
                    f"{self.total_detection_time:.2f}s total, "
                    f"{avg_time_per_frame*1000:.1f}ms/frame avg"
                )

                self.logger.debug(
                    f"Marked {item.convert_path} dataloader detection as FAILED: {error_message}"
                )

    def get_statistics(self) -> dict:
        """Get aggregated statistics for all processed tasks.

        Returns:
            Dictionary with keys:
                - datasets_succeeded: Number of datasets that passed detection
                - datasets_failed: Number of datasets that failed detection
                - total_frames: Total frames processed across all datasets
                - total_time_s: Total detection time across all datasets
                - avg_time_per_frame_s: Average time per frame (0 if no frames)
        """
        avg_time_per_frame = (
            self.total_detection_time / self.total_frames_processed
            if self.total_frames_processed > 0
            else 0.0
        )

        return {
            "datasets_succeeded": self.datasets_succeeded,
            "datasets_failed": self.datasets_failed,
            "total_frames": self.total_frames_processed,
            "total_time_s": self.total_detection_time,
            "avg_time_per_frame_s": avg_time_per_frame,
        }


__all__ = [
    "DataloaderDbServer",
    "TASK_CATEGORY",
]
