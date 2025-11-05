"""Dataset detection and validation logic.

This module contains the core validation logic for LeRobot datasets:
- Loading datasets and validating metadata
- Iterating through frames and episodes
- Collecting validation statistics and errors
"""

import logging
import os
import sys
import traceback
from contextlib import redirect_stdout
from pathlib import Path

from robocoin_dataset.dataloader.dataset_utils import (
    create_episode_dataloader,
    create_lerobot_dataset,
)
from robocoin_dataset.dataloader.task_manager import _parse_episode_specification


def _run_dataloader_detection(
    repo_path: str | Path,
    episode_indices: str | int | list[int] | None = "all",
    strict_mode: bool = False,
    batch_size: int = 32,
    num_workers: int = 0,
) -> dict:
    """Validate LeRobot dataset by loading and decoding specified episodes.

    This function performs comprehensive validation of a LeRobot dataset:
    1. Loads the dataset and verifies metadata
    2. Validates ALL video keys are present and decodable
    3. Iterates through ALL frames of specified episodes
    4. Collects detailed statistics and error information

    Args:
        repo_path: Path to LeRobot dataset directory
        episode_indices: Episodes to test (default: "all")
            - None or "all": test all episodes
            - int: single episode (e.g., 0)
            - list[int]: specific episodes (e.g., [0, 1, 2])
            - str: "0", "0,1,2", "0-5", "0-5,10,15-17"
        strict_mode: If True, fail immediately on first error.
                    If False (default), collect all errors and continue.
        batch_size: Batch size for dataloader (default: 32)
        num_workers: Number of dataloader workers (default: 0)

    Returns:
        Comprehensive validation result dictionary:
        {
            "success": bool,  # Overall success (all episodes passed)
            "dataset_path": str,
            "total_episodes_in_dataset": int,
            "episodes_tested": list[int],
            "episodes_succeeded": list[int],
            "episodes_failed": list[int],
            "frames_per_episode": {episode_idx: frame_count},
            "total_frames_validated": int,
            "video_keys": list[str],
            "non_video_keys": list[str],
            "backend": str,
            "backend_reason": str,
            "errors": list[dict],  # List of error details
            "error_summary": str | None,  # Human-readable error summary
        }

    Raises:
        Exception: If strict_mode=True and any validation fails
    """

    # Import tqdm for progress bars
    try:
        from tqdm import tqdm  # type: ignore
    except Exception:
        tqdm = None  # type: ignore

    repo_path = Path(repo_path)

    # Initialize result structure
    result = {
        "success": False,
        "dataset_path": str(repo_path),
        "total_episodes_in_dataset": 0,
        "episodes_tested": [],
        "episodes_succeeded": [],
        "episodes_failed": [],
        "frames_per_episode": {},
        "total_frames_validated": 0,
        "video_keys": [],
        "non_video_keys": [],
        "backend": "unknown",
        "backend_reason": "",
        "errors": [],
        "error_summary": None,
    }

    try:
        # Load dataset
        # Pass dataset name as repo_id and full path as root for clarity
        ds = create_lerobot_dataset(
            repo_id=repo_path.name,  # Dataset folder name (e.g., "my_dataset")
            root=repo_path,           # Full path (e.g., "/path/to/my_dataset")
        )
        result["backend"] = getattr(ds, "robocoin_video_backend", "unknown")
        result["backend_reason"] = getattr(ds, "robocoin_video_backend_reason", "")

        # Get dataset metadata
        total_episodes = len(ds.episode_data_index["from"])
        result["total_episodes_in_dataset"] = total_episodes

        # Collect video and non-video keys
        video_keys = list(ds.meta.video_keys) if hasattr(ds.meta, "video_keys") else []
        all_keys = set(ds.meta.get_features().keys()) if hasattr(ds.meta, "get_features") else set()
        non_video_keys = sorted(all_keys - set(video_keys))

        result["video_keys"] = video_keys
        result["non_video_keys"] = non_video_keys

        # Parse episode specification
        try:
            episodes_to_test = _parse_episode_specification(episode_indices, total_episodes)
        except ValueError as e:
            error_msg = f"Invalid episode specification: {e}"
            result["errors"].append(
                {
                    "type": "episode_specification_error",
                    "message": error_msg,
                }
            )
            result["error_summary"] = error_msg
            # Print error to terminal for debugging
            print(f"\n❌ ERROR: {error_msg}", file=sys.stderr)
            if strict_mode:
                raise ValueError(error_msg) from e
            return result

        result["episodes_tested"] = episodes_to_test

        if not episodes_to_test:
            result["success"] = True  # No episodes to test = success
            return result

        # Progress tracking
        total_frames_to_test = 0
        try:
            for ep_idx in episodes_to_test:
                from_idx = ds.episode_data_index["from"][ep_idx].item()
                to_idx = ds.episode_data_index["to"][ep_idx].item()
                total_frames_to_test += int(to_idx - from_idx)
        except Exception:
            pass

        # Create overall progress bar
        overall_progress = None
        if tqdm is not None:
            overall_progress = tqdm(
                total=total_frames_to_test,
                desc="🔍 Validating dataset",
                unit="frame",
                file=sys.stderr,
                position=0,
            )

        # Test each episode
        for ep_idx in episodes_to_test:
            episode_error = None
            episode_frames = 0

            try:
                # Get episode frame range
                from_idx = ds.episode_data_index["from"][ep_idx].item()
                to_idx = ds.episode_data_index["to"][ep_idx].item()
                episode_frames = int(to_idx - from_idx)

                # Create episode dataloader
                dl = create_episode_dataloader(
                    ds,
                    episode_index=ep_idx,
                    batch_size=batch_size,
                    num_workers=num_workers,
                )

                # Episode-specific progress bar
                ep_progress = None
                if tqdm is not None:
                    ep_progress = tqdm(
                        total=episode_frames,
                        desc=f"  📹 Episode {ep_idx}",
                        unit="frame",
                        file=sys.stderr,
                        position=1,
                        leave=False,
                    )

                # Iterate through all frames
                frames_validated = 0
                with open(os.devnull, "w") as devnull, redirect_stdout(devnull):
                    for batch in dl:
                        # Verify batch structure
                        if not isinstance(batch, dict):
                            raise ValueError(f"Batch is not a dict: {type(batch)}")

                        # Verify all video keys present
                        for vkey in video_keys:
                            if vkey not in batch:
                                raise ValueError(f"Video key '{vkey}' missing from batch")

                        # Count frames in batch
                        batch_size_actual = len(batch["index"]) if "index" in batch else 1
                        frames_validated += batch_size_actual

                        # Update progress bars
                        if ep_progress is not None:
                            ep_progress.update(batch_size_actual)
                        if overall_progress is not None:
                            overall_progress.update(batch_size_actual)

                # Close episode progress bar
                if ep_progress is not None:
                    ep_progress.close()

                # Record success
                result["episodes_succeeded"].append(ep_idx)
                result["frames_per_episode"][ep_idx] = frames_validated
                result["total_frames_validated"] += frames_validated

            except Exception as e:
                episode_error = str(e)
                error_detail = {
                    "type": "episode_validation_error",
                    "episode_idx": ep_idx,
                    "message": episode_error,
                    "traceback": traceback.format_exc(),
                }
                result["errors"].append(error_detail)
                result["episodes_failed"].append(ep_idx)
                result["frames_per_episode"][ep_idx] = 0

                # Print error to terminal with full traceback for debugging
                if overall_progress is not None:
                    overall_progress.write(f"❌ Episode {ep_idx} failed: {episode_error}")
                else:
                    print(f"\n❌ Episode {ep_idx} failed: {episode_error}", file=sys.stderr)

                # Print full traceback to stderr for debugging (even in non-strict mode)
                print(f"\n{'=' * 70}", file=sys.stderr)
                print(f"ERROR in Episode {ep_idx}:", file=sys.stderr)
                print(f"{'-' * 70}", file=sys.stderr)
                print(traceback.format_exc(), file=sys.stderr)
                print(f"{'=' * 70}\n", file=sys.stderr)

                if strict_mode:
                    if overall_progress is not None:
                        overall_progress.close()
                    raise RuntimeError(
                        f"Episode {ep_idx} validation failed: {episode_error}"
                    ) from e

        # Close overall progress bar
        if overall_progress is not None:
            overall_progress.close()

        # Determine overall success
        result["success"] = len(result["episodes_failed"]) == 0

        # Generate error summary
        if result["errors"]:
            failed_eps = result["episodes_failed"]
            result["error_summary"] = (
                f"{len(failed_eps)} episode(s) failed validation: {failed_eps}. "
                f"See 'errors' field for details."
            )

        return result

    except Exception as e:
        # Fatal error (dataset loading, etc.)
        error_msg = str(e)
        result["errors"].append(
            {
                "type": "fatal_error",
                "message": error_msg,
                "traceback": traceback.format_exc(),
            }
        )
        result["error_summary"] = f"Fatal error: {error_msg}"
        result["success"] = False

        # Print fatal error to terminal for debugging
        print(f"\n{'=' * 70}", file=sys.stderr)
        print("FATAL ERROR:", file=sys.stderr)
        print(f"{'-' * 70}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        print(f"{'=' * 70}\n", file=sys.stderr)

        if strict_mode:
            raise

        return result


def run_local_batch_detection(
    db_file: str | Path,
    episodes: str = "all",
    strict_mode: bool = False,
    batch_size: int = 32,
    num_workers: int = 0,
    create_hardlinks: bool = True,
    hardlink_target_dir: Path | None = None,
    hardlink_relative: bool = True,
    hardlink_skip_missing: bool = False,
    logger: logging.Logger | None = None,
) -> dict:
    """Process all pending dataloader detection tasks in batch (local mode).

    Workflow for each dataset:
    1. Sync tasks (_sync_dataloader_detection_tasks)
    2. Loop until no tasks:
       a. Claim one task (_gen_one_dataloader_detection_task) → PROCESSING
       b. Optionally create hardlinks (_prepare_hardlinks)
       c. Run detection (_run_dataloader_detection)
       d. Update status to COMPLETED/FAILED

    Args:
        db_file: Path to database
        episodes: Episodes to test (default: "all")
        strict_mode: Fail immediately on first error (default: False)
        batch_size: Batch size for dataloader (default: 32)
        num_workers: Number of dataloader workers (default: 0)
        create_hardlinks: Whether to create hardlinks (default: True)
        hardlink_target_dir: Target directory for hardlinks (default: None = auto)
        hardlink_relative: Use relative hardlinks (default: True)
        hardlink_skip_missing: Skip missing files in hardlinks (default: False)
        logger: Logger instance (default: None)

    Returns:
        {
            "datasets_processed": int,
            "succeeded": [uuid, ...],
            "failed": [(uuid, error_msg), ...],
        }
    """
    from robocoin_dataset.database.database import DatasetDatabase
    from robocoin_dataset.database.models import DatasetDB, TaskStatus
    from robocoin_dataset.dataloader.dataset_utils import _prepare_hardlinks
    from robocoin_dataset.dataloader.task_manager import (
        _gen_one_dataloader_detection_task,
        _sync_dataloader_detection_tasks,
    )

    _logger = logger or logging.getLogger(__name__)
    db_file_path = Path(db_file).expanduser().absolute()
    db = DatasetDatabase(db_file_path)

    succeeded = []
    failed = []
    datasets_processed = 0

    while True:
        # Sync and claim one task
        with db.with_session() as session:
            _sync_dataloader_detection_tasks(session, logger=_logger)
            dataset_uuid, convert_path = _gen_one_dataloader_detection_task(session)

        if not dataset_uuid or not convert_path:
            break  # No more tasks

        datasets_processed += 1
        _logger.info(f"Processing dataset {datasets_processed}: {dataset_uuid}")

        # Prepare path (with optional hardlinks)
        try:
            if create_hardlinks:
                test_path = _prepare_hardlinks(
                    source_path=convert_path,
                    target_dir=hardlink_target_dir,
                    relative=hardlink_relative,
                    skip_missing=hardlink_skip_missing,
                )
                _logger.info(f"  Created hardlinks at: {test_path}")
            else:
                test_path = Path(convert_path)
        except Exception as e:
            err_msg = f"Path preparation failed: {e}"
            _logger.error(f"  {err_msg}")
            failed.append((dataset_uuid, err_msg))

            # Update DB to FAILED
            with db.with_session() as session:
                item = (
                    session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
                )
                if item:
                    item.data_loader_detection_status = TaskStatus.FAILED
                    item.data_loader_detection_err_msg = err_msg
                    session.commit()
            continue

        # Run detection
        result = _run_dataloader_detection(
            test_path,
            episode_indices=episodes,
            strict_mode=strict_mode,
            batch_size=batch_size,
            num_workers=num_workers,
        )

        # Update DB based on result
        with db.with_session() as session:
            item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
            if item:
                if result["success"]:
                    item.data_loader_detection_status = TaskStatus.COMPLETED
                    item.data_loader_detection_err_msg = None
                    _logger.info(
                        f"  ✅ Validation completed: {result['total_frames_validated']} frames "
                        f"in {len(result['episodes_tested'])} episodes"
                    )
                    succeeded.append(dataset_uuid)
                else:
                    item.data_loader_detection_status = TaskStatus.FAILED
                    item.data_loader_detection_err_msg = result.get(
                        "error_summary", "Unknown error"
                    )
                    _logger.error(f"  ❌ Validation failed: {item.data_loader_detection_err_msg}")
                    failed.append((dataset_uuid, item.data_loader_detection_err_msg))
                session.commit()

    _logger.info(f"Batch processing complete: {len(succeeded)} succeeded, {len(failed)} failed")

    return {
        "datasets_processed": datasets_processed,
        "succeeded": succeeded,
        "failed": failed,
    }
