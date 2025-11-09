"""Dataset utilities for LeRobot datasets.

This module provides utilities for:
- Creating LeRobot datasets.
- Episode sampling with downsampling support (single & multi-episode)
- Hardlink preparation for dataset structures
- Worker initialization for DataLoader
- Dataset detection using MultiEpisodeSampler
"""

import logging
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import torch

from robocoin_dataset.hardlink.prepare_hardlink import (
    prepare_hardlink_for_task,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

######################### Constants #########################

TASK_CATEGORY = "dataloader_detection"

######################### Logging setup #########################

# Suppress noisy INFO logs from httpx (used by HuggingFace datasets)
# These logs show 404s when checking for optional files - doesn't affect functionality
logging.getLogger("httpx").setLevel(logging.WARNING)

# Auto-add vendored lerobot to path and import
try:
    vendored_path = Path(__file__).resolve().parents[3] / "third_parties" / "robocoin-lerobot" / "src"
    if vendored_path.is_dir() and str(vendored_path) not in sys.path:
        sys.path.insert(0, str(vendored_path))
    from lerobot.datasets.lerobot_dataset import LeRobotDataset  # type: ignore
except Exception:
    LeRobotDataset = None  # type: ignore

######################### business logic functions #########################

class MultiEpisodeSampler(torch.utils.data.Sampler):  # type: ignore

    def __init__(
        self,
        dataset: "LeRobotDataset",
        episode_indices: list[int],
        sample_ratio: float = 1.0,
    ) -> None:
        if not 0.0 <= sample_ratio <= 1.0:
            raise ValueError(f"sample_ratio must be between 0 and 1, got {sample_ratio}")

        self.frame_ids = []
        self.episode_boundaries = []

        for ep_idx in episode_indices:
            from_idx = dataset.episode_data_index["from"][ep_idx].item()
            to_idx = dataset.episode_data_index["to"][ep_idx].item()

            start_pos = len(self.frame_ids)

            if sample_ratio == 1.0:
                episode_frames = list(range(from_idx, to_idx))
            else:
                total_frames = to_idx - from_idx
                num_samples = max(1, int(total_frames * sample_ratio))

                if num_samples == 1:
                    episode_frames = [from_idx]
                else:
                    step = (total_frames - 1) / (num_samples - 1)
                    episode_frames = [from_idx + int(i * step) for i in range(num_samples)]

            self.frame_ids.extend(episode_frames)
            self.episode_boundaries.append((ep_idx, start_pos, len(self.frame_ids)))

    def __iter__(self) -> Iterator:
        return iter(self.frame_ids)

    def __len__(self) -> int:
        return len(self.frame_ids)

def create_episode_dataloader(
    dataset: "LeRobotDataset",
    episode_index: int,
    batch_size: int = 32,
    num_workers: int = 0,
    sample_ratio: float = 1.0,
) -> torch.utils.data.DataLoader:

    episode_sampler = MultiEpisodeSampler(dataset, episode_index, sample_ratio)
    return torch.utils.data.DataLoader(
        dataset,
        num_workers=num_workers,
        batch_size=batch_size,
        sampler=episode_sampler,
        worker_init_fn=_worker_init_suppress_output if num_workers > 0 else None,
    )


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
    video_backend: str = "pyav",
    batch_encoding_size: int = 1,
) -> "LeRobotDataset":

    if LeRobotDataset is None:
        raise RuntimeError(
            "LeRobotDataset is not available."
        )

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
        video_backend=video_backend,
        batch_encoding_size=batch_encoding_size,
    )


