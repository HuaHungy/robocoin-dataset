"""Dataloader utilities and validation for LeRobot datasets.

This module provides a unified interface for:
- Dataset creation and loading
- Episode sampling and dataloader creation
- Local and distributed validation workflows
- Server/client architecture for distributed processing
- Task management for database-backed workflows

All core functionality is consolidated in this module for ease of use and maintenance.
"""

import asyncio
import logging
import multiprocessing as mp
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB, TaskStatus
from robocoin_dataset.dataloader.dataloader_utils import (
    EpisodeSampler,
    LeRobotDataset,
    MultiEpisodeSampler,
    _mark_task_failed,
    _parse_episode_specification,
    _run_detection,
    _update_task_status,
    create_episode_dataloader,
    create_lerobot_dataset,
    run_local_batch_detection,
)
from robocoin_dataset.distribution_computation.constant import (
    CLIENT_ID,
    DATASET_UUID,
    MSG_CONTENT,
    MSG_TYPE,
    TASK_FAILED,
    TASK_ID,
    TASK_RESULT,
    TASK_RESULT_CONTENT,
    TASK_RESULT_STATUS,
    TASK_SUCCESS,
)
from robocoin_dataset.distribution_computation.task_client import TaskClient
from robocoin_dataset.distribution_computation.task_server import TaskServer
from robocoin_dataset.format_converter.tolerobot.constant import LEFORMAT_PATH
from robocoin_dataset.hardlink.prepare_hardlink import (
    prepare_hardlink_for_task,
    query_existing_hardlink,
    update_hardlink_path,
)
from robocoin_dataset.hardlink.validate_hardlink import (
    create_or_validate_hardlinks,
    validate_source_for_lerobot,
)

# =============================
# Task Management Constants
# =============================

TASK_CATEGORY = "dataloader_detection"

# =============================
# Server Components
# =============================


class DataloaderDbProcess:
    """Single-dataset processor for dataloader detection."""

    def __init__(
        self, db_file_path: str | Path, logger: logging.Logger | None = None
    ) -> None:
        if not db_file_path:
            raise ValueError("db_file_path is required and cannot be None or empty")

        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()

        if not self.db_file_path.exists():
            raise FileNotFoundError(f"Database file not found: {self.db_file_path}")
        if not self.db_file_path.is_file():
            raise ValueError(f"Database path is not a file: {self.db_file_path}")

        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)

    def process_one_dataset(
        self,
        hardlink_target_dir: Path | None = None,
    ) -> None:
        """Process one dataset from the queue.

        Args:
            hardlink_target_dir: Target directory for hardlinks (default: None = auto)
        """
        # Sync tasks and claim one
        with self.db.with_session() as session:
            _sync_dataloader_detection_tasks(session, logger=self.logger)
            dataset_uuid, convert_path = _gen_one_dataloader_detection_task(session)

        if not dataset_uuid or not convert_path:
            self.logger.info("No dataloader detection task to process")
            return

        # Prepare hardlink using the centralized helper function
        try:
            test_path = prepare_hardlink_for_task(
                self.db, dataset_uuid, convert_path, hardlink_target_dir
            )
            self.logger.info(f"Using hardlinks: {test_path}")
        except Exception as e:
            error_msg = f"Hardlink preparation failed: {e}"
            self.logger.error(error_msg)
            _mark_task_failed(self.db, dataset_uuid, error_msg)
            return

        # Run detection
        result = _run_detection(test_path, episode_indices="all", sample_ratio=0.1)

        # Update database (uses helper from utils.py)
        _update_task_status(self.db, dataset_uuid, result, self.logger)


