import logging
import os
import sys
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
) -> None:
    """Mark datasets requiring dataloader detection as pending and align versions.

    Trigger rules mirror state-action post-processing:
      - convert must be COMPLETED
      - either status is PENDING, or COMPLETED but processed against an older convert_version
    """
    query = session.query(DatasetDB).filter(
        and_(
            DatasetDB.convert_status == TaskStatus.COMPLETED,
            or_(
                DatasetDB.data_loader_detection_status == TaskStatus.PENDING,
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

    for item in items:
        item.data_loader_detection_status = TaskStatus.PENDING
        item.data_loader_detection_version_ps = item.convert_version

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
    item.data_loader_detection_version = (item.data_loader_detection_version or 0) + 1
    session.commit()
    return item.dataset_uuid, item.convert_path


def _run_dataloader_detection(repo_path: str | Path) -> dict:
    """Build a dataset at repo_path and iterate episode 0 to validate decoding.

    Returns basic metrics for logging/inspection.
    """
    ds = create_lerobot_dataset(repo_id=str(repo_path))

    # Default to episode 0 if indexable; otherwise probe first sample
    result: dict[str, int | str] = {}
    try:
        dl = create_episode_dataloader(ds, episode_index=0, batch_size=32, num_workers=0)
        num_batches = 0
        num_frames = 0

        # Optional tqdm progress bar; fallback to no bar if not installed
        try:
            from tqdm import tqdm  # type: ignore
        except Exception:  # pragma: no cover
            tqdm = None  # type: ignore

        # Estimate total frames for episode 0 if available
        total_frames = None
        try:
            from_idx = ds.episode_data_index["from"][0].item()
            to_idx = ds.episode_data_index["to"][0].item()
            total_frames = int(to_idx - from_idx)
        except Exception:
            total_frames = None

        progress = None
        if tqdm is not None:
            progress = tqdm(total=total_frames, desc="Decoding", unit="frame", file=sys.stderr)

        # Suppress noisy prints from underlying libs while iterating
        with open(os.devnull, "w") as devnull, redirect_stdout(devnull):
            for batch in dl:
                batch_size_actual = (
                    len(batch["index"]) if isinstance(batch, dict) and "index" in batch else 1
                )
                num_batches += 1
                num_frames += batch_size_actual
                if progress is not None:
                    progress.update(batch_size_actual)

        if progress is not None:
            progress.close()

        result = {
            "num_batches": num_batches,
            "num_frames": num_frames,
            "backend": getattr(ds, "robocoin_video_backend", "unknown"),
            "backend_reason": getattr(ds, "robocoin_video_backend_reason", ""),
        }
    except Exception:
        # Fallback: probe one item to trigger decode path for non-episodic datasets
        _ = ds[0]  # may raise
        result = {
            "num_batches": 1,
            "num_frames": 1,
            "backend": getattr(ds, "robocoin_video_backend", "unknown"),
            "backend_reason": getattr(ds, "robocoin_video_backend_reason", ""),
        }

    return result


class DataloaderDbProcess:
    def __init__(self, db_file_path: str | Path | None = None, logger: logging.Logger | None = None) -> None:
        self.db_file_path: Path = Path(db_file_path if db_file_path is not None else DEFAULT_DB_FILE).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)

    def process_one_dataset(self) -> None:
        # 1) Sync tasks (queue pending/stale)
        with self.db.with_session() as session:
            _sync_dataloader_detection_tasks(session)
            dataset_uuid, convert_path = _gen_one_dataloader_detection_task(session)

        if not dataset_uuid or not convert_path:
            self.logger.info("No dataloader detection task to process")
            return

        # 2) Run detection and update status
        try:
            _run_dataloader_detection(convert_path)
            with self.db.with_session() as session:
                item = (
                    session.query(DatasetDB)
                    .filter(DatasetDB.dataset_uuid == dataset_uuid)
                    .first()
                )
                if item is None:
                    raise ValueError(f"Dataset {dataset_uuid} not found")
                item.data_loader_detection_status = TaskStatus.COMPLETED
                session.commit()
        except Exception:
            with self.db.with_session() as session:
                item = (
                    session.query(DatasetDB)
                    .filter(DatasetDB.dataset_uuid == dataset_uuid)
                    .first()
                )
                if item is None:
                    raise ValueError(f"Dataset {dataset_uuid} not found")
                item.data_loader_detection_status = TaskStatus.FAILED
                item.data_loader_detection_err_msg = str(traceback.format_exc())
                session.commit()
            self.logger.error(
                f"Dataloader detection failed for {convert_path}: {traceback.format_exc()}"
            )


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
            _sync_dataloader_detection_tasks(session)

            # claim one
            item = (
                session.query(DatasetDB)
                .filter(DatasetDB.data_loader_detection_status == TaskStatus.PENDING)
                .first()
            )
            if not item:
                return None

            item.data_loader_detection_status = TaskStatus.PROCESSING
            item.data_loader_detection_version = (item.data_loader_detection_version or 0) + 1
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
            if status == TaskStatus.FAILED:
                item.data_loader_detection_err_msg = task_status_msg
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
        # Run detection; propagate exceptions for the framework to mark FAILED
        return _run_dataloader_detection(repo_path)
