"""Dataset utilities for LeRobot datasets.

This module provides utilities for:
- Creating LeRobot datasets with auto backend selection
- Episode sampling with downsampling support
- Hardlink preparation for dataset structures
- Worker initialization for DataLoader
- Dataset detection and validation using EpisodeSampler with downsampling
"""

import logging
import os
import sys
from collections.abc import Iterator
from contextlib import redirect_stdout
from pathlib import Path
from typing import TYPE_CHECKING

import torch

from robocoin_dataset.hardlink.prepare_hardlink import (
    prepare_hardlink_for_task,
)

if TYPE_CHECKING:
    pass

######################### Logging setup #########################

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

######################### business logic functions #########################

def _set_backend_metadata(ds: "LeRobotDataset", backend: str, reason: str) -> None:
    """Set backend metadata on dataset (best-effort, silently ignore failures)."""
    try:
        setattr(ds, "robocoin_video_backend", backend)
        setattr(ds, "robocoin_video_backend_reason", reason)
    except Exception:
        pass


class EpisodeSampler(torch.utils.data.Sampler):  # type: ignore

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

    @staticmethod
    def calculate_sample_count(
        dataset: "LeRobotDataset",
        episode_index: int,
        sample_ratio: float = 1.0,
    ) -> int:
        """Calculate number of frames that will be sampled for an episode.

        Args:
            dataset: LeRobot dataset
            episode_index: Episode index
            sample_ratio: Sample ratio (0.0-1.0)

        Returns:
            Number of frames that will be sampled
        """
        from_idx = dataset.episode_data_index["from"][episode_index].item()
        to_idx = dataset.episode_data_index["to"][episode_index].item()
        total_frames = to_idx - from_idx

        if sample_ratio == 1.0:
            return total_frames

        return max(1, int(total_frames * sample_ratio))

def create_episode_dataloader(
    dataset: "LeRobotDataset",
    episode_index: int,
    batch_size: int = 32,
    num_workers: int = 0,
    sample_ratio: float = 1.0,
) -> torch.utils.data.DataLoader:

    episode_sampler = EpisodeSampler(dataset, episode_index, sample_ratio)
    return torch.utils.data.DataLoader(
        dataset,
        num_workers=num_workers,
        batch_size=batch_size,
        sampler=episode_sampler,
        worker_init_fn=_worker_init_suppress_output if num_workers > 0 else None,
    )


