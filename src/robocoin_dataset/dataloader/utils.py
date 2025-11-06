"""Dataset utilities for LeRobot datasets.

This module provides utilities for:
- Creating LeRobot datasets with auto backend selection
- Episode sampling with downsampling support
- Hardlink preparation for dataset structures
- Worker initialization for DataLoader
- Dataset detection and validation:
  - _run_detection: Fast detection using EpisodeSampler with downsampling (default)
  - _run_comprehensive_detection: Comprehensive validation of all episodes
"""

import logging
import os
import sys
import traceback
from collections.abc import Iterator
from contextlib import redirect_stdout
from pathlib import Path
from typing import TYPE_CHECKING

import torch

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Suppress noisy INFO logs from httpx (used by HuggingFace datasets)
# These logs show 404s when checking for optional files - doesn't affect functionality
logging.getLogger("httpx").setLevel(logging.WARNING)

# Best-effort: auto-add vendored lerobot path for local runs without PYTHONPATH
try:
    _here_lr = Path(__file__).resolve()
    _repo_root_lr = _here_lr.parents[3]
    _vendored_lr = _repo_root_lr / "third_parties" / "robocoin-lerobot" / "src"
    if _vendored_lr.is_dir() and str(_vendored_lr) not in sys.path:
        sys.path.insert(0, str(_vendored_lr))
except Exception:
    pass

try:
    # Prefer the vendored lerobot package in third_parties if available on PYTHONPATH
    from lerobot.datasets.lerobot_dataset import LeRobotDataset  # type: ignore
except Exception:  # pragma: no cover
    LeRobotDataset = None  # type: ignore


class EpisodeSampler(torch.utils.data.Sampler):  # type: ignore
    """Episode sampler referencing lerobot's visualize_dataset logic.

    Selects the frame indices belonging to a given episode.

    Args:
        dataset: LeRobotDataset instance
        episode_index: Index of the episode to sample from
        sample_ratio: Ratio of frames to sample (0.0 to 1.0). Default is 1.0 (all frames).
                     Frames are evenly distributed across the episode when downsampling.
    """

    def __init__(self, dataset: "LeRobotDataset", episode_index: int, sample_ratio: float = 1.0) -> None:
        if not 0.0 <= sample_ratio <= 1.0:
            raise ValueError(f"sample_ratio must be between 0 and 1, got {sample_ratio}")

        from_idx = dataset.episode_data_index["from"][episode_index].item()
        to_idx = dataset.episode_data_index["to"][episode_index].item()

        if sample_ratio == 1.0:
            self.frame_ids = list(range(from_idx, to_idx))
        else:
            total_frames = to_idx - from_idx
            num_samples = max(1, int(total_frames * sample_ratio))

            if num_samples == 1:
                self.frame_ids = [from_idx]
            else:
                step = (total_frames - 1) / (num_samples - 1)
                self.frame_ids = [from_idx + int(i * step) for i in range(num_samples)]

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
    sample_ratio: float = 1.0,
) -> torch.utils.data.DataLoader:
    """Create a DataLoader for a specific episode with optional downsampling.

    Args:
        dataset: LeRobotDataset instance
        episode_index: Index of the episode to load
        batch_size: Batch size for the DataLoader
        num_workers: Number of worker processes
        sample_ratio: Ratio of frames to sample (0.0 to 1.0)

    Returns:
        Configured DataLoader for the episode
    """
    episode_sampler = EpisodeSampler(dataset, episode_index, sample_ratio)
    return torch.utils.data.DataLoader(
        dataset,
        num_workers=num_workers,
        batch_size=batch_size,
        sampler=episode_sampler,
        worker_init_fn=_worker_init_suppress_output if num_workers > 0 else None,
    )


