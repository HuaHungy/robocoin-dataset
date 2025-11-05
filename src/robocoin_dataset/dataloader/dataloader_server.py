"""Server-side components for distributed dataloader detection.

This module provides:
- DataloaderDbProcess: Single-dataset processor
- DataloaderDbServer: Task distribution server
"""

import logging
from pathlib import Path

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB, TaskStatus
from robocoin_dataset.dataloader.detection import _run_dataloader_detection
from robocoin_dataset.dataloader.task_manager import (
    DEFAULT_DB_FILE,
    TASK_CATEGORY,
    _gen_one_dataloader_detection_task,
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


class DataloaderDbProcess:
    """Single-dataset processor for dataloader detection."""

    def __init__(
        self, db_file_path: str | Path | None = None, logger: logging.Logger | None = None
    ) -> None:
        self.db_file_path: Path = (
            Path(db_file_path if db_file_path is not None else DEFAULT_DB_FILE)
            .expanduser()
            .absolute()
        )
        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)

    def process_one_dataset(self) -> None:
        """Process one dataset from the queue."""
        # 1) Sync tasks (queue pending/stale)
        with self.db.with_session() as session:
            _sync_dataloader_detection_tasks(session, logger=self.logger)
            dataset_uuid, convert_path = _gen_one_dataloader_detection_task(session)

        if not dataset_uuid or not convert_path:
            self.logger.info("No dataloader detection task to process")
            return

        # 2) Run detection and update status (default: test all episodes, non-strict mode)
        result = _run_dataloader_detection(
            convert_path,
            episode_indices="all",
            strict_mode=False,
        )

        # Update database based on result
        with self.db.with_session() as session:
            item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
            if item is None:
                raise ValueError(f"Dataset {dataset_uuid} not found")

            if result["success"]:
                item.data_loader_detection_status = TaskStatus.COMPLETED
                item.data_loader_detection_err_msg = None
                # Version was already incremented when task was claimed
                self.logger.info(
                    f"Dataset {dataset_uuid} validation completed: "
                    f"{result['total_frames_validated']} frames in {len(result['episodes_tested'])} episodes"
                )
            else:
                item.data_loader_detection_status = TaskStatus.FAILED
                item.data_loader_detection_err_msg = result.get("error_summary", "Unknown error")
                # Version was already incremented when task was claimed (not rolled back on failure)
                self.logger.error(
                    f"Dataset {dataset_uuid} validation failed: {result.get('error_summary', 'Unknown error')}"
                )

            session.commit()


class DataloaderDbServer(TaskServer):
    """Task distribution server for dataloader detection."""

    def __init__(
        self,
        db_file_path: str | Path | None = None,
        host: str = "0.0.0.0",
        port: int = 8771,
        heartbeat_interval: float = 30.0,
        timeout: float = 15.0,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(
            logger=logger,
            host=host,
            port=port,
            heartbeat_interval=heartbeat_interval,
            timeout=timeout,
        )
        self.db_file_path: Path = (
            Path(db_file_path if db_file_path is not None else DEFAULT_DB_FILE)
            .expanduser()
            .absolute()
        )
        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)

    def get_task_category(self) -> str:
        return TASK_CATEGORY

    def generate_task_content(self) -> dict | None:
        """Generate task content from the database queue."""
        with self.db.with_session() as session:
            # pre-sync queue
            _sync_dataloader_detection_tasks(session, logger=self.logger)

            # claim one
            dataset_uuid, convert_path = _gen_one_dataloader_detection_task(session)
            if dataset_uuid is None:
                return None

            return {
                DATASET_UUID: dataset_uuid,
                LEFORMAT_PATH: convert_path,
            }

    def handle_task_result(self, task_content: dict, task_result_content: dict) -> None:
        """Handle task result from client and update database."""
        ds_uuid = task_content.get(DATASET_UUID)
        # Client execution state: did the client process crash/throw exception?
        client_execution_status = task_result_content.get(TASK_RESULT_STATUS)

        # Level 1: Check if client crashed (process-level failure)
        if client_execution_status == TASK_FAILED:
            db_status = TaskStatus.FAILED
            db_error_message = task_result_content.get("err_msg", "Client execution failed")
        else:
            # Level 2: Client executed successfully, check dataset validation result (business-level)
            dataset_validation_result = task_result_content.get(TASK_RESULT_CONTENT, {})
            dataset_validation_passed = dataset_validation_result.get("success", False)

            if dataset_validation_passed:
                db_status = TaskStatus.COMPLETED
                db_error_message = None
            else:
                db_status = TaskStatus.FAILED
                db_error_message = dataset_validation_result.get(
                    "error_summary", "Dataset validation failed"
                )

        with self.db.with_session() as session:
            item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == ds_uuid).first()
            if item is None:
                self.logger.error(f"Dataset {ds_uuid} not found in dataset DB.")
                return

            item.data_loader_detection_status = db_status
            if db_status == TaskStatus.COMPLETED:
                # Version was already incremented when task was claimed
                item.data_loader_detection_err_msg = None
            elif db_status == TaskStatus.FAILED:
                item.data_loader_detection_err_msg = db_error_message
                # Version was already incremented when task was claimed (not rolled back on failure)
            session.commit()
            self.logger.info(
                f"Upsert {item.convert_path} dataloader detection status to {db_status}, update_message: {db_error_message}"
            )
