"""Client component for distributed dataloader detection tasks.

This module provides the client-side execution for:
- Connecting to the server and requesting tasks
- Running detection on assigned datasets
- Multi-client process management
"""

import asyncio
import logging
import multiprocessing as mp
import time
from pathlib import Path

from robocoin_dataset.dataloader.dataloader_utils import _run_detection
from robocoin_dataset.distribution_computation.constant import (
    CLIENT_ID,
    MSG_CONTENT,
    MSG_TYPE,
    TASK_ID,
    TASK_RESULT,
    TASK_RESULT_STATUS,
    TASK_SUCCESS,
)
from robocoin_dataset.distribution_computation.task_client import TaskClient
from robocoin_dataset.format_converter.tolerobot.constant import LEFORMAT_PATH

TASK_CATEGORY = "dataloader_detection"


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

    def _process_one_task(self, task_content: dict) -> dict:
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

        self.logger.debug(f"Processing dataset: {test_path}")

        # Run detection with downsampling (pass client_id for progress bar positioning)
        return _run_detection(
            test_path,
            episode_indices=episodes,
            sample_ratio=sample_ratio,
            batch_size=batch_size,
            num_workers=num_workers,
            client_id=self.client_id,
            tqdm_position=self.tqdm_position,
            logger=self.logger,
        )


async def run_one_client_async(
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
                logger.debug(f"✅ Client {client.client_id} is ready, starting task loop")

        # Process tasks until none remain
        while True:
            task = await client.request_task()
            if task is None:
                if logger:
                    logger.debug("📭 No task from server, client exiting")
                break

            if logger:
                logger.debug(f"🚀 Starting to process task: {task.get(TASK_ID)}")

            result_content = client._process_one_task(task)
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
                logger.debug("📤 Task result submitted, preparing to request next task...")

    except Exception as e:
        if logger:
            logger.exception(f"Client runtime exception: {e}")
    finally:
        await client._cleanup()

    return {
        "tasks_processed": tasks_processed,
        "tasks_succeeded": tasks_succeeded,
        "tasks_failed": tasks_failed,
    }


def run_one_client_process_main(
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

    logger.debug(f"Client process {process_id} started, connecting to {server_uri}")

    # Run async client (use process_id as tqdm_position for multi-client progress bars)
    try:
        stats = asyncio.run(
            run_one_client_async(
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
        logger.exception(f"Client process {process_id} failed: {e}")
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


def run_multi_clients(
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
    # Create a simple logger for console output
    console_logger = logging.getLogger("multi_client_console")
    console_logger.setLevel(logging.INFO)
    if not console_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        console_logger.addHandler(handler)

    console_logger.info("\n" + "=" * 80)
    console_logger.info("🚀 STARTING MULTI-CLIENT EXECUTION".center(80))
    console_logger.info("=" * 80)
    console_logger.info(f"\n{'CONFIGURATION'}")
    console_logger.info(f"  Clients            : {num_clients}")
    console_logger.info(f"  Server URI         : {server_uri}")
    console_logger.info(f"  Heartbeat interval : {heartbeat_interval}s")
    console_logger.info(f"  Log directory      : {log_dir}")
    console_logger.info(f"\n{'SPAWNING PROCESSES'}")

    # Create queue for collecting statistics from child processes
    stats_queue = mp.Queue()

    processes = []
    start_time = time.time()

    for i in range(num_clients):
        proc = mp.Process(
            target=run_one_client_process_main,
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
        console_logger.info(f"  ✓ Process {i:>2} spawned (PID: {proc.pid})")

        # Add startup delay to avoid thundering herd
        if i < num_clients - 1:
            time.sleep(0.8)

    console_logger.info(f"\n{'EXECUTION'}")
    console_logger.info(f"  ⏳ Waiting for {num_clients} client(s) to complete...")
    console_logger.info("  💡 Press Ctrl+C to interrupt")
    console_logger.info("")

    exit_codes = {}

    try:
        # Wait for all processes to complete
        for i, proc in enumerate(processes):
            proc.join()
            exit_codes[i] = proc.exitcode

    except KeyboardInterrupt:
        console_logger.info("\n\n" + "=" * 80)
        console_logger.info("⚠️  INTERRUPTION DETECTED - SHUTTING DOWN".center(80))
        console_logger.info("=" * 80 + "\n")
        for i, proc in enumerate(processes):
            if proc.is_alive():
                console_logger.info(f"  ⏹  Terminating process {i:>2} (PID: {proc.pid})")
                proc.terminate()
                proc.join(timeout=5.0)
                if proc.is_alive():
                    console_logger.info(f"  ⚠️  Force-killing process {i:>2} (PID: {proc.pid})")
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
    console_logger.info("\n" + "=" * 80)
    console_logger.info("📊 MULTI-CLIENT EXECUTION SUMMARY".center(80))
    console_logger.info("=" * 80)

    # Configuration section
    console_logger.info(f"\n{'CONFIGURATION'}")
    console_logger.info(f"  Clients spawned    : {num_clients}")
    console_logger.info(f"  Elapsed time       : {time_str}")

    # Task results section
    console_logger.info(f"\n{'TASK RESULTS'}")
    console_logger.info(f"  Total processed    : {total_tasks_processed}")
    console_logger.info(f"  ✅ Succeeded       : {total_tasks_succeeded}")
    console_logger.info(f"  ❌ Failed          : {total_tasks_failed}")

    # Process status section
    console_logger.info(f"\n{'PROCESS STATUS'}")
    console_logger.info(f"  ✅ Completed       : {process_success_count}")
    console_logger.info(f"  ❌ Failed          : {process_fail_count}")

    # Per-process details table
    if exit_codes:
        console_logger.info(f"\n{'PROCESS DETAILS'}")
        console_logger.info(f"  {'ID':<6} {'Status':<18} {'Tasks':<10}")
        console_logger.info(f"  {'-'*6} {'-'*18} {'-'*10}")

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

            console_logger.info(f"  {proc_id:<6} {status:<18} {tasks_processed:<10}")

    console_logger.info("\n" + "=" * 80 + "\n")

    return 0 if total_tasks_failed == 0 else 1


__all__ = [
    "DataloaderDbClient",
    "run_one_client_async",
    "run_one_client_process_main",
    "run_multi_clients",
    "TASK_CATEGORY",
]
