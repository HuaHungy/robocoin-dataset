import asyncio
import logging
import multiprocessing as mp
import os
import sys
import time
import traceback
from collections.abc import Iterator
from contextlib import redirect_stdout
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import and_, or_

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB, TaskStatus
from robocoin_dataset.distribution_computation.constant import (
    CLIENT_ID,
    DATASET_UUID,
    ERR_MSG,
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

# =============================
# LeRobot dataset/dataloader utilities (no DB)
# =============================
# Best-effort: auto-add vendored lerobot path for local runs without PYTHONPATH
try:
    _here_lr = Path(__file__).resolve()
    _repo_root_lr = _here_lr.parents[3]
    _vendored_lr = _repo_root_lr / "third_parties" / "robocoin-lerobot" / "src"
    if _vendored_lr.is_dir() and str(_vendored_lr) not in sys.path:
        sys.path.insert(0, str(_vendored_lr))
except Exception:
    pass

import torch  # type: ignore

try:
    # Prefer the vendored lerobot package in third_parties if available on PYTHONPATH
    from lerobot.datasets.lerobot_dataset import LeRobotDataset  # type: ignore
except Exception:  # pragma: no cover
    LeRobotDataset = None  # type: ignore


class EpisodeSampler(torch.utils.data.Sampler):  # type: ignore
    """Episode sampler referencing lerobot's visualize_dataset logic.

    Selects the frame indices belonging to a given episode.
    """

    def __init__(self, dataset: "LeRobotDataset", episode_index: int) -> None:
        from_idx = dataset.episode_data_index["from"][episode_index].item()
        to_idx = dataset.episode_data_index["to"][episode_index].item()
        self.frame_ids = range(from_idx, to_idx)

    def __iter__(self) -> Iterator:
        return iter(self.frame_ids)

    def __len__(self) -> int:
        return len(self.frame_ids)


def _worker_init_suppress_output(worker_id: int) -> None:
    """Suppress stdout/stderr in DataLoader worker processes.

    This prevents print statements in third-party libraries (like lerobot's video_utils.py)
    from flooding the console when using num_workers > 0.

    Args:
        worker_id: Worker process ID (provided by PyTorch DataLoader)
    """
    import atexit
    import sys

    # Close existing file objects if they exist
    if hasattr(sys.stdout, "close") and sys.stdout not in (sys.__stdout__,):
        try:
            sys.stdout.close()
        except Exception:
            pass
    if hasattr(sys.stderr, "close") and sys.stderr not in (sys.__stderr__,):
        try:
            sys.stderr.close()
        except Exception:
            pass

    # Open new file handles
    devnull_out = open(os.devnull, "w")
    devnull_err = open(os.devnull, "w")

    sys.stdout = devnull_out
    sys.stderr = devnull_err

    # Register cleanup to close handles when worker exits
    def cleanup() -> None:
        try:
            devnull_out.close()
        except Exception:
            pass
        try:
            devnull_err.close()
        except Exception:
            pass

    atexit.register(cleanup)


def create_episode_dataloader(
    dataset: "LeRobotDataset",
    episode_index: int,
    batch_size: int = 32,
    num_workers: int = 0,
) -> torch.utils.data.DataLoader:  # type: ignore
    episode_sampler = EpisodeSampler(dataset, episode_index)
    return torch.utils.data.DataLoader(
        dataset,
        num_workers=num_workers,
        batch_size=batch_size,
        sampler=episode_sampler,
        worker_init_fn=_worker_init_suppress_output if num_workers > 0 else None,
    )


def _prepare_symlinks(
    source_path: str | Path,
    target_dir: Path | None = None,
    relative: bool = True,
    skip_missing: bool = False,
) -> Path:
    """Create symlink structure for dataset and return the path to test.

    This function wraps create_lerobot_symlink_structure and can be used by both
    local mode and distributed client mode.

    Args:
        source_path: Source dataset directory (convert_path)
        target_dir: Target directory for symlinks (default: {source}_symlink)
        relative: Use relative symlinks (default: True)
        skip_missing: Skip missing files during symlink creation (default: False)

    Returns:
        Path to the symlink directory (the path to test with dataloader)

    Raises:
        Exception: If symlink creation fails
    """
    from robocoin_dataset.dataloader.make_symlink import (
        create_lerobot_symlink_structure,
    )

    source = Path(source_path)
    target = target_dir if target_dir is not None else source.parent / f"{source.name}_symlink"

    create_lerobot_symlink_structure(
        source_dir=source,
        target_dir=target,
        relative=relative,
        skip_missing=skip_missing,
    )

    return target


def create_lerobot_dataset(
    repo_id: str,
    root: str | Path | None = None,
    episodes: list[int] | None = None,
    image_transforms: "callable | None" = None,
    delta_timestamps: dict[list[float]] | None = None,
    tolerance_s: float = 0.001,
    revision: str | None = None,
    force_cache_sync: bool = False,
    download_videos: bool = True,
    video_backend: str = "auto",
    batch_encoding_size: int = 1,
) -> "LeRobotDataset":
    """Create a LeRobotDataset with optional auto backend fallback."""
    if LeRobotDataset is None:
        raise RuntimeError(
            "LeRobotDataset is not available. Ensure third_parties/robocoin-lerobot is on PYTHONPATH."
        )

    # Helper to build dataset with a specific backend
    def _build(backend: str) -> "LeRobotDataset":
        return LeRobotDataset(
            repo_id=repo_id,
            root=Path(root) if root is not None else None,
            episodes=episodes,
            image_transforms=image_transforms,
            delta_timestamps=delta_timestamps,
            tolerance_s=tolerance_s,
            revision=revision,
            force_cache_sync=force_cache_sync,
            download_videos=download_videos,
            video_backend=backend,
            batch_encoding_size=batch_encoding_size,
        )

    if video_backend != "auto":
        ds = _build(video_backend)
        # Attach chosen backend metadata for downstream UIs/CLIs
        try:
            setattr(ds, "robocoin_video_backend", video_backend)
            setattr(ds, "robocoin_video_backend_reason", "user_selected")
        except Exception:
            pass
        return ds

    # Auto: prefer torchcodec, then fallback to pyav on failure
    try:
        ds = _build("torchcodec")
        # Probe a single item to trigger video decoding if any video keys exist
        if len(ds.meta.video_keys) > 0 and ds.num_frames > 0:
            _ = ds[0]
        try:
            setattr(ds, "robocoin_video_backend", "torchcodec")
            setattr(ds, "robocoin_video_backend_reason", "ok")
        except Exception:
            pass
        return ds
    except Exception as e:
        # Fallback to pyav
        ds = _build("pyav")
        try:
            setattr(ds, "robocoin_video_backend", "pyav")
            setattr(ds, "robocoin_video_backend_reason", f"torchcodec failed: {repr(e)}")
        except Exception:
            pass
        return ds


# =============================
# Task category for DB-backed dataloader detection
# =============================
TASK_CATEGORY = "dataloader_detection"

# =============================
# Default DB path
# =============================
try:
    _here = Path(__file__).resolve()
    _repo_root = _here.parents[3]
    DEFAULT_DB_FILE = (
        (_repo_root / "examples" / "dataloader_test" / "datasets_new.db").expanduser().absolute()
    )
except Exception:
    DEFAULT_DB_FILE = Path("examples/dataloader_test/datasets_new.db").expanduser().absolute()


def _sync_dataloader_detection_tasks(
    session: Session,
    logger: logging.Logger | None = None,
) -> None:
    """Mark datasets requiring dataloader detection as pending and align versions.

    ##############################################################################
    # HERE : version_ps = data_merge_version                                     #
    ##############################################################################

    Trigger rules (STRICT REQUIREMENTS):
      - data_merge_status must be COMPLETED
      - convert_status must be COMPLETED
      - data_loader_detection_status is NULL (never tested), PENDING, or COMPLETED but outdated

    WARNING: NULL data_loader_detection_status is ILLEGAL but handled for robustness.
    """
    _logger = logger or logging.getLogger(__name__)

    query = session.query(DatasetDB).filter(
        and_(
            DatasetDB.data_merge_status == TaskStatus.COMPLETED,
            DatasetDB.convert_status == TaskStatus.COMPLETED,
            or_(
                # NEW: Match records that have never been tested (NULL status)
                DatasetDB.data_loader_detection_status == None,  # noqa: E711
                # Match records explicitly marked as PENDING
                DatasetDB.data_loader_detection_status == TaskStatus.PENDING,
                # Match records that were COMPLETED but are now outdated
                and_(
                    DatasetDB.data_loader_detection_status == TaskStatus.COMPLETED,
                    DatasetDB.data_loader_detection_version_ps < DatasetDB.data_merge_version,
                    # FIXED: dlder_ps < data_merge_version not dlder_ps < convert_version.
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


def _gen_one_dataloader_detection_task(session: Session) -> tuple[str | None, str | None]:
    """Claim one pending dataset and transition it to PROCESSING.

    ##############################################################################
    # HERE : version = version + 1                                               #
    ##############################################################################

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
    item.data_loader_detection_version = (
        item.data_loader_detection_version or 0
    ) + 1  # Increment version when claiming the task
    session.commit()
    return item.dataset_uuid, item.convert_path


def _parse_episode_specification(
    episode_spec: str | int | list[int] | None,
    total_episodes: int,
) -> list[int]:
    """Parse episode specification into list of episode indices.

    Args:
        episode_spec: Episode specification in various formats:
            - None or "all": all episodes [0, 1, ..., total_episodes-1]
            - int: single episode (e.g., 0)
            - list[int]: specific episodes (e.g., [0, 1, 2])
            - str "0": single episode 0
            - str "0,1,2": comma-separated episodes
            - str "0-5": range (inclusive) [0, 1, 2, 3, 4, 5]
            - str "0-5,10,15-17": mixed notation
        total_episodes: Total number of episodes in dataset

    Returns:
        Sorted list of unique episode indices

    Raises:
        ValueError: If specification is invalid or episodes out of range
    """
    if episode_spec is None or (isinstance(episode_spec, str) and episode_spec.lower() == "all"):
        return list(range(total_episodes))

    if isinstance(episode_spec, int):
        if episode_spec < 0 or episode_spec >= total_episodes:
            raise ValueError(f"Episode {episode_spec} out of range [0, {total_episodes - 1}]")
        return [episode_spec]

    if isinstance(episode_spec, list):
        for ep in episode_spec:
            if not isinstance(ep, int) or ep < 0 or ep >= total_episodes:
                raise ValueError(f"Episode {ep} out of range [0, {total_episodes - 1}]")
        return sorted(set(episode_spec))

    if isinstance(episode_spec, str):
        # Parse string specification
        episodes = []
        parts = episode_spec.split(",")
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if "-" in part and not part.startswith("-"):
                # Range notation: "0-5"
                try:
                    start_str, end_str = part.split("-", 1)
                    start = int(start_str.strip())
                    end = int(end_str.strip())
                    if start > end:
                        raise ValueError(f"Invalid range: {part} (start > end)")
                    episodes.extend(range(start, end + 1))
                except ValueError as e:
                    raise ValueError(f"Invalid range specification: {part}") from e
            else:
                # Single episode
                try:
                    episodes.append(int(part))
                except ValueError as e:
                    raise ValueError(f"Invalid episode number: {part}") from e

        # Validate range
        for ep in episodes:
            if ep < 0 or ep >= total_episodes:
                raise ValueError(f"Episode {ep} out of range [0, {total_episodes - 1}]")

        return sorted(set(episodes))

    raise ValueError(f"Invalid episode specification type: {type(episode_spec)}")


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
        ds = create_lerobot_dataset(repo_id=str(repo_path))
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
    create_symlinks: bool = True,
    symlink_target_dir: Path | None = None,
    symlink_relative: bool = True,
    symlink_skip_missing: bool = False,
    logger: logging.Logger | None = None,
) -> dict:
    """Process all pending dataloader detection tasks in batch (local mode).

    Workflow for each dataset:
    1. Sync tasks (_sync_dataloader_detection_tasks)
    2. Loop until no tasks:
       a. Claim one task (_gen_one_dataloader_detection_task) → PROCESSING
       b. Optionally create symlinks (_prepare_symlinks)
       c. Run detection (_run_dataloader_detection)
       d. Update status to COMPLETED/FAILED

    Args:
        db_file: Path to database
        episodes: Episodes to test (default: "all")
        strict_mode: Fail immediately on first error (default: False)
        batch_size: Batch size for dataloader (default: 32)
        num_workers: Number of dataloader workers (default: 0)
        create_symlinks: Whether to create symlinks (default: True)
        symlink_target_dir: Target directory for symlinks (default: None = auto)
        symlink_relative: Use relative symlinks (default: True)
        symlink_skip_missing: Skip missing files in symlinks (default: False)
        logger: Logger instance (default: None)

    Returns:
        {
            "datasets_processed": int,
            "succeeded": [uuid, ...],
            "failed": [(uuid, error_msg), ...],
        }
    """
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

        # Prepare path (with optional symlinks)
        try:
            if create_symlinks:
                test_path = _prepare_symlinks(
                    source_path=convert_path,
                    target_dir=symlink_target_dir,
                    relative=symlink_relative,
                    skip_missing=symlink_skip_missing,
                )
                _logger.info(f"  Created symlinks at: {test_path}")
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


class DataloaderDbProcess:
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
        ds_uuid = task_content.get(DATASET_UUID)
        # Client execution state: did the client process crash/throw exception?
        client_execution_status = task_result_content.get(TASK_RESULT_STATUS)

        # Level 1: Check if client crashed (process-level failure)
        if client_execution_status == TASK_FAILED:
            db_status = TaskStatus.FAILED
            db_error_message = task_result_content.get(ERR_MSG, "Client execution failed")
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


class DataloaderDbClient(TaskClient):
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
        repo_path = task_content.get(LEFORMAT_PATH)

        # Get configurable parameters (with defaults)
        episodes = task_content.get("episodes", "all")
        strict_mode = task_content.get("strict_mode", False)
        batch_size = task_content.get("batch_size", 32)
        num_workers = task_content.get("num_workers", 0)

        # Symlink parameters (optional, default: no symlinks in distributed mode)
        create_symlinks = task_content.get("create_symlinks", False)

        # Prepare path (with optional symlinks)
        if create_symlinks:
            symlink_relative = task_content.get("symlink_relative", True)
            symlink_skip_missing = task_content.get("symlink_skip_missing", False)
            test_path = _prepare_symlinks(
                source_path=repo_path,
                relative=symlink_relative,
                skip_missing=symlink_skip_missing,
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
