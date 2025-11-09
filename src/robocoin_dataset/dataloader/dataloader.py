"""Orchestration layer for dataloader detection tasks.

This module provides high-level orchestration for:
- Server/client architecture for distributed processing
- Multi-client task distribution and execution
- Asynchronous client task processing

Core utilities, database operations, and business logic are in dataloader_utils.py.
This module focuses solely on assembling and coordinating those components.
"""

import asyncio
import logging
import multiprocessing as mp
import time
from pathlib import Path

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB, TaskStatus
from robocoin_dataset.dataloader.dataloader_utils import (
    TASK_CATEGORY,
    LeRobotDataset,
    MultiEpisodeSampler,
    _gen_one_dataloader_detection_task,
    _parse_episode_specification,
    _run_detection,
    _sync_dataloader_detection_tasks,
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
# Server Components
# =============================


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

            # Step 1: Sync and claim task (with DB session)
            with self.db.with_session() as session:
                # pre-sync queue (only on first attempt to avoid redundant syncs)
                if attempt == 1:
                    _sync_dataloader_detection_tasks(session, logger=self.logger)

                # claim one
                dataset_uuid, convert_path = _gen_one_dataloader_detection_task(session)
                if dataset_uuid is None:
                    return None

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
                # Log to summary
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
                self.summary_logger.info(f"❌ {ds_uuid}: {db_error_message}")
            session.commit()
            self.logger.info(
                f"Upsert {item.convert_path} dataloader detection status to {db_status}, update_message: {db_error_message}"
            )


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
# Public API Exports
# =============================

__all__ = [
    # Re-exported from dataloader_utils for convenience
    "TASK_CATEGORY",
    "LeRobotDataset",
    "MultiEpisodeSampler",
    "create_lerobot_dataset",
    "create_episode_dataloader",
    "run_local_batch_detection",
    "_run_detection",
    "_parse_episode_specification",
    "_sync_dataloader_detection_tasks",
    "_gen_one_dataloader_detection_task",
    # Re-exported from hardlink modules for convenience
    "query_existing_hardlink",
    "update_hardlink_path",
    "create_or_validate_hardlinks",
    "validate_source_for_lerobot",
    # Orchestration components (defined in this module)
    "DataloaderDbServer",
    "DataloaderDbClient",
    "run_client_async",
    "client_process_main",
    "run_multi_client",
]
