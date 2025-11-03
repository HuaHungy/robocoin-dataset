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
    DATASET_UUID,
    ERR_MSG,
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
    DEFAULT_DB_FILE = (_repo_root / "examples" / "dataloader_test" / "datasets_new.db").expanduser().absolute()
except Exception:
    DEFAULT_DB_FILE = Path("examples/dataloader_test/datasets_new.db").expanduser().absolute()


def _sync_dataloader_detection_tasks(
    session: Session,
    logger: logging.Logger | None = None,
) -> None:
    """Mark datasets requiring dataloader detection as pending and align versions.

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
                    DatasetDB.data_loader_detection_version_ps < DatasetDB.convert_version,
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
        item.data_loader_detection_version_ps = item.convert_version

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

    Returns (dataset_uuid, convert_path) or (None, None) if no task available.
    """
    item = (
        session.query(DatasetDB)
        .filter(DatasetDB.data_loader_detection_status == TaskStatus.PENDING)
        .first()
    )
    if not item:
        return None, None

    item.data_loader_detection_status = TaskStatus.PROCESSING
    item.data_loader_detection_version_ps = item.convert_version
    # Version is NOT incremented here - only increment after successful detection
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
            raise ValueError(f"Episode {episode_spec} out of range [0, {total_episodes-1}]")
        return [episode_spec]

    if isinstance(episode_spec, list):
        for ep in episode_spec:
            if not isinstance(ep, int) or ep < 0 or ep >= total_episodes:
                raise ValueError(f"Episode {ep} out of range [0, {total_episodes-1}]")
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
                raise ValueError(f"Episode {ep} out of range [0, {total_episodes-1}]")

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
            result["errors"].append({
                "type": "episode_specification_error",
                "message": error_msg,
            })
            result["error_summary"] = error_msg
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
                        batch_size_actual = (
                            len(batch["index"]) if "index" in batch else 1
                        )
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

                # Log error to progress bar
                if overall_progress is not None:
                    overall_progress.write(f"❌ Episode {ep_idx} failed: {episode_error}")

                if strict_mode:
                    if overall_progress is not None:
                        overall_progress.close()
                    raise RuntimeError(f"Episode {ep_idx} validation failed: {episode_error}") from e

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
        result["errors"].append({
            "type": "fatal_error",
            "message": error_msg,
            "traceback": traceback.format_exc(),
        })
        result["error_summary"] = f"Fatal error: {error_msg}"
        result["success"] = False

        if strict_mode:
            raise

        return result


class DataloaderDbProcess:
    def __init__(self, db_file_path: str | Path | None = None, logger: logging.Logger | None = None) -> None:
        self.db_file_path: Path = Path(db_file_path if db_file_path is not None else DEFAULT_DB_FILE).expanduser().absolute()
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
            item = (
                session.query(DatasetDB)
                .filter(DatasetDB.dataset_uuid == dataset_uuid)
                .first()
            )
            if item is None:
                raise ValueError(f"Dataset {dataset_uuid} not found")

            if result["success"]:
                item.data_loader_detection_status = TaskStatus.COMPLETED
                item.data_loader_detection_err_msg = None
                # Increment version ONLY after successful detection
                item.data_loader_detection_version = (item.data_loader_detection_version or 0) + 1
                self.logger.info(
                    f"Dataset {dataset_uuid} validation completed: "
                    f"{result['total_frames_validated']} frames in {len(result['episodes_tested'])} episodes"
                )
            else:
                item.data_loader_detection_status = TaskStatus.FAILED
                item.data_loader_detection_err_msg = result.get("error_summary", "Unknown error")
                # Do NOT increment version on failure
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
        self.db_file_path: Path = Path(db_file_path if db_file_path is not None else DEFAULT_DB_FILE).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)

    def get_task_category(self) -> str:
        return TASK_CATEGORY

    def generate_task_content(self) -> dict | None:
        with self.db.with_session() as session:
            # pre-sync queue
            _sync_dataloader_detection_tasks(session, logger=self.logger)

            # claim one
            item = (
                session.query(DatasetDB)
                .filter(DatasetDB.data_loader_detection_status == TaskStatus.PENDING)
                .first()
            )
            if not item:
                return None

            item.data_loader_detection_status = TaskStatus.PROCESSING
            # Version is NOT incremented here - only increment after successful detection
            item.data_loader_detection_version_ps = item.convert_version
            session.commit()

            return {
                DATASET_UUID: item.dataset_uuid,
                LEFORMAT_PATH: item.convert_path,
            }

    def handle_task_result(self, task_content: dict, task_result_content: dict) -> None:
        ds_uuid = task_content.get(DATASET_UUID)
        task_status = task_result_content.get(TASK_RESULT_STATUS)
        task_status_msg = task_result_content.get(ERR_MSG)

        status = TaskStatus.COMPLETED if task_status == TASK_SUCCESS else TaskStatus.FAILED
        with self.db.with_session() as session:
            item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == ds_uuid).first()
            if item is None:
                self.logger.error(f"Dataset {ds_uuid} not found in dataset DB.")
                return

            item.data_loader_detection_status = status
            if status == TaskStatus.COMPLETED:
                # Increment version ONLY after successful detection
                item.data_loader_detection_version = (item.data_loader_detection_version or 0) + 1
            elif status == TaskStatus.FAILED:
                item.data_loader_detection_err_msg = task_status_msg
                # Do NOT increment version on failure
            session.commit()
            self.logger.info(
                f"Upsert {item.convert_path} dataloader detection status to {status}, update_message: {task_status_msg}"
            )