def run_local_batch_detection(
    db_file: str | Path,
    summary_logger: logging.Logger,
    episodes: str = "all",
    sample_ratio: float = 0.1,
    batch_size: int = 32,
    num_workers: int = 0,
    hardlink_target_dir: Path | None = None,
    logger: logging.Logger | None = None,
) -> dict:

    import time

    from robocoin_dataset.database.database import DatasetDatabase
    from robocoin_dataset.database.models import DatasetDB, TaskStatus

    _logger = logger or logging.getLogger(__name__)
    db = DatasetDatabase(Path(db_file).expanduser().absolute())

    succeeded, failed, datasets_processed = [], [], 0
    batch_start_time = time.perf_counter()
    total_frames = 0

    # Process datasets until none remain
    while True:
        # Sync tasks and claim one
        with db.with_session() as session:
            _sync_dataloader_detection_tasks(session, logger=_logger)
            dataset_uuid, convert_path = _gen_one_dataloader_detection_task(session)

        if not dataset_uuid or not convert_path:
            break

        datasets_processed += 1
        _logger.info(f"Processing dataset {datasets_processed}: {dataset_uuid}")

        # Prepare hardlinks (find existing or create new)
        try:
            test_path = prepare_hardlink_for_task(
                db, dataset_uuid, convert_path, hardlink_target_dir
            )
            _logger.info(f"Using hardlinks: {test_path}")
        except Exception as e:
            error_msg = f"Hardlink preparation failed: {e}"
            _logger.error(error_msg)
            # Mark task as failed in database
            with db.with_session() as session:
                item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
                if item:
                    item.data_loader_detection_status = TaskStatus.FAILED
                    item.data_loader_detection_err_msg = error_msg
                    session.commit()
            failed.append((dataset_uuid, error_msg))
            summary_logger.info(f"❌ {dataset_uuid}: {error_msg}")
            continue

        # Run detection with configurable parameters
        result = _run_detection(
            test_path,
            episode_indices=episodes,
            sample_ratio=sample_ratio,
            batch_size=batch_size,
            num_workers=num_workers,
        )

        # Update database based on detection result
        if result.get("success"):
            # Mark task as success in database
            with db.with_session() as session:
                item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
                if item:
                    item.data_loader_detection_status = TaskStatus.COMPLETED
                    session.commit()
            succeeded.append(dataset_uuid)
            total_frames += result.get("total_frames_sampled", 0)
            if summary_logger:
                summary_logger.info(
                    f"✅ {dataset_uuid}: {result.get('total_frames_sampled', 0)} frames, "
                    f"{result.get('total_time_s', 0):.2f}s"
                )
            _logger.info(
                f"✅ Detection succeeded for {dataset_uuid}: "
                f"{result.get('total_frames_sampled', 0)} frames in {result.get('total_time_s', 0):.2f}s"
            )
        else:
            error_msg = result.get("error_message", "Unknown error")
            # Mark task as failed in database
            with db.with_session() as session:
                item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
                if item:
                    item.data_loader_detection_status = TaskStatus.FAILED
                    item.data_loader_detection_err_msg = error_msg
                    session.commit()
            failed.append((dataset_uuid, error_msg))
            summary_logger.info(f"❌ {dataset_uuid}: {error_msg}")
            _logger.error(f"❌ Detection failed for {dataset_uuid}: {error_msg}")

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


def _parse_episode_specification(
    episode_spec: str | int | list[int] | None,
    total_episodes: int,
) -> list[int]:
    """Parse episode specification: None/"all", int, list[int], "0,1,2", "0-5", "0-5,10".

    Returns sorted unique episode indices, validates range [0, total_episodes-1].
    """
    # Handle None or "all"
    if episode_spec is None or (isinstance(episode_spec, str) and episode_spec.lower() == "all"):
        return list(range(total_episodes))

    # Convert int to list for unified handling
    if isinstance(episode_spec, int):
        episode_spec = [episode_spec]

    # Parse list[int] or string
    if isinstance(episode_spec, list):
        episodes = episode_spec
    elif isinstance(episode_spec, str):
        episodes = []
        for part in episode_spec.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part and not part.startswith("-"):
                start, end = map(int, part.split("-", 1))
                if start > end:
                    raise ValueError(f"Invalid range: {part} (start > end)")
                episodes.extend(range(start, end + 1))
            else:
                episodes.append(int(part))
    else:
        raise ValueError(f"Invalid episode specification type: {type(episode_spec)}")

    # Validate range
    for ep in episodes:
        if ep < 0 or ep >= total_episodes:
            raise ValueError(f"Episode {ep} out of range [0, {total_episodes - 1}]")

    return sorted(set(episodes))