def prepare_hardlink_db(
    source_path: str | Path,
    dataset_uuid: str,
    target_dir: Path | None = None,
    db_session: "Session | None" = None,
) -> Path:
    """Prepare hardlinks with database integration.

    Queries DB for existing hardlink path, validates/creates hardlinks, saves to DB.

    Args:
        source_path: Source dataset directory
        dataset_uuid: Dataset UUID for database lookup
        target_dir: Target directory for hardlinks (optional)
        db_session: SQLAlchemy session for database operations (optional)

    Returns:
        Path to the hardlink directory
    """
    from robocoin_dataset.database.models import DatasetHardLinkDB

    src = Path(source_path)

    # Query hardlink path from database
    existing_path = None
    if db_session:
        record = (
            db_session.query(DatasetHardLinkDB)
            .filter(DatasetHardLinkDB.dataset_uuid == dataset_uuid)
            .first()
        )
        if record and record.hard_link_path:
            existing_path = Path(record.hard_link_path)

    # Determine target path
    dst = existing_path or target_dir or src.parent / f"{src.name}_hardlink"

    # Validate and create hardlinks (local operation)
    result_path = _prepare_hardlinks(src, dst)

    # Save hardlink path to database
    if db_session:
        if record:
            record.hard_link_path = str(result_path.absolute())
        else:
            record = DatasetHardLinkDB(
                dataset_uuid=dataset_uuid,
                hard_link_path=str(result_path.absolute()),
            )
            db_session.add(record)
        db_session.commit()

    return result_path


def _prepare_hardlinks(src: Path, dst: Path) -> Path:
    """Local function: validate existing hardlinks or create new ones.

    Args:
        src: Source dataset directory
        dst: Destination hardlink directory

    Returns:
        Path to the hardlink directory
    """
    from robocoin_dataset.hardlink.make_hardlink import (
        RepoHardLinkCorresp,
        create_hardlinks_from_correspondence,
    )
    from robocoin_dataset.hardlink.validate_hardlink import validate_hardlink

    logger = logging.getLogger(__name__)
    hardlink_corresp = RepoHardLinkCorresp()

    # Validate -> Create if needed
    if dst.exists():
        try:
            if validate_hardlink(src, dst, hardlink_corresp):
                logger.info(f"Reusing existing hardlinks: {dst}")
                return dst
        except Exception:
            pass

    # Create hardlinks
    logger.info(f"Creating hardlinks: {src} → {dst}")
    create_hardlinks_from_correspondence(src, dst, hardlink_corresp)
    logger.info(f"Hardlinks created successfully: {dst}")

    return dst

def _validate_single_episode(
    ds: "LeRobotDataset",
    ep_idx: int,
    video_keys: list[str],
    batch_size: int,
    num_workers: int,
    overall_progress: "object | None" = None,
) -> tuple[bool, int, str | None]:
    """Validate a single episode by iterating through all frames.

    Args:
        ds: LeRobotDataset instance
        ep_idx: Episode index to validate
        video_keys: List of video keys to verify in each batch
        batch_size: Batch size for dataloader
        num_workers: Number of dataloader workers
        overall_progress: Optional overall progress bar to update

    Returns:
        Tuple of (success, frames_validated, error_message)
    """
    try:
        from tqdm import tqdm  # type: ignore
    except Exception:
        tqdm = None  # type: ignore

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

        # Iterate through all frames (simple core loop like simple_data_loader.py)
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

        return True, frames_validated, None

    except Exception as e:
        return False, 0, str(e)