class DataloaderDbClient(TaskClient):
    def __init__(
        self,
        server_uri: str = "ws://localhost:8771",
        heartbeat_interval: float = 10.0,
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
        # Run detection with all episodes, non-strict mode (collect all errors)
        return _run_dataloader_detection(
            repo_path,
            episode_indices="all",
            strict_mode=False,
        )


# =============================
# Multi-process support for client and local modes
# =============================


async def run_client_async(server_uri: str, heartbeat_interval: float, logger: logging.Logger) -> dict:
    """Run a single client that connects to server and processes tasks until none remain.

    Returns:
        Statistics dictionary with keys: tasks_processed, tasks_succeeded, tasks_failed
    """
    client = DataloaderDbClient(server_uri=server_uri, heartbeat_interval=heartbeat_interval, logger=logger)

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
                logger.info(f"🚀 Starting to process task: {task.get('task_id')}")

            result_content = await client.process_task(task)
            tasks_processed += 1

            # Check if task succeeded or failed
            if result_content.get("task_result_status") == "task_success":
                tasks_succeeded += 1
            else:
                tasks_failed += 1

            result = {
                "msg_type": "task_result",
                "msg_content": result_content,
            }
            result["task_id"] = task.get("task_id")
            result["client_id"] = client.client_id
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
            stats_queue.put({
                "process_id": process_id,
                "tasks_processed": 0,
                "tasks_succeeded": 0,
                "tasks_failed": 0,
            })
        return 1


def local_process_main(
    db_file: str | Path,
    target_dir: str | Path | None,
    absolute_symlinks: bool,
    skip_missing: bool,
    log_dir: str | Path,
    log_level: str,
    process_id: int,
    stats_queue: "mp.Queue | None" = None,
) -> int:
    """Entry point for each local process in multi-local mode.

    This function claims datasets atomically from the database to avoid
    race conditions when multiple processes are running concurrently.
    """
    from sqlalchemy import func

    from robocoin_dataset.dataloader.make_data_sym_links import create_lerobot_symlink_structure
    from robocoin_dataset.utils.logger import setup_logger

    # Create per-process logger
    logger = setup_logger(
        name=f"dataloader_local_{process_id}",
        log_dir=Path(log_dir),
        level=getattr(logging, log_level, logging.INFO),
    )

    logger.info(f"Local process {process_id} started")

    db_file_path = Path(db_file)
    db = DatasetDatabase(db_file_path)

    processed_count = 0
    success_count = 0
    fail_count = 0

    while True:
        # Atomically claim one dataset to process (prevents race conditions)
        ds_uuid = None
        convert_path = None

        with db.with_session() as session:
            # Sync tasks first
            _sync_dataloader_detection_tasks(session, logger=logger)

            # Claim one pending task atomically
            item = (
                session.query(DatasetDB)
                .filter(DatasetDB.data_loader_detection_status == TaskStatus.PENDING)
                .first()
            )

            if not item:
                logger.info(f"Process {process_id}: No more datasets to process")
                break

            # Transition to PROCESSING to claim it
            item.data_loader_detection_status = TaskStatus.PROCESSING
            # Version is NOT incremented here - only increment after successful detection
            item.data_loader_detection_version_ps = item.convert_version
            session.commit()

            ds_uuid = item.dataset_uuid
            convert_path = item.convert_path

        if not ds_uuid or not convert_path:
            break

        source_dir = Path(convert_path)
        logger.info(f"Process {process_id}: Processing dataset {ds_uuid}")

        tgt_dir = Path(target_dir) if target_dir else source_dir.parent / f"{source_dir.name}_symlink"

        # Try symlink creation and dataloader detection
        ok = True
        err: str | None = None
        try:
            create_lerobot_symlink_structure(
                source_dir=source_dir,
                target_dir=tgt_dir,
                relative=not absolute_symlinks,
                skip_missing=skip_missing,
            )
            # Run comprehensive validation (all episodes, non-strict)
            result = _run_dataloader_detection(
                tgt_dir,
                episode_indices="all",
                strict_mode=False,
            )

            if result["success"]:
                logger.info(
                    f"Process {process_id}: Dataset {ds_uuid} completed - "
                    f"{result['total_frames_validated']} frames in {len(result['episodes_tested'])} episodes"
                )
                success_count += 1
            else:
                ok = False
                err = result.get("error_summary", "Validation failed")
                logger.error(f"Process {process_id}: Dataset {ds_uuid} failed: {err}")
                fail_count += 1
        except Exception as e:
            ok = False
            err = str(e)
            logger.error(f"Process {process_id}: Dataset {ds_uuid} failed: {err}")
            fail_count += 1

        # Update status
        with db.with_session() as session:
            values = {
                DatasetDB.data_loader_detection_status: TaskStatus.COMPLETED if ok else TaskStatus.FAILED,
                DatasetDB.data_loader_detection_version_ps: DatasetDB.data_merge_version,
            }
            # Increment version ONLY after successful detection
            if ok:
                values[DatasetDB.data_loader_detection_version] = func.coalesce(DatasetDB.data_loader_detection_version, 0) + 1
            # Do NOT increment version on failure
            if not ok and err:
                values[DatasetDB.data_loader_detection_err_msg] = err
            session.query(DatasetDB).filter(DatasetDB.dataset_uuid == ds_uuid).update(
                values, synchronize_session=False
            )
            session.commit()

        processed_count += 1

    logger.info(
        f"Process {process_id} completed: {processed_count} total, "
        f"{success_count} succeeded, {fail_count} failed"
    )

    # Send statistics back to parent process
    if stats_queue is not None:
        stats_queue.put({
            "process_id": process_id,
            "tasks_processed": processed_count,
            "tasks_succeeded": success_count,
            "tasks_failed": fail_count,
        })

    return 0 if fail_count == 0 else 1


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
    process_fail_count = sum(1 for code in exit_codes.values() if code not in (0, None) and code is not None)

    print(f"🔧 Process completions: {process_success_count} successful, {process_fail_count} failed")

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


def run_multi_local(
    db_file: str | Path,
    num_processes: int,
    target_dir: str | Path | None,
    absolute_symlinks: bool,
    skip_missing: bool,
    log_dir: str | Path,
    log_level: str,
) -> int:
    """Spawn multiple local processing processes.

    Args:
        db_file: Path to SQLite database
        num_processes: Number of local processes to spawn
        target_dir: Target directory for symlinks (None = auto)
        absolute_symlinks: Use absolute symlinks instead of relative
        skip_missing: Skip missing source files
        log_dir: Directory for log files
        log_level: Logging level string (e.g. "INFO", "DEBUG")

    Returns:
        Exit code: 0 if all processes succeeded, 1 otherwise
    """
    print(f"🚀 Starting {num_processes} local process(es)...")
    print(f"   Database: {db_file}")
    print(f"   Target dir: {target_dir or 'auto (source_symlink)'}")
    print(f"   Absolute symlinks: {absolute_symlinks}")
    print(f"   Symlink skip missing: {skip_missing}")
    print(f"   Log dir: {log_dir}")
    print()

    # Create queue for collecting statistics from child processes
    stats_queue = mp.Queue()

    processes = []
    start_time = time.time()

    for i in range(num_processes):
        proc = mp.Process(
            target=local_process_main,
            kwargs=dict(
                db_file=db_file,
                target_dir=target_dir,
                absolute_symlinks=absolute_symlinks,
                skip_missing=skip_missing,
                log_dir=log_dir,
                log_level=log_level,
                process_id=i,
                stats_queue=stats_queue,
            ),
        )
        proc.start()
        processes.append(proc)
        print(f"   ✓ Local process {i} spawned (PID: {proc.pid})")

        # Add startup delay to avoid thundering herd
        if i < num_processes - 1:
            time.sleep(0.1)

    print(f"\n⏳ Waiting for {num_processes} process(es) to complete...")
    print("   Press Ctrl+C to interrupt\n")

    exit_codes = {}

    try:
        # Wait for all processes to complete
        for i, proc in enumerate(processes):
            proc.join()
            exit_codes[i] = proc.exitcode

    except KeyboardInterrupt:
        print("\n\n⚠️  KeyboardInterrupt received, shutting down processes...")
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
    print("📊 MULTI-LOCAL SUMMARY")
    print("=" * 70)
    print(f"Total processes: {num_processes}")
    print(f"Elapsed time: {elapsed:.1f}s")
    print()

    # Display TASK statistics (not process statistics)
    print(f"📦 Tasks processed: {total_tasks_processed}")
    print(f"✅ Tasks succeeded: {total_tasks_succeeded}")
    print(f"❌ Tasks failed: {total_tasks_failed}")
    print()

    # Display process-level information
    process_success_count = sum(1 for code in exit_codes.values() if code == 0)
    process_fail_count = sum(1 for code in exit_codes.values() if code not in (0, None) and code is not None)

    print(f"🔧 Process completions: {process_success_count} successful, {process_fail_count} failed")

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