def run_local_batch_detection(
    db_file: str | Path,
    episodes: str = "all",
    sample_ratio: float = 0.1,
    batch_size: int = 32,
    num_workers: int = 0,
    hardlink_target_dir: Path | None = None,
    logger: logging.Logger | None = None,
    summary_logger: logging.Logger | None = None,
) -> dict:
    """Process all pending dataloader detection tasks in batch (local mode).

    Workflow for each dataset:
    1. Sync tasks → Claim one task → PROCESSING
    2. Prepare hardlinks (find existing or create new)
    3. Run detection (fast detection with sampling)
    4. Update status → COMPLETED/FAILED

    Args:
        db_file: Path to database
        episodes: Episodes to test (default: "all")
        sample_ratio: Sample ratio for detection (default: 0.1 = 10%)
        batch_size: Batch size for dataloader (default: 32)
        num_workers: Number of dataloader workers (default: 0)
        hardlink_target_dir: Target directory for hardlinks (default: None = auto)
        logger: Logger instance (default: None)

    Returns:
        {
            "datasets_processed": int,
            "succeeded": [uuid, ...],
            "failed": [(uuid, error_msg), ...],
            "total_time_s": float,
            "total_frames": int,
            "avg_time_per_frame_s": float,
        }
    """
    import time

    from robocoin_dataset.database.database import DatasetDatabase
    from robocoin_dataset.dataloader.dataloader import (
        _gen_one_dataloader_detection_task,
        _sync_dataloader_detection_tasks,
    )

    _logger = logger or logging.getLogger(__name__)
    db = DatasetDatabase(Path(db_file).expanduser().absolute())

    succeeded, failed, datasets_processed = [], [], 0
    batch_start_time = time.perf_counter()
    total_frames = 0

    while True:
        # Sync and claim one task
        with db.with_session() as session:
            _sync_dataloader_detection_tasks(session, logger=_logger)
            dataset_uuid, convert_path = _gen_one_dataloader_detection_task(session)

        if not dataset_uuid or not convert_path:
            break

        datasets_processed += 1
        _logger.info(f"Processing dataset {datasets_processed}: {dataset_uuid}")

        # Prepare path with hardlinks (find existing or create new)
        try:
            test_path = _prepare_dataset_path(
                db, dataset_uuid, convert_path, hardlink_target_dir, _logger
            )
        except Exception as e:
            error_msg = f"Hardlink preparation failed: {e}"
            _logger.error(error_msg)
            _mark_task_failed(db, dataset_uuid, error_msg)
            failed.append((dataset_uuid, error_msg))
            continue

        # Run detection
        result = _run_detection(
            test_path, episode_indices=episodes, sample_ratio=sample_ratio,
            batch_size=batch_size, num_workers=num_workers,
        )

        # Update database
        success, error_msg = _update_task_status(db, dataset_uuid, result, _logger)
        if success:
            succeeded.append(dataset_uuid)
            # Accumulate frame counts for batch statistics
            total_frames += result.get('total_frames_sampled', 0)
            # Log per-dataset summary
            if summary_logger:
                summary_logger.info(
                    f"✅ {dataset_uuid}: {result.get('total_frames_sampled', 0)} frames, "
                    f"{result.get('total_time_s', 0):.2f}s, "
                    f"{len(result.get('episodes_tested', []))} episodes, "
                    f"backend={result.get('backend', 'unknown')}"
                )
        else:
            failed.append((dataset_uuid, error_msg))
            if summary_logger:
                summary_logger.info(f"❌ {dataset_uuid}: {error_msg}")

    # Calculate batch statistics
    batch_elapsed = time.perf_counter() - batch_start_time
    avg_time_per_frame = batch_elapsed / total_frames if total_frames > 0 else 0.0

    _logger.info(
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
        _set_backend_metadata(ds, video_backend, "user_selected")
        return ds

    # Auto: prefer torchcodec, then fallback to pyav on failure
    try:
        ds = _build("torchcodec")
        # Probe a single item to trigger video decoding if any video keys exist
        if len(ds.meta.video_keys) > 0 and ds.num_frames > 0:
            _ = ds[0]
        _set_backend_metadata(ds, "torchcodec", "ok")
        return ds
    except Exception as e:
        # Fallback to pyav
        ds = _build("pyav")
        _set_backend_metadata(ds, "pyav", f"torchcodec failed: {repr(e)}")
        return ds

######################### helper functions #########################

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


def _prepare_dataset_path(
    db: "object",
    dataset_uuid: str,
    convert_path: str,
    hardlink_target_dir: Path | None,
    logger: logging.Logger,
) -> Path:
    """Prepare dataset path with hardlinks (legacy wrapper).

    This is a legacy wrapper that adds logging around prepare_hardlink_for_task.
    New code should use prepare_hardlink_for_task directly.

    Raises:
        FileNotFoundError: If source dataset is missing required LeRobotDataset files
    """
    result_path = prepare_hardlink_for_task(db, dataset_uuid, convert_path, hardlink_target_dir)
    logger.info(f"Using hardlinks: {result_path}")
    return result_path


def _update_task_status(
    db: "object",
    dataset_uuid: str,
    result: dict,
    logger: logging.Logger,
) -> tuple[bool, str | None]:
    """Update database with detection result.

    Returns:
        (success, error_msg) tuple
    """
    from robocoin_dataset.database.models import DatasetDB, TaskStatus

    with db.with_session() as session:
        item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
        if not item:
            return False, "Dataset not found in database"

        if result["success"]:
            item.data_loader_detection_status = TaskStatus.COMPLETED
            item.data_loader_detection_err_msg = None
            frames_count = result.get('total_frames_sampled', 0)

            # Performance summary
            time_total = result.get('total_time_s', 0)
            time_per_ep = result.get('time_per_episode_s', 0)
            time_per_frame = result.get('time_per_frame_s', 0)
            sample_ratio = result.get('sample_ratio', 1.0)
            backend = result.get('backend', 'unknown')

            logger.info(
                f"✅ {frames_count} frames in {len(result['episodes_tested'])} episodes | "
                f"{time_total:.2f}s total, {time_per_ep:.3f}s/ep, {time_per_frame*1000:.1f}ms/frame | "
                f"sample_ratio={sample_ratio:.2f}, backend={backend}"
            )
            session.commit()
            return True, None
        item.data_loader_detection_status = TaskStatus.FAILED
        error_msg = result.get("error_message", "Unknown error")
        item.data_loader_detection_err_msg = error_msg
        logger.error(f"❌ {error_msg}")
        session.commit()
        return False, error_msg


def _mark_task_failed(
    db: "object",
    dataset_uuid: str,
    error_msg: str,
) -> None:
    """Mark task as failed in database."""
    from robocoin_dataset.database.models import DatasetDB, TaskStatus

    with db.with_session() as session:
        item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
        if item:
            item.data_loader_detection_status = TaskStatus.FAILED
            item.data_loader_detection_err_msg = error_msg
            session.commit()


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


def _run_detection(
    repo_path: str | Path,
    episode_indices: str | int | list[int] | None = "all",
    sample_ratio: float = 0.1,
    batch_size: int = 32,
    num_workers: int = 0,
    client_id: str | None = None,
    tqdm_position: int = 0,
) -> dict:
    """Fast dataloader detection using episode sampling with downsampling.

    This is a lightweight detection method optimized for speed. It tests
    episodes using EpisodeSampler with sample_ratio < 1.0 to reduce frames tested.
    No detailed validation or error tracking - just checks if frames can be loaded.

    Use this for quick smoke tests or performance benchmarking.

    Memory management:
    - Explicitly cleans up dataloaders after each episode
    - Cleans up dataset in finally block
    - Forces garbage collection to prevent accumulation

    Args:
        client_id: Optional client identifier for multi-client progress bars
        tqdm_position: Base position for tqdm progress bars (client_id will use position*2 and position*2+1)
    """
    import gc
    import time

    try:
        from tqdm import tqdm  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "tqdm is required for dataloader detection. Install with: pip install tqdm"
        ) from e

    repo_path = Path(repo_path)
    start_time = time.perf_counter()

    result = {
        "success": False,
        "dataset_path": str(repo_path),
        "total_episodes_in_dataset": 0,
        "episodes_tested": [],
        "total_frames_sampled": 0,
        "sample_ratio": sample_ratio,
        "backend": "unknown",
        "error_message": None,
        "total_time_s": 0.0,
        "time_per_episode_s": 0.0,
        "time_per_frame_s": 0.0,
    }

    ds = None  # Initialize for finally block
    try:
        # Load dataset - local only (hardlink validation already done by create_or_validate_hardlinks)
        ds = create_lerobot_dataset(
            repo_id=repo_path.name,
            root=repo_path,
            download_videos=False,  # Never download from HuggingFace
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

        # Calculate total frames to be sampled for progress bar
        total_frames_to_sample = sum(
            EpisodeSampler.calculate_sample_count(ds, ep_idx, sample_ratio)
            for ep_idx in episodes_to_test
        )

        # Prepare progress bar descriptions with client info
        dataset_name = repo_path.name[:30]  # Truncate long dataset names
        client_prefix = f"[{client_id}] " if client_id else ""

        # Progress bars (always enabled - tqdm is required)
        # Use tqdm_position * 2 to leave space between different clients' bars
        episode_progress = tqdm(
            total=len(episodes_to_test),
            desc=f"{client_prefix}🚀 {dataset_name}",
            unit="ep",
            file=sys.stderr,
            position=tqdm_position * 2,
            leave=False,  # Clear bar when done to avoid clutter
        )
        frame_progress = tqdm(
            total=total_frames_to_sample,
            desc=f"{client_prefix}📹 Frames",
            unit="fr",
            file=sys.stderr,
            position=tqdm_position * 2 + 1,
            leave=False,  # Clear bar when done to avoid clutter
        )

        # Test each episode with downsampling
        for ep_num, ep_idx in enumerate(episodes_to_test, 1):
            # Update frame progress bar with current episode
            frame_progress.set_description(f"{client_prefix}📹 Ep {ep_idx}/{total_episodes}")

            # Create dataloader with EpisodeSampler using sample_ratio
            dl = create_episode_dataloader(
                ds,
                episode_index=ep_idx,
                batch_size=batch_size,
                num_workers=num_workers,
                sample_ratio=sample_ratio,
            )

            try:
                # Iterate through batches (simple test - no validation)
                # Suppress stdout to hide verbose output from third-party libraries (e.g., lerobot video decoding)
                with open(os.devnull, "w") as devnull, redirect_stdout(devnull):
                    for batch in dl:
                        batch_frames = len(batch["index"]) if "index" in batch else 1
                        result["total_frames_sampled"] += batch_frames
                        frame_progress.update(batch_frames)
            finally:
                # CRITICAL: Clean up dataloader after each episode to prevent memory accumulation
                # This is especially important with num_workers > 0 (worker processes)
                del dl
                gc.collect()

            episode_progress.update(1)

        # Close progress bars
        episode_progress.close()
        frame_progress.close()

        # Calculate timing statistics
        elapsed_time = time.perf_counter() - start_time
        result["total_time_s"] = elapsed_time
        result["time_per_episode_s"] = elapsed_time / len(episodes_to_test) if episodes_to_test else 0.0
        result["time_per_frame_s"] = elapsed_time / result["total_frames_sampled"] if result["total_frames_sampled"] > 0 else 0.0

        result["success"] = True
        return result

    except Exception as e:
        elapsed_time = time.perf_counter() - start_time
        result["total_time_s"] = elapsed_time
        result["error_message"] = str(e)
        result["success"] = False
        print(f"❌ Fast detection failed: {e}", file=sys.stderr)
        return result

    finally:
        # CRITICAL: Clean up dataset to prevent memory leaks
        # This frees video decoder resources, file handles, and cached data
        if ds is not None:
            del ds
        gc.collect()