def _run_detection(
    repo_path: str | Path,
    episode_indices: str | int | list[int] | None = "all",
    sample_ratio: float = 0.1,
    batch_size: int = 32,
    num_workers: int = 0,
    client_id: str | None = None,
    tqdm_position: int = 0,
) -> dict:
    """Fast dataloader detection using multi-episode sampling."""
    import contextlib
    import gc
    import time

    from tqdm import tqdm  # type: ignore

    repo_path = Path(repo_path)
    start_time = time.perf_counter()
    result = {"success": False, "dataset_path": str(repo_path), "sample_ratio": sample_ratio,
              "backend": "pyav", "total_frames_sampled": 0}

    ds = None
    try:
        # Load dataset and parse episodes
        ds = create_lerobot_dataset(repo_id=repo_path.name, root=repo_path, download_videos=False)
        total_episodes = len(ds.episode_data_index["from"])
        episodes_to_test = _parse_episode_specification(episode_indices, total_episodes)

        result.update({
            "total_episodes_in_dataset": total_episodes,
            "episodes_tested": episodes_to_test,
        })

        if not episodes_to_test:
            result["success"] = True
            return result

        # Create sampler and dataloader
        sampler = MultiEpisodeSampler(ds, episodes_to_test, sample_ratio)
        dl = torch.utils.data.DataLoader(
            ds, num_workers=num_workers, batch_size=batch_size, sampler=sampler,
            worker_init_fn=_worker_init_suppress_output if num_workers > 0 else None,
        )

        # Run detection with progress bar (suppress stdout to avoid LeRobot prints)
        dataset_name = repo_path.name[:40]
        client_prefix = f"[{client_id}] " if client_id else ""

        with contextlib.redirect_stdout(open(os.devnull, "w")):
            for batch in tqdm(dl, total=len(dl), desc=f"{client_prefix}📦 {dataset_name}",
                            unit="batch", file=sys.stderr, position=tqdm_position, leave=False):
                result["total_frames_sampled"] += len(batch["index"]) if "index" in batch else batch_size

        # Properly shutdown DataLoader workers to avoid semaphore leaks
        if hasattr(dl, '_iterator') and dl._iterator is not None:
            dl._iterator._shutdown_workers()
        del dl
        gc.collect()

        # Calculate timing stats
        elapsed = time.perf_counter() - start_time
        result.update({
            "success": True,
            "total_time_s": elapsed,
            "time_per_episode_s": elapsed / len(episodes_to_test),
            "time_per_frame_s": elapsed / result["total_frames_sampled"] if result["total_frames_sampled"] else 0.0,
        })

    except Exception as e:
        result.update({
            "error_message": str(e),
            "total_time_s": time.perf_counter() - start_time,
        })
        print(f"❌ Detection failed: {e}", file=sys.stderr)

    finally:
        if ds:
            del ds
        gc.collect()

    return result


######################### Task Management Functions #########################


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

    from robocoin_dataset.database.models import DatasetDB, TaskStatus

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
    from robocoin_dataset.database.models import DatasetDB, TaskStatus

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
    # Constants
    "TASK_CATEGORY",
    # Dataset classes and utilities
    "LeRobotDataset",
    "MultiEpisodeSampler",
    "create_lerobot_dataset",
    "create_episode_dataloader",
    # Detection and validation
    "_run_detection",
    "_parse_episode_specification",
    "run_local_batch_detection",
    # Database task management
    "_sync_dataloader_detection_tasks",
    "_gen_one_dataloader_detection_task",
]
