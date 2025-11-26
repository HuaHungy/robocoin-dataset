import logging
import random
import traceback
import warnings
from collections.abc import Iterator
from pathlib import Path

import torch
import torch.utils.data
import tqdm
from lerobot.datasets.lerobot_dataset import LeRobotDataset  # type: ignore
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import and_, or_

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DatasetDB,
    DatasetHardLinkDB,
    TaskStatus,
)
from robocoin_dataset.distribution_computation.constant import (
    DATASET_UUID,
    ERR_MSG,
    TASK_RESULT_STATUS,
    TASK_SUCCESS,
)
from robocoin_dataset.distribution_computation.task_client import TaskClient
from robocoin_dataset.distribution_computation.task_server import TaskServer

warnings.filterwarnings(
    "ignore", category=UserWarning, module="torchvision.io._video_deprecation_warning"
)

NUM_WORKERS = "num_workers"
SAMPLE_RATE = "sample_rate"
HARD_LINK_PATH = "hard_link_path"


def _sync_dataloader_check_tasks(session: Session) -> None:
    query = session.query(DatasetDB).filter(
        and_(
            # 必要前提：convert必须成功
            DatasetDB.qced_repo_gen_status == TaskStatus.COMPLETED,
            # 两个触发分支
            or_(
                # 分支1: 正在排队
                DatasetDB.data_loader_detection_status == TaskStatus.PENDING,
                # 分支2: 已完成但版本过期
                and_(
                    DatasetDB.data_loader_detection_status == TaskStatus.COMPLETED,
                    DatasetDB.data_loader_detection_version_ps != DatasetDB.qced_repo_gen_version,
                ),
            ),
        )
    )
    items = query.all()

    if not items:
        return

    for item in items:
        item.data_loader_detection_status = TaskStatus.PENDING
        item.data_loader_detection_version_ps = item.qced_repo_gen_version

    session.commit()


def _gen_one_dataloader_check_task(
    session: Session,
) -> tuple[str | None, str | None]:
    query = session.query(DatasetDB).filter(
        and_(
            # 必要前提：convert必须成功
            DatasetDB.qced_repo_gen_status == TaskStatus.COMPLETED,
            DatasetDB.data_loader_detection_status == TaskStatus.PENDING,
        )
    )
    ds_item = query.first()

    if not ds_item:
        return None, None

    query = session.query(DatasetHardLinkDB).filter(
        DatasetHardLinkDB.dataset_uuid == ds_item.dataset_uuid
    )
    hard_link_item = query.first()
    if not hard_link_item:
        return None, None
    hard_link_path = Path(hard_link_item.hard_link_path)
    ds_item.data_loader_detection_status = TaskStatus.PROCESSING

    ds_item.data_loader_detection_version = ds_item.data_loader_detection_version + 1
    session.commit()

    return ds_item.dataset_uuid, hard_link_path


class EpisodeSampler(torch.utils.data.Sampler):
    def __init__(self, dataset: LeRobotDataset, sample_rate: float = 0.1) -> None:
        self.frame_ids = random.sample(
            range(dataset.num_frames), k=int(dataset.num_frames * sample_rate)
        )
        self.frame_ids = self.frame_ids[:: int(1 / sample_rate)]

    def __iter__(self) -> Iterator:
        return iter(self.frame_ids)

    def __len__(self) -> int:
        return len(self.frame_ids)


def diagnose_stats_dimensions(episodes_stats: dict) -> str:
    """Diagnose which episodes and features have corrupted stats (0-dimensional arrays)."""
    issues = []
    
    for episode_id, episode_stats in episodes_stats.items():
        for feature_key, feature_stats in episode_stats.items():
            for stat_key, stat_value in feature_stats.items():
                if hasattr(stat_value, 'ndim') and stat_value.ndim == 0:
                    issues.append(
                        f"Episode {episode_id}, Feature '{feature_key}', Stat '{stat_key}': "
                        f"shape={stat_value.shape}, ndim={stat_value.ndim}, value={stat_value}"
                    )
                elif hasattr(stat_value, 'shape') and len(stat_value.shape) == 0:
                    issues.append(
                        f"Episode {episode_id}, Feature '{feature_key}', Stat '{stat_key}': "
                        f"shape={stat_value.shape} (scalar), value={stat_value}"
                    )
    
    if issues:
        return "Found corrupted stats:\n" + "\n".join(issues)
    else:
        return "No 0-dimensional stats found in episodes_stats"


def load_repo(
    repo_hardlink: str | Path,
    num_workers: int = 8,
    sample_rate: float = 0.1,
) -> None:
    try:
        dataset = LeRobotDataset(
            repo_id="test/test_repo",
            root=repo_hardlink,
            video_backend="pyav",  # torchcodec is not supported.(2.0)
        )
    except ValueError as e:
        if "Number of dimensions must be at least 1" in str(e):
            # Try to diagnose the issue by loading episodes_stats directly
            try:
                from lerobot.datasets.lerobot_dataset import load_episodes_stats
                episodes_stats = load_episodes_stats(repo_hardlink)
                diagnosis = diagnose_stats_dimensions(episodes_stats)
                raise ValueError(f"Dataset stats corruption detected:\n{diagnosis}\nOriginal error: {e}") from e
            except Exception as diag_e:
                raise ValueError(f"Dataset stats corruption detected. Could not load episodes_stats for diagnosis: {diag_e}\nOriginal error: {e}") from e
        else:
            raise
    
    sampler = EpisodeSampler(dataset, sample_rate=sample_rate)

    dataloader = torch.utils.data.DataLoader(
        dataset,
        batch_size=32,
        sampler=sampler,
        num_workers=num_workers,
    )
    for batch in tqdm.tqdm(dataloader, total=len(dataloader)):
        pass


