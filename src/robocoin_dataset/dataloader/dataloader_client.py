"""Client-side components for distributed dataloader detection.

This module provides:
- DataloaderDbClient: Single client for connecting to server
- Multi-client process management utilities
"""

import asyncio
import logging
import multiprocessing as mp
import time
from pathlib import Path

from robocoin_dataset.dataloader.dataset_utils import _prepare_hardlinks
from robocoin_dataset.dataloader.detection import _run_dataloader_detection
from robocoin_dataset.dataloader.task_manager import TASK_CATEGORY
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


class DataloaderDbClient(TaskClient):
    """Client for distributed dataloader detection tasks."""

    def __init__(
        self,
        server_uri: str = "ws://localhost:8771",
        heartbeat_interval: float = 30.0,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(
            server_uri=server_uri,
            heartbeat_interval=heartbeat_interval,
            logger=logger,
        )

    def get_task_category(self) -> str:
        return TASK_CATEGORY

    def generate_task_request_desc(self) -> dict:
        return {}

    def _sync_process_task(self, task_content: dict) -> dict:
        """Process a single task synchronously."""
        repo_path = task_content.get(LEFORMAT_PATH)

        # Get configurable parameters (with defaults)
        episodes = task_content.get("episodes", "all")
        strict_mode = task_content.get("strict_mode", False)
        batch_size = task_content.get("batch_size", 32)
        num_workers = task_content.get("num_workers", 0)

        # Hardlink parameters (optional, default: no hardlinks in distributed mode)
        create_hardlinks = task_content.get("create_hardlinks", False)

        # Prepare path (with optional hardlinks)
        if create_hardlinks:
            hardlink_relative = task_content.get("hardlink_relative", True)
            hardlink_skip_missing = task_content.get("hardlink_skip_missing", False)
            test_path = _prepare_hardlinks(
                source_path=repo_path,
                relative=hardlink_relative,
                skip_missing=hardlink_skip_missing,
            )
        else:
            test_path = repo_path

        return _run_dataloader_detection(
            test_path,
            episode_indices=episodes,
            strict_mode=strict_mode,
            batch_size=batch_size,
            num_workers=num_workers,
        )


# =============================
# Multi-process support for client and local modes
# =============================


async def run_client_async(
    server_uri: str, heartbeat_interval: float, logger: logging.Logger
) -> dict:
    """Run a single client that connects to server and processes tasks until none remain.

    Returns:
        Statistics dictionary with keys: tasks_processed, tasks_succeeded, tasks_failed
    """
    client = DataloaderDbClient(
        server_uri=server_uri, heartbeat_interval=heartbeat_interval, logger=logger
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

    # Create per-process logger
    logger = setup_logger(
        name=f"dataloader_client_{process_id}",
        log_dir=Path(log_dir),
        level=getattr(logging, log_level, logging.INFO),
    )

    logger.info(f"Client process {process_id} started, connecting to {server_uri}")

    # Run async client
    try:
        stats = asyncio.run(
            run_client_async(
                server_uri=server_uri,
                heartbeat_interval=heartbeat_interval,
                logger=logger,
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
    print(f"🚀 Starting {num_clients} client process(es)...")
    print(f"   Server: {server_uri}")
    print(f"   Heartbeat: {heartbeat_interval}s")
    print(f"   Log dir: {log_dir}")
    print()

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
        print(f"   ✓ Client process {i} spawned (PID: {proc.pid})")

        # Add startup delay to avoid thundering herd
        if i < num_clients - 1:
            time.sleep(0.1)

    print(f"\n⏳ Waiting for {num_clients} client(s) to complete...")
    print("   Press Ctrl+C to interrupt\n")

    exit_codes = {}

    try:
        # Wait for all processes to complete
        for i, proc in enumerate(processes):
            proc.join()
            exit_codes[i] = proc.exitcode

    except KeyboardInterrupt:
        print("\n\n⚠️  KeyboardInterrupt received, shutting down clients...")
        for i, proc in enumerate(processes):
            if proc.is_alive():
                print(f"   Terminating process {i} (PID: {proc.pid})")
                proc.terminate()
                proc.join(timeout=5.0)
                if proc.is_alive():
                    print(f"   Force-killing process {i} (PID: {proc.pid})")
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

    # Summary
    print("\n" + "=" * 70)
    print("📊 MULTI-CLIENT SUMMARY")
    print("=" * 70)
    print(f"Total clients: {num_clients}")
    print(f"Elapsed time: {elapsed:.1f}s")
    print()

    # Display TASK statistics (not process statistics)
    print(f"📦 Tasks processed: {total_tasks_processed}")
    print(f"✅ Tasks succeeded: {total_tasks_succeeded}")
    print(f"❌ Tasks failed: {total_tasks_failed}")
    print()

    # Display process-level information
    process_success_count = sum(1 for code in exit_codes.values() if code == 0)
    process_fail_count = sum(
        1 for code in exit_codes.values() if code not in (0, None) and code is not None
    )

    print(
        f"🔧 Process completions: {process_success_count} successful, {process_fail_count} failed"
    )

    if exit_codes:
        print("\nPer-process details:")
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
            print(f"   Process {proc_id}: {status} ({tasks_processed} tasks)")

    print("=" * 70 + "\n")

    return 0 if total_tasks_failed == 0 else 1