class DataloaderDbServer(TaskServer):
    """Task distribution server for dataloader detection."""

    def __init__(
        self,
        db_file_path: str | Path,
        host: str = "0.0.0.0",
        port: int = 8771,
        heartbeat_interval: float = 30.0,
        timeout: float = 15.0,
        logger: logging.Logger | None = None,
        episodes: str = "all",
        sample_ratio: float = 0.1,
        batch_size: int = 32,
        num_workers: int = 0,
        summary_logger: logging.Logger | None = None,
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

        # Auto-shutdown mechanism
        self._shutdown_event = asyncio.Event()
        self._auto_shutdown_task = None

    def get_task_category(self) -> str:
        return TASK_CATEGORY

    def generate_task_content(self) -> dict | None:
        """Generate task content from the database queue.

        Server prepares hardlinks with database integration and sends the
        hardlink path to client. This ensures:
        1. Database query for existing hardlinks
        2. Validation and reuse of valid hardlinks
        3. Creation of new hardlinks if needed (WITHOUT holding DB lock)
        4. Database update with hardlink path

        If hardlink preparation fails, the task is marked as FAILED and the
        server automatically tries the next task. This prevents one bad dataset
        from blocking the entire queue.
        """
        # Retry loop: continue until we find a valid task or run out of tasks
        # This ensures that hardlink preparation failures don't stop processing
        max_retries = 100  # Safety limit to prevent infinite loops
        attempt = 0

        while attempt < max_retries:
            attempt += 1

            # Step 1: Sync and claim task (with DB session)
            with self.db.with_session() as session:
                # pre-sync queue (only on first attempt to avoid redundant syncs)
                if attempt == 1:
                    _sync_dataloader_detection_tasks(session, logger=self.logger)

                # claim one
                dataset_uuid, convert_path = _gen_one_dataloader_detection_task(session)
                if dataset_uuid is None:
                    # No tasks available - schedule shutdown if not already scheduled
                    if self._auto_shutdown_task is None or self._auto_shutdown_task.done():
                        self.logger.info("No tasks available, will auto-shutdown in 5 seconds if no new tasks arrive")
                        self._auto_shutdown_task = asyncio.create_task(self._auto_shutdown_after_delay())
                    return None

                # Task available - cancel any pending shutdown
                if self._auto_shutdown_task and not self._auto_shutdown_task.done():
                    self._auto_shutdown_task.cancel()
                    self._auto_shutdown_task = None

            # Step 2: Prepare hardlinks using the centralized helper function
            try:
                test_path = prepare_hardlink_for_task(
                    self.db, dataset_uuid, convert_path, hardlink_target_dir=None
                )
                self.logger.info(f"Prepared dataset path for client: {test_path}")

                # Success! Return the task
                return {
                    DATASET_UUID: dataset_uuid,
                    LEFORMAT_PATH: str(test_path),  # Send hardlink path to client
                    "episodes": self.episodes,
                    "sample_ratio": self.sample_ratio,
                    "batch_size": self.batch_size,
                    "num_workers": self.num_workers,
                }

            except Exception as e:
                # Hardlink preparation failed - mark as failed and try next task
                err_msg = f"Hardlink preparation failed: {e}"
                self.logger.error(f"❌ {dataset_uuid}: {err_msg}")

                with self.db.with_session() as session:
                    item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
                    if item:
                        item.data_loader_detection_status = TaskStatus.FAILED
                        item.data_loader_detection_err_msg = err_msg
                        session.commit()

                # Log to summary if available
                if self.summary_logger:
                    self.summary_logger.info(f"❌ {dataset_uuid}: {err_msg}")

                # Continue to next iteration to try another task
                self.logger.info("Attempting to fetch next task...")
                continue

        # Safety: should never reach here unless we hit max_retries
        self.logger.warning(f"Reached max retry limit ({max_retries}) in generate_task_content")
        return None

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
                # Log to summary if available
                if self.summary_logger:
                    result = task_result_content.get(TASK_RESULT_CONTENT, {})
                    self.summary_logger.info(
                        f"✅ {ds_uuid}: {result.get('total_frames_sampled', 0)} frames, "
                        f"{result.get('total_time_s', 0):.2f}s, "
                        f"{len(result.get('episodes_tested', []))} episodes, "
                        f"backend={result.get('backend', 'unknown')}"
                    )
            elif db_status == TaskStatus.FAILED:
                item.data_loader_detection_err_msg = db_error_message
                # Version was already incremented when task was claimed (not rolled back on failure)
                if self.summary_logger:
                    self.summary_logger.info(f"❌ {ds_uuid}: {db_error_message}")
            session.commit()
            self.logger.info(
                f"Upsert {item.convert_path} dataloader detection status to {db_status}, update_message: {db_error_message}"
            )

    async def _auto_shutdown_after_delay(self) -> None:
        """Auto-shutdown after 5 seconds of no tasks."""
        try:
            await asyncio.sleep(5.0)
            self.logger.info("Auto-shutdown triggered: No tasks for 5 seconds")
            self._shutdown_event.set()
        except asyncio.CancelledError:
            self.logger.info("Auto-shutdown cancelled: New tasks arrived")

    async def start(self) -> None:
        """Override start to support auto-shutdown."""
        from websockets.legacy.server import serve

        async with serve(self.handler, self.host, self.port, max_size=2**28):
            self.logger.info(f"Task server started successfully: ws://{self.host}:{self.port}")
            # Wait for shutdown event instead of running forever
            await self._shutdown_event.wait()
            self.logger.info("Server shutting down gracefully")


# =============================
# Client Components
# =============================


class DataloaderDbClient(TaskClient):
    """Client for distributed dataloader detection tasks."""

    def __init__(
        self,
        server_uri: str = "ws://localhost:8771",
        heartbeat_interval: float = 30.0,
        logger: logging.Logger | None = None,
        tqdm_position: int = 0,
    ) -> None:
        super().__init__(
            server_uri=server_uri,
            heartbeat_interval=heartbeat_interval,
            logger=logger,
        )
        self.tqdm_position = tqdm_position

    def get_task_category(self) -> str:
        return TASK_CATEGORY

    def generate_task_request_desc(self) -> dict:
        return {}

    def _sync_process_task(self, task_content: dict) -> dict:
        """Process a single task synchronously.

        Client receives the dataset path from server (already prepared with hardlinks).
        Client just runs detection on the provided path.
        """
        # Server provides the dataset path (already prepared with hardlinks)
        test_path = task_content.get(LEFORMAT_PATH)

        # Get configurable parameters (with defaults)
        episodes = task_content.get("episodes", "all")
        sample_ratio = task_content.get("sample_ratio", 0.1)  # Default: 10% sampling
        batch_size = task_content.get("batch_size", 32)
        num_workers = task_content.get("num_workers", 0)

        self.logger.info(f"Processing dataset: {test_path}")

        # Run detection with downsampling (pass client_id for progress bar positioning)
        return _run_detection(
            test_path,
            episode_indices=episodes,
            sample_ratio=sample_ratio,
            batch_size=batch_size,
            num_workers=num_workers,
            client_id=self.client_id,
            tqdm_position=self.tqdm_position,
        )


async def run_client_async(
    server_uri: str, heartbeat_interval: float, logger: logging.Logger, tqdm_position: int = 0
) -> dict:
    """Run a single client that connects to server and processes tasks until none remain.

    Returns:
        Statistics dictionary with keys: tasks_processed, tasks_succeeded, tasks_failed
    """
    client = DataloaderDbClient(
        server_uri=server_uri, heartbeat_interval=heartbeat_interval, logger=logger, tqdm_position=tqdm_position
    )

    # Track task counts
    tasks_processed = 0
    tasks_succeeded = 0
    tasks_failed = 0

    # Connect to server
    try:
        if not client.connected:
            await client.connect_to_server()
            client._receiver_task = asyncio.create_task(client._message_receiver())
            await client.register()
            if not client.client_id:
                if logger:
                    logger.error("❌ Registration failed, exiting")
                return {
                    "tasks_processed": 0,
                    "tasks_succeeded": 0,
                    "tasks_failed": 0,
                }
            await client._start_heartbeat()
            if logger:
                logger.info(f"✅ Client {client.client_id} is ready, starting task loop")

        # Process tasks until none remain
        while True:
            task = await client.request_task()
            if task is None:
                if logger:
                    logger.info("📭 No task from server, client exiting")
                break

            if logger:
                logger.info(f"🚀 Starting to process task: {task.get(TASK_ID)}")

            result_content = await client.process_task(task)
            tasks_processed += 1

            # Check if task succeeded or failed
            if result_content.get(TASK_RESULT_STATUS) == TASK_SUCCESS:
                tasks_succeeded += 1
            else:
                tasks_failed += 1

            result = {
                MSG_TYPE: TASK_RESULT,
                MSG_CONTENT: result_content,
            }
            result[TASK_ID] = task.get(TASK_ID)
            result[CLIENT_ID] = client.client_id
            await client.submit_result(result)
            if logger:
                logger.info("📤 Task result submitted, preparing to request next task...")

    except Exception as e:
        if logger:
            logger.error(f"Client runtime exception: {e}")
    finally:
        await client._cleanup()

    return {
        "tasks_processed": tasks_processed,
        "tasks_succeeded": tasks_succeeded,
        "tasks_failed": tasks_failed,
    }


def client_process_main(
    server_uri: str,
    heartbeat_interval: float,
    log_dir: str | Path,
    log_level: str,
    process_id: int,
    stats_queue: "mp.Queue | None" = None,
) -> int:
    """Entry point for each client process in multi-client mode."""
    from robocoin_dataset.utils.logger import setup_logger

    # Suppress console output for client processes
    # Remove all handlers from root logger
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    logging.basicConfig(
        level=logging.CRITICAL + 1,  # Disable console output
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[],  # No handlers
    )

    # Create per-process logger with unique file name
    logger = setup_logger(
        name=f"client_{process_id:02d}",
        log_dir=Path(log_dir),
        level=getattr(logging, log_level, logging.INFO),
        console_output=False,
    )

    logger.info(f"Client process {process_id} started, connecting to {server_uri}")

    # Run async client (use process_id as tqdm_position for multi-client progress bars)
    try:
        stats = asyncio.run(
            run_client_async(
                server_uri=server_uri,
                heartbeat_interval=heartbeat_interval,
                logger=logger,
                tqdm_position=process_id,
            )
        )
        # Send statistics back to parent process
        if stats_queue is not None:
            stats_queue.put({"process_id": process_id, **stats})
        return 0 if stats["tasks_failed"] == 0 else 1
    except Exception as e:
        logger.error(f"Client process {process_id} failed: {e}")
        if stats_queue is not None:
            stats_queue.put(
                {
                    "process_id": process_id,
                    "tasks_processed": 0,
                    "tasks_succeeded": 0,
                    "tasks_failed": 0,
                }
            )
        return 1


def run_multi_client(
    server_uri: str,
    num_clients: int,
    heartbeat_interval: float,
    log_dir: str | Path,
    log_level: str,
) -> int:
    """Spawn multiple client processes.

    Args:
        server_uri: WebSocket URI of the server (e.g. ws://localhost:8771)
        num_clients: Number of client processes to spawn
        heartbeat_interval: Heartbeat interval in seconds
        log_dir: Directory for log files
        log_level: Logging level string (e.g. "INFO", "DEBUG")

    Returns:
        Exit code: 0 if all processes succeeded, 1 otherwise
    """
    print("\n" + "=" * 80)
    print("🚀 STARTING MULTI-CLIENT EXECUTION".center(80))
    print("=" * 80)
    print(f"\n{'CONFIGURATION'}")
    print(f"  Clients            : {num_clients}")
    print(f"  Server URI         : {server_uri}")
    print(f"  Heartbeat interval : {heartbeat_interval}s")
    print(f"  Log directory      : {log_dir}")
    print(f"\n{'SPAWNING PROCESSES'}")

    # Create queue for collecting statistics from child processes
    stats_queue = mp.Queue()

    processes = []
    start_time = time.time()

    for i in range(num_clients):
        proc = mp.Process(
            target=client_process_main,
            kwargs=dict(
                server_uri=server_uri,
                heartbeat_interval=heartbeat_interval,
                log_dir=log_dir,
                log_level=log_level,
                process_id=i,
                stats_queue=stats_queue,
            ),
        )
        proc.start()
        processes.append(proc)
        print(f"  ✓ Process {i:>2} spawned (PID: {proc.pid})")

        # Add startup delay to avoid thundering herd
        if i < num_clients - 1:
            time.sleep(0.1)

    print(f"\n{'EXECUTION'}")
    print(f"  ⏳ Waiting for {num_clients} client(s) to complete...")
    print("  💡 Press Ctrl+C to interrupt")
    print()

    exit_codes = {}

    try:
        # Wait for all processes to complete
        for i, proc in enumerate(processes):
            proc.join()
            exit_codes[i] = proc.exitcode

    except KeyboardInterrupt:
        print("\n\n" + "=" * 80)
        print("⚠️  INTERRUPTION DETECTED - SHUTTING DOWN".center(80))
        print("=" * 80 + "\n")
        for i, proc in enumerate(processes):
            if proc.is_alive():
                print(f"  ⏹  Terminating process {i:>2} (PID: {proc.pid})")
                proc.terminate()
                proc.join(timeout=5.0)
                if proc.is_alive():
                    print(f"  ⚠️  Force-killing process {i:>2} (PID: {proc.pid})")
                    proc.kill()
                    proc.join()
                exit_codes[i] = -2  # Mark as interrupted

    elapsed = time.time() - start_time

    # Collect statistics from queue
    process_stats = {}
    try:
        while not stats_queue.empty():
            stats = stats_queue.get_nowait()
            process_stats[stats["process_id"]] = stats
    except Exception:
        pass

    # Calculate aggregated task statistics
    total_tasks_processed = sum(s.get("tasks_processed", 0) for s in process_stats.values())
    total_tasks_succeeded = sum(s.get("tasks_succeeded", 0) for s in process_stats.values())
    total_tasks_failed = sum(s.get("tasks_failed", 0) for s in process_stats.values())

    # Calculate process statistics
    process_success_count = sum(1 for code in exit_codes.values() if code == 0)
    process_fail_count = sum(
        1 for code in exit_codes.values() if code not in (0, None) and code is not None
    )

    # Format elapsed time
    if elapsed < 60:
        time_str = f"{elapsed:.1f}s"
    elif elapsed < 3600:
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        time_str = f"{minutes}m {seconds}s"
    else:
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        time_str = f"{hours}h {minutes}m"

    # Summary header
    print("\n" + "=" * 80)
    print("📊 MULTI-CLIENT EXECUTION SUMMARY".center(80))
    print("=" * 80)

    # Configuration section
    print(f"\n{'CONFIGURATION'}")
    print(f"  Clients spawned    : {num_clients}")
    print(f"  Elapsed time       : {time_str}")

    # Task results section
    print(f"\n{'TASK RESULTS'}")
    print(f"  Total processed    : {total_tasks_processed}")
    print(f"  ✅ Succeeded       : {total_tasks_succeeded}")
    print(f"  ❌ Failed          : {total_tasks_failed}")

    # Process status section
    print(f"\n{'PROCESS STATUS'}")
    print(f"  ✅ Completed       : {process_success_count}")
    print(f"  ❌ Failed          : {process_fail_count}")

    # Per-process details table
    if exit_codes:
        print(f"\n{'PROCESS DETAILS'}")
        print(f"  {'ID':<6} {'Status':<18} {'Tasks':<10}")
        print(f"  {'-'*6} {'-'*18} {'-'*10}")

        for proc_id in sorted(exit_codes.keys()):
            code = exit_codes[proc_id]
            stats = process_stats.get(proc_id, {})
            tasks_processed = stats.get("tasks_processed", 0)

            if code == 0:
                status = "✅ SUCCESS"
            elif code == -2:
                status = "⚠️  INTERRUPTED"
            elif code is None:
                status = "❓ UNKNOWN"
            else:
                status = f"❌ FAILED (exit {code})"

            print(f"  {proc_id:<6} {status:<18} {tasks_processed:<10}")

    print("\n" + "=" * 80 + "\n")

    return 0 if total_tasks_failed == 0 else 1


# =============================
# Task Management Functions
# =============================


def _sync_dataloader_detection_tasks(
    session: "Session",
    logger: logging.Logger | None = None,
) -> None:
    """Mark datasets requiring dataloader detection as pending and align versions.

    Trigger rules (STRICT REQUIREMENTS):
      - data_merge_status must be COMPLETED
      - convert_status must be COMPLETED
      - data_loader_detection_status is NULL (never tested), PENDING, or COMPLETED but outdated

    WARNING: NULL data_loader_detection_status is ILLEGAL but handled for robustness.
    """
    from sqlalchemy.sql.expression import and_, or_

    _logger = logger or logging.getLogger(__name__)

    query = session.query(DatasetDB).filter(
        and_(
            DatasetDB.data_merge_status == TaskStatus.COMPLETED,
            or_(
                # NEW: Match records that have never been tested (NULL status)
                DatasetDB.data_loader_detection_status == None,  # noqa: E711
                # Match records explicitly marked as PENDING
                DatasetDB.data_loader_detection_status == TaskStatus.PENDING,
                # Match records that were COMPLETED but are now outdated
                and_(
                    DatasetDB.data_loader_detection_status == TaskStatus.COMPLETED,
                    DatasetDB.data_loader_detection_version_ps < DatasetDB.data_merge_version,
                ),
            ),
        )
    )

    items = query.all()
    if not items:
        return

    # Separate NULL status records and warn about them
    null_status_items = []
    valid_items = []

    for item in items:
        if item.data_loader_detection_status is None:
            null_status_items.append(item)
        else:
            valid_items.append(item)

        item.data_loader_detection_status = TaskStatus.PENDING
        item.data_loader_detection_version_ps = item.data_merge_version
        item.data_loader_detection_version = (item.data_loader_detection_version or 0) + 1

    # Log warnings for NULL status records
    if null_status_items:
        _logger.warning(
            f"⚠️  Found {len(null_status_items)} dataset(s) with NULL data_loader_detection_status. "
            f"This is ILLEGAL - status should be initialized. Treating as PENDING for robustness."
        )
        for item in null_status_items:
            _logger.warning(
                f"   ⚠️  Dataset {item.dataset_uuid} has NULL data_loader_detection_status "
                f"(convert_path: {item.convert_path})"
            )

    if valid_items:
        _logger.info(f"Marked {len(valid_items)} dataset(s) as PENDING for dataloader detection")

    session.commit()


def _gen_one_dataloader_detection_task(session: "Session") -> tuple[str | None, str | None]:
    """Claim one pending dataset and transition it to PROCESSING.

    Returns (dataset_uuid, convert_path) or (None, None) if no task available.
    """
    item = (
        session.query(DatasetDB)
        .filter(DatasetDB.data_merge_status == TaskStatus.COMPLETED)
        .filter(DatasetDB.data_loader_detection_status == TaskStatus.PENDING)
        .first()
    )
    if not item:
        return None, None

    item.data_loader_detection_status = TaskStatus.PROCESSING
    session.commit()
    return item.dataset_uuid, item.convert_path


# =============================
# Public API Exports
# =============================

__all__ = [
    # Dataset utilities (from utils module)
    "LeRobotDataset",
    "EpisodeSampler",
    "MultiEpisodeSampler",
    "create_lerobot_dataset",
    "create_episode_dataloader",
    # Hardlink utilities - database operations (from prepare_hardlink module)
    "query_existing_hardlink",
    "update_hardlink_path",
    # Hardlink utilities - file system operations (from validate_hardlink module)
    "create_or_validate_hardlinks",
    "validate_source_for_lerobot",
    # Detection and validation (from utils module)
    "_run_detection",  # Fast detection with sampling
    "run_local_batch_detection",
    # Task management
    "TASK_CATEGORY",
    "_sync_dataloader_detection_tasks",
    "_gen_one_dataloader_detection_task",
    "_parse_episode_specification",
    # Server components
    "DataloaderDbProcess",
    "DataloaderDbServer",
    # Client components
    "DataloaderDbClient",
    "run_client_async",
    "client_process_main",
    "run_multi_client",
]
