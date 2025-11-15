"""Local batch execution for dataloader detection tasks.

This module provides local (non-distributed) execution for:
- Sequential processing of datasets in the database
- Hardlink validation before detection
- Direct database updates (no server/client architecture)
"""

import logging
import time
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
    """Run dataloader detection in local batch mode (sequential processing).

    Args:
        db_file: Path to the database file
        summary_logger: Logger for summary output
        episodes: Episode specification (e.g., "all", "0-5", "0,2,4")
        sample_ratio: Ratio of frames to sample (0.0-1.0)
        batch_size: Batch size for dataloader
        num_workers: Number of dataloader workers
        logger: Optional logger instance

    Returns:
        Dictionary with processing statistics

    Note:
        Hardlinks must be pre-created in the database before running detection.
        Use the hardlink preparation script to create them first.
    """
    _logger = logger or logging.getLogger(__name__)
    db = DatasetDatabase(Path(db_file).expanduser().absolute())

    succeeded, failed, datasets_processed = [], [], 0
    dataset_details = []  # Store detailed per-dataset statistics
    batch_start_time = time.perf_counter()
    total_frames = 0

    # Process datasets until none remain
    while True: # MAIN LOOP
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
            # Task was already claimed, so we have dataset_uuid
            error_msg = f"Hardlink assertion failed: {e}"
            _logger.exception(error_msg)

            # Mark task as failed in database
            with db.with_session() as session:
                _mark_task_failed(session, dataset_uuid, error_msg)
            failed.append((dataset_uuid, error_msg))
            summary_logger.debug(f"❌ {dataset_uuid}: {error_msg}")
            continue

        # Run detection with configurable parameters
        result = _run_detection(
            hardlink_path,
            episode_indices=episodes,
            sample_ratio=sample_ratio,
            batch_size=batch_size,
            num_workers=num_workers,
            logger=_logger,
        )

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
