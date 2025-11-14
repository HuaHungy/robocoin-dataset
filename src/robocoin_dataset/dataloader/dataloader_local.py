"""Local batch execution for dataloader detection tasks.

This module provides local (non-distributed) execution for:
- Sequential processing of datasets in the database
- Hardlink validation before detection
- Direct database updates (no server/client architecture)
"""

import logging
import time
import traceback
from pathlib import Path

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.dataloader.dataloader_task import (
    _gen_one_dataloader_detection_task,
    _mark_task_completed,
    _mark_task_failed,
    _sync_dataloader_detection_tasks,
)
from robocoin_dataset.dataloader.dataloader_utils import _run_detection


def run_local_detection(
    db_file: str | Path,
    summary_logger: logging.Logger,
    episodes: str = "all",
    sample_ratio: float = 0.1,
    batch_size: int = 32,
    num_workers: int = 0,
    logger: logging.Logger | None = None,
) -> dict:

    _logger = logger or logging.getLogger(__name__)
    db = DatasetDatabase(Path(db_file).expanduser().absolute())

    succeeded, failed, datasets_processed = [], [], 0
    dataset_details = []  # Store detailed per-dataset statistics
    batch_start_time = time.perf_counter()
    total_frames = 0

    # Process datasets until none remain
    while True: # MAIN LOOP
        dataset_uuid = None  # Initialize to avoid NameError in exception handlers
        hardlink_path = None

        # Sync+Gen tasks and claim one (includes hardlink validation)
        try:
            with db.with_session() as session:
                _sync_dataloader_detection_tasks(session, logger=_logger)
                dataset_uuid, hardlink_path = _gen_one_dataloader_detection_task(session)

            if not dataset_uuid or not hardlink_path:
                break

            datasets_processed += 1
            _logger.debug(f"Processing dataset {datasets_processed}: {dataset_uuid}")
            _logger.debug(f"Using existing hardlink: {hardlink_path}")

        except FileNotFoundError as e:
            # Task was claimed before validation, so dataset_uuid is always set
            error_msg = f"Hardlink assertion failed: {e}\n{traceback.format_exc()}"
            _logger.exception(error_msg)
            # Mark task as failed in database
            with db.with_session() as session:
                _mark_task_failed(session, dataset_uuid, error_msg)
            failed.append((dataset_uuid, error_msg))
            summary_logger.debug(f"❌ {dataset_uuid}: {error_msg}")
            continue
        except Exception as e:
            # Catch any unexpected exceptions during task generation/claiming
            if dataset_uuid:
                error_msg = f"Unexpected error during task generation: {e}\n{traceback.format_exc()}"
                _logger.exception(error_msg)
                with db.with_session() as session:
                    _mark_task_failed(session, dataset_uuid, error_msg)
                failed.append((dataset_uuid, error_msg))
                summary_logger.debug(f"❌ {dataset_uuid}: {error_msg}")
            else:
                _logger.exception(f"❌ Unexpected error before task claimed: {e}")
            continue

        # Run detection with configurable parameters (wrapped in try-except for safety)
        try:
            result = _run_detection(
                hardlink_path,
                episode_indices=episodes,
                sample_ratio=sample_ratio,
                batch_size=batch_size,
                num_workers=num_workers,
                logger=_logger,
            )
        except Exception as e:
            # Safety net: _run_detection should catch all exceptions internally,
            # but if something catastrophic happens, we still want to mark as FAILED
            error_msg = f"Catastrophic failure during detection: {e}\n{traceback.format_exc()}"
            _logger.exception(error_msg)
            with db.with_session() as session:
                _mark_task_failed(session, dataset_uuid, error_msg)
            failed.append((dataset_uuid, error_msg))
            summary_logger.debug(f"❌ {dataset_uuid}: {error_msg}")
            continue

        # Update database based on detection result
        if result.get("success"):
            # Mark task as success in database
            with db.with_session() as session:
                _mark_task_completed(session, dataset_uuid)
            succeeded.append(dataset_uuid)
            total_frames += result.get("total_frames_sampled", 0)

            # Collect detailed statistics for summary
            dataset_name = Path(hardlink_path).name
            num_episodes_tested = len(result.get("episodes_tested", []))
            dataset_details.append({
                "uuid": dataset_uuid,
                "dataset_name": dataset_name,
                "total_time_sec": result.get("total_time_s", 0),
                "num_episodes": num_episodes_tested,
                "total_frames": result.get("total_frames_sampled", 0),
                "time_per_episode_sec": result.get("time_per_episode_s", 0),
                "frames_per_episode": result.get("total_frames_sampled", 0) / num_episodes_tested if num_episodes_tested > 0 else 0,
            })

            summary_logger.debug(
                f"✅ Detection succeeded for {dataset_uuid}: "
                f"{result.get('total_frames_sampled', 0)} frames in {result.get('total_time_s', 0):.2f}s"
            )
            _logger.debug(
                f"✅ Detection succeeded for {dataset_uuid}: "
                f"{result.get('total_frames_sampled', 0)} frames in {result.get('total_time_s', 0):.2f}s"
            )
        else:
            error_msg = result.get("error_message", "Unknown error")
            # Mark task as failed in database
            with db.with_session() as session:
                _mark_task_failed(session, dataset_uuid, error_msg)
            failed.append((dataset_uuid, error_msg))
            summary_logger.debug(f"❌ {dataset_uuid}: {error_msg}")
            _logger.error(f"❌ Detection failed for {dataset_uuid}: {error_msg}")

    # Calculate batch statistics
    batch_elapsed = time.perf_counter() - batch_start_time
    avg_time_per_frame = batch_elapsed / total_frames if total_frames > 0 else 0.0

    _logger.debug(
        f"Batch processing complete: {len(succeeded)} succeeded, {len(failed)} failed | "
        f"{batch_elapsed:.2f}s total, {total_frames} frames, {avg_time_per_frame*1000:.1f}ms/frame avg"
    )

    return {
        "datasets_processed": datasets_processed,
        "succeeded": succeeded,
        "failed": failed,
        "total_time_s": batch_elapsed,
        "total_frames": total_frames,
        "avg_time_per_frame_s": avg_time_per_frame,
        "dataset_details": dataset_details,  # Per-dataset statistics for detailed analysis
    }


__all__ = [
    "run_local_detection",
]