def run_local_batch_detection(
    db_file: str | Path,
    episodes: str = "all",
    comprehensive: bool = False,
    sample_ratio: float = 0.1,
    strict_mode: bool = False,
    batch_size: int = 32,
    num_workers: int = 0,
    create_hardlinks: bool = True,
    hardlink_target_dir: Path | None = None,
    logger: logging.Logger | None = None,
) -> dict:
    """Process all pending dataloader detection tasks in batch (local mode).

    Workflow for each dataset:
    1. Sync tasks (_sync_dataloader_detection_tasks)
    2. Loop until no tasks:
       a. Claim one task (_gen_one_dataloader_detection_task) → PROCESSING
       b. Optionally prepare hardlinks (prepare_hardlink_db) with database integration
       c. Run detection (_run_detection by default, or _run_comprehensive_detection if comprehensive=True)
       d. Update status to COMPLETED/FAILED

    Args:
        db_file: Path to database
        episodes: Episodes to test (default: "all")
        comprehensive: Use comprehensive detection (default: False, use fast detection)
        sample_ratio: Sample ratio for fast detection (default: 0.1 = 10%). Ignored if comprehensive=True
        strict_mode: Fail immediately on first error (default: False). Only used in comprehensive mode
        batch_size: Batch size for dataloader (default: 32)
        num_workers: Number of dataloader workers (default: 0)
        create_hardlinks: Whether to use hardlinks (default: True)
        hardlink_target_dir: Target directory for hardlinks (default: None = auto)
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
    from robocoin_dataset.dataloader.dataloader import (
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
            break

        datasets_processed += 1
        _logger.info(f"Processing dataset {datasets_processed}: {dataset_uuid}")

        # Prepare path (with optional hardlinks using database integration)
        try:
            if create_hardlinks:
                with db.with_session() as session:
                    test_path = prepare_hardlink_db(
                        source_path=convert_path,
                        dataset_uuid=dataset_uuid,
                        target_dir=hardlink_target_dir,
                        db_session=session,
                    )
                _logger.info(f"Using hardlinks: {test_path}")
            else:
                test_path = Path(convert_path)
        except Exception as e:
            err_msg = f"Hardlink preparation failed: {e}"
            _logger.error(err_msg)
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
        if comprehensive:
            # Comprehensive detection: test all frames with validation
            result = _run_comprehensive_detection(
                test_path,
                episode_indices=episodes,
                strict_mode=strict_mode,
                batch_size=batch_size,
                num_workers=num_workers,
            )
        else:
            # Fast detection: test with downsampling
            result = _run_detection(
                test_path,
                episode_indices=episodes,
                sample_ratio=sample_ratio,
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
                    # Handle different result structures (fast vs comprehensive)
                    frames_count = result.get('total_frames_validated') or result.get('total_frames_sampled', 0)
                    _logger.info(
                        f"✅ {frames_count} frames in "
                        f"{len(result['episodes_tested'])} episodes"
                    )
                    succeeded.append(dataset_uuid)
                else:
                    item.data_loader_detection_status = TaskStatus.FAILED
                    item.data_loader_detection_err_msg = result.get(
                        "error_summary", result.get("error_message", "Unknown error")
                    )
                    _logger.error(f"❌ {item.data_loader_detection_err_msg}")
                    failed.append((dataset_uuid, item.data_loader_detection_err_msg))
                session.commit()

    _logger.info(f"Batch processing complete: {len(succeeded)} succeeded, {len(failed)} failed")

    return {
        "datasets_processed": datasets_processed,
        "succeeded": succeeded,
        "failed": failed,
    }


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
    """Create a LeRobotDataset with optional auto backend fallback.

    Returns:
        LeRobotDataset instance with auto-selected video backend.
    """
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

def _run_comprehensive_detection(
    repo_path: str | Path,
    episode_indices: str | int | list[int] | None = "all",
    strict_mode: bool = False,
    batch_size: int = 32,
    num_workers: int = 0,
) -> dict:
    """Comprehensive validation of LeRobot dataset by loading and decoding specified episodes.

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
    from robocoin_dataset.dataloader.dataloader import _parse_episode_specification

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
        ds = create_lerobot_dataset(
            repo_id=repo_path.name,
            root=repo_path,
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
            print(f"❌ {error_msg}", file=sys.stderr)
            if strict_mode:
                raise ValueError(error_msg) from e
            return result

        result["episodes_tested"] = episodes_to_test

        if not episodes_to_test:
            result["success"] = True
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

        # Test each episode (thin loop - core logic extracted to helper)
        for ep_idx in episodes_to_test:
            success, frames_validated, error_message = _validate_single_episode(
                ds=ds,
                ep_idx=ep_idx,
                video_keys=video_keys,
                batch_size=batch_size,
                num_workers=num_workers,
                overall_progress=overall_progress,
            )

            if success:
                # Record success
                result["episodes_succeeded"].append(ep_idx)
                result["frames_per_episode"][ep_idx] = frames_validated
                result["total_frames_validated"] += frames_validated
            else:
                # Record failure
                error_detail = {
                    "type": "episode_validation_error",
                    "episode_idx": ep_idx,
                    "message": error_message,
                    "traceback": traceback.format_exc(),
                }
                result["errors"].append(error_detail)
                result["episodes_failed"].append(ep_idx)
                result["frames_per_episode"][ep_idx] = 0

                # Print concise error
                if overall_progress is not None:
                    overall_progress.write(f"❌ Episode {ep_idx}: {error_message}")
                else:
                    print(f"❌ Episode {ep_idx}: {error_message}", file=sys.stderr)

                if strict_mode:
                    if overall_progress is not None:
                        overall_progress.close()
                    raise RuntimeError(f"Episode {ep_idx} validation failed: {error_message}")

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

        print(f"❌ FATAL ERROR: {error_msg}", file=sys.stderr)

        if strict_mode:
            raise

        return result

def _run_detection(
    repo_path: str | Path,
    episode_indices: str | int | list[int] | None = "all",
    sample_ratio: float = 0.1,
    batch_size: int = 32,
    num_workers: int = 0,
) -> dict:
    """Fast dataloader detection using episode sampling with downsampling.

    This is a lightweight detection method optimized for speed. It tests
    episodes using EpisodeSampler with sample_ratio < 1.0 to reduce frames tested.
    No detailed validation or error tracking - just checks if frames can be loaded.

    Use this for quick smoke tests or performance benchmarking.
    For comprehensive validation, use _run_comprehensive_detection instead.

    Args:
        repo_path: Path to LeRobot dataset directory
        episode_indices: Episodes to test (default: "all")
            - None or "all": test all episodes
            - int: single episode (e.g., 0)
            - list[int]: specific episodes (e.g., [0, 1, 2])
            - str: "0", "0,1,2", "0-5", etc.
        sample_ratio: Ratio of frames to sample per episode (default: 0.1 = 10%)
        batch_size: Batch size for dataloader (default: 32)
        num_workers: Number of dataloader workers (default: 0)

    Returns:
        Simple result dictionary:
        {
            "success": bool,
            "dataset_path": str,
            "total_episodes_in_dataset": int,
            "episodes_tested": list[int],
            "total_frames_sampled": int,
            "sample_ratio": float,
            "backend": str,
            "error_message": str | None,
        }
    """
    from robocoin_dataset.dataloader.dataloader import _parse_episode_specification

    try:
        from tqdm import tqdm  # type: ignore
    except Exception:
        tqdm = None  # type: ignore

    repo_path = Path(repo_path)

    result = {
        "success": False,
        "dataset_path": str(repo_path),
        "total_episodes_in_dataset": 0,
        "episodes_tested": [],
        "total_frames_sampled": 0,
        "sample_ratio": sample_ratio,
        "backend": "unknown",
        "error_message": None,
    }

    try:
        # Load dataset
        ds = create_lerobot_dataset(
            repo_id=repo_path.name,
            root=repo_path,
        )
        result["backend"] = getattr(ds, "robocoin_video_backend", "unknown")

        # Get dataset metadata
        total_episodes = len(ds.episode_data_index["from"])
        result["total_episodes_in_dataset"] = total_episodes

        # Parse episode specification
        episodes_to_test = _parse_episode_specification(episode_indices, total_episodes)
        result["episodes_tested"] = episodes_to_test

        if not episodes_to_test:
            result["success"] = True
            return result

        # Progress bar
        if tqdm is not None:
            progress = tqdm(
                total=len(episodes_to_test),
                desc="🚀 Fast detection",
                unit="episode",
                file=sys.stderr,
            )
        else:
            progress = None

        # Test each episode with downsampling
        for ep_idx in episodes_to_test:
            # Create dataloader with EpisodeSampler using sample_ratio
            dl = create_episode_dataloader(
                ds,
                episode_index=ep_idx,
                batch_size=batch_size,
                num_workers=num_workers,
                sample_ratio=sample_ratio,
            )

            # Iterate through batches (simple test - no validation)
            # Suppress stdout to hide verbose output from third-party libraries (e.g., lerobot video decoding)
            with open(os.devnull, "w") as devnull, redirect_stdout(devnull):
                for batch in dl:
                    result["total_frames_sampled"] += len(batch["index"]) if "index" in batch else 1

            if progress is not None:
                progress.update(1)

        if progress is not None:
            progress.close()

        result["success"] = True
        return result

    except Exception as e:
        result["error_message"] = str(e)
        result["success"] = False
        print(f"❌ Fast detection failed: {e}", file=sys.stderr)
        return result