class DataLoaderChecker:
    def __init__(
        self,
        db_file_path: str | Path,
        sample_rate: float = 0.1,
        num_workers: int = 8,
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.sample_rate = sample_rate
        self.num_workers = num_workers
        self.logger = logger or logging.getLogger(__name__)

    def check_one_repo(self) -> None:
        with self.db.with_session() as session:
            _sync_dataloader_check_tasks(session=session)
            dataset_uuid, hardlink = _gen_one_dataloader_check_task(session=session)
            if dataset_uuid is None:
                return

        try:
            load_repo(hardlink, sample_rate=self.sample_rate, num_workers=self.num_workers)
            with self.db.with_session() as session:
                ds_item = (
                    session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
                )
                if not ds_item:
                    return
                ds_item.data_loader_detection_status = TaskStatus.COMPLETED
                ds_item.data_loader_detection_err_msg = None
                session.commit()
        except Exception:
            with self.db.with_session() as session:
                ds_item = (
                    session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
                )
                if ds_item:
                    ds_item.data_loader_detection_status = TaskStatus.FAILED
                    ds_item.data_loader_detection_err_msg = traceback.format_exc()
                else:
                    return
                session.commit()
            self.logger.info(traceback.format_exc())


class DataLoaderCheckerServer(TaskServer):
    def __init__(
        self,
        db_file_path: str | Path,
        host: str = "0.0.0.0",
        port: int = 2010,
        heartbeat_interval: float = 30.0,  # 服务端每30秒发一次 ping
        timeout: float = 15.0,  # 等待 pong 超过15秒则断开
        logger: logging.Logger | None = None,
        sample_rate: float = 0.1,
        num_workers: int = 8,
    ) -> None:
        super().__init__(
            logger=logger,
            host=host,
            port=port,
            heartbeat_interval=heartbeat_interval,
            timeout=timeout,
        )
        db_file_path = Path(db_file_path).expanduser().absolute()

        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.sample_rate = sample_rate
        self.num_workers = num_workers
        self.logger = logger or logging.getLogger(__name__)

    def get_task_category(self) -> str:
        return "dataset dataloader checker"

    def generate_task_content(self) -> dict | None:
        with self.db.with_session() as session:
            _sync_dataloader_check_tasks(session=session)
            dataset_uuid, hardlink_path = _gen_one_dataloader_check_task(session=session)

        if not dataset_uuid:
            return None
        return {
            DATASET_UUID: dataset_uuid,
            HARD_LINK_PATH: str(hardlink_path),
            NUM_WORKERS: self.num_workers,
            SAMPLE_RATE: self.sample_rate,
        }

    def handle_task_result(self, task_content: dict, task_result_content: dict) -> None:
        ds_uuid = task_content.get(DATASET_UUID)

        task_status = task_result_content.get(TASK_RESULT_STATUS)
        task_status_msg = task_result_content.get(ERR_MSG)

        err_msg = task_result_content.get(ERR_MSG)

        if task_status == TASK_SUCCESS:
            with self.db.with_session() as session:
                item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == ds_uuid).first()
                if item:
                    item.data_loader_detection_status = TaskStatus.COMPLETED
                    item.data_loader_detection_err_msg = None
                else:
                    return
                session.commit()
        else:
            with self.db.with_session() as session:
                item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == ds_uuid).first()
                if item:
                    item.data_loader_detection_status = TaskStatus.FAILED
                    item.data_loader_detection_err_msg = err_msg
                else:
                    return

                self.logger.info(
                    f"Upsert {item.convert_path} dataset dataloader check status to {item.qced_repo_gen_status}, "
                    f"update_message: {task_status_msg}"
                )
                session.commit()


class DataLoaderCheckerClient(TaskClient):
    def __init__(
        self,
        server_uri: str = "ws://localhost:2010",
        heartbeat_interval: float = 10.0,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(
            server_uri=server_uri,
            heartbeat_interval=heartbeat_interval,
            logger=logger,
        )

    def get_task_category(self) -> str:
        return "dataset dataloader checker"

    def generate_task_request_desc(self) -> dict:
        """客户端可自定义任务请求参数"""
        return {}

    def _sync_process_task(self, task_content: dict) -> dict:
        try:
            hard_link_path = task_content.get(HARD_LINK_PATH)
            num_workers = task_content.get(NUM_WORKERS)
            sample_rate = task_content.get(SAMPLE_RATE)

            load_repo(hard_link_path, sample_rate=sample_rate, num_workers=num_workers)

            return {}
        except Exception as e:
            raise RuntimeError(f"dataset dataloader check {hard_link_path} failed") from e
