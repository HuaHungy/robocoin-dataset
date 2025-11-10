import logging
from pathlib import Path

import tqdm
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from robocoin_dataset.annotation.subtask_annotion.utils import (
    compute_video_hash,
    get_video_paths,
)
from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DatasetDB,
    TaskStatus,
    VideoHashDB,
)
from robocoin_dataset.distribution_computation.constant import (
    DATASET_UUID,
    ERR_MSG,
    TASK_RESULT_CONTENT,
    TASK_RESULT_STATUS,
    TASK_SUCCESS,
)
from robocoin_dataset.distribution_computation.task_client import TaskClient
from robocoin_dataset.distribution_computation.task_server import TaskServer
from robocoin_dataset.format_converter.tolerobot.constant import (
    LEFORMAT_PATH,
)

VIDEO_HASHES_RESULT = "video_hashes_result"


def _sync_video_hash_status(session: Session) -> None:
    query = session.query(DatasetDB).filter(
        and_(
            # 必要前提：convert必须成功
            DatasetDB.convert_status == TaskStatus.COMPLETED,
            # 两个触发分支
            or_(
                # 分支1: 正在排队
                DatasetDB.video_hash_status == TaskStatus.PENDING,
                # 分支2: 已完成但版本过期
                and_(
                    DatasetDB.video_hash_status == TaskStatus.COMPLETED,
                    DatasetDB.video_hash_version_ps < DatasetDB.convert_version,
                ),
            ),
        )
    )
    items = query.all()

    if not items:
        return
    for item in items:
        item.video_hash_status = TaskStatus.PENDING
        item.video_hash_version = item.video_hash_version + 1
        item.video_hash_version_ps = item.convert_version

    session.commit()


def _gen_one_video_hash_task(session: Session) -> tuple[str | None, str | None]:
    query = session.query(DatasetDB).filter(
        DatasetDB.video_hash_status == TaskStatus.PENDING,
    )
    item = query.first()
    if not item:
        return None, None
    item.video_hash_status = TaskStatus.PROCESSING
    session.commit()
    return (
        item.dataset_uuid,
        item.convert_path,
    )


def compute_dataset_video_hashes(
    repo_path: str | Path,
) -> dict[str, tuple[int, int, str, str]]:
    results = {}
    video_paths = get_video_paths(repo_path=repo_path)
    for video_path, ep_idx in tqdm.tqdm(
        video_paths.items(), desc="Compute Video Hash", unit="video"
    ):
        file_hash, frame_num, serialized_image_phash = compute_video_hash(video_path)
        results[str(video_path)] = (ep_idx, frame_num, file_hash, serialized_image_phash)

    return results


def _upsert_video_hashes(
    session: Session,
    hashes: dict[str, tuple[int, int, str, bytes]],
    dataset_uuid: str,
) -> None:
    query = session.query(VideoHashDB).filter(VideoHashDB.video_path.in_(hashes.keys()))
    items = query.all()
    for item in items:
        ep_idx, frame_num, file_hash, serialized_phashes = hashes[item.video_path]
        item.dataset_uuid = dataset_uuid
        item.ep_idx = ep_idx
        item.frame_num = frame_num
        item.file_hash = file_hash
        item.image_hashes = serialized_phashes

    existing_video_paths = [item.video_path for item in items]

    non_existed_video_paths = [
        video_path for video_path in hashes.keys() if video_path not in existing_video_paths
    ]

    for video_path in non_existed_video_paths:
        ep_idx, frame_num, file_hash, serialized_phashes = hashes[video_path]
        item = VideoHashDB(
            dataset_uuid=dataset_uuid,
            ep_idx=ep_idx,
            video_path=video_path,
            frame_num=frame_num,
            file_hash=file_hash,
            image_hashes=serialized_phashes,
        )
        session.add(item)
    session.commit()


class VideoHash:
    def __init__(
        self,
        db_file_path: str | Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)

    def sync_video_hash_status(self) -> None:
        with self.db.with_session() as session:
            _sync_video_hash_status(session)

    def compute_video_hashes_one_dataset(self) -> None:
        with self.db.with_session() as session:
            dataset_uuid, repo_path = _gen_one_video_hash_task(session)

        if not dataset_uuid:
            return

        try:
            hash_results: dict[str, tuple[int, int, str, str]] = compute_dataset_video_hashes(
                repo_path=repo_path
            )

            with self.db.with_session() as session:
                try:
                    _upsert_video_hashes(session, hash_results, dataset_uuid)
                except Exception as e:
                    raise e
                query = session.query(DatasetDB).filter(
                    DatasetDB.dataset_uuid == dataset_uuid,
                )
                item = query.first()
                if not item:
                    raise ValueError(f"Dataset {dataset_uuid} not found")

                item.video_hash_status = TaskStatus.COMPLETED
                session.commit()
        except Exception as e:
            query = session.query(DatasetDB).filter(
                DatasetDB.dataset_uuid == dataset_uuid,
            )
            item = query.first()
            if not item:
                raise ValueError(f"Dataset {dataset_uuid} not found")

            item.video_hash_status = TaskStatus.FAILED
            item.video_hash_err_msg = str(e)
            session.commit()


class VideoHashServer(TaskServer):
    def __init__(
        self,
        db_file_path: str | Path,
        host: str = "0.0.0.0",
        port: int = 8768,
        heartbeat_interval: float = 30.0,  # 服务端每30秒发一次 ping
        timeout: float = 15.0,  # 等待 pong 超过15秒则断开
        logger: logging.Logger | None = None,
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
        self.logger = logger or logging.getLogger(__name__)
        self.logger.info("Video Hash Server started, ")

    def get_task_category(self) -> str:
        return "video_hash"

    def generate_task_content(self) -> dict | None:
        with self.db.with_session() as session:
            query = session.query(DatasetDB).filter(
                and_(
                    # 必要前提：convert必须成功
                    DatasetDB.convert_status == TaskStatus.COMPLETED,
                    # 两个触发分支
                    or_(
                        # 分支1: 正在排队
                        DatasetDB.video_hash_status == TaskStatus.PENDING,
                        # 分支2: 已完成但版本过期
                        and_(
                            DatasetDB.video_hash_status == TaskStatus.COMPLETED,
                            DatasetDB.video_hash_version_ps < DatasetDB.convert_version,
                        ),
                    ),
                )
            )
            item = query.first()

            if not item:
                return None

            item.video_hash_status = TaskStatus.PROCESSING
            item.video_hash_version = item.video_hash_version + 1
            item.video_hash_version_ps = item.convert_version

            session.commit()
            return {
                DATASET_UUID: item.dataset_uuid,
                LEFORMAT_PATH: item.convert_path,
            }

    def handle_task_result(self, task_content: dict, task_result_content: dict) -> None:
        ds_uuid = task_content.get(DATASET_UUID)

        task_status = task_result_content.get(TASK_RESULT_STATUS)
        task_status_msg = task_result_content.get(ERR_MSG)

        task_status = TaskStatus.COMPLETED if task_status == TASK_SUCCESS else TaskStatus.FAILED

        hash_result_tuple_dict: dict[str, tuple[int, int, str, str]] = {}
        video_hash_results: dict = task_result_content.get(TASK_RESULT_CONTENT).get(
            VIDEO_HASHES_RESULT
        )

        for video_path, value in video_hash_results.items():
            ep_idx = value.get("ep_idx")
            frame_num = value.get("frame_num")
            file_hash = value.get("file_hash")
            serialized_phashes = value.get("image_hashes")
            hash_result_tuple_dict[video_path] = (ep_idx, frame_num, file_hash, serialized_phashes)

        if task_status == TaskStatus.COMPLETED:
            with self.db.with_session() as session:
                _upsert_video_hashes(session, hash_result_tuple_dict, ds_uuid)
                query = session.query(DatasetDB).filter(
                    DatasetDB.dataset_uuid == ds_uuid,
                )
                item = query.first()
                if not item:
                    raise ValueError(f"Dataset {ds_uuid} not found")

                item.video_hash_status = TaskStatus.COMPLETED
                session.commit()
        else:
            with self.db.with_session() as session:
                _upsert_video_hashes(session, video_hash_results, ds_uuid)
                query = session.query(DatasetDB).filter(
                    DatasetDB.dataset_uuid == ds_uuid,
                )
                item = query.first()
                if not item:
                    raise ValueError(f"Dataset {ds_uuid} not found")

                item.video_hash_status = task_status
                item.video_hash_err_msg = task_status_msg
                session.commit()


class VideoHashClient(TaskClient):
    def __init__(
        self,
        server_uri: str = "ws://localhost:8767",
        heartbeat_interval: float = 10.0,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(
            server_uri=server_uri,
            heartbeat_interval=heartbeat_interval,
            logger=logger,
        )

    def get_task_category(self) -> str:
        return "simulation_replay"

    def generate_task_request_desc(self) -> dict:
        """客户端可自定义任务请求参数"""
        return {}

    def _sync_process_task(self, task_content: dict) -> dict:
        try:
            repo_path = task_content.get(LEFORMAT_PATH)
            video_hashes = compute_dataset_video_hashes(repo_path)
            video_hashes_dict = {}
            for video_path, (ep_idx, frame_num, file_hash, image_hashes) in video_hashes.items():
                item_dict = {
                    "ep_idx": ep_idx,
                    "frame_num": frame_num,
                    "file_hash": file_hash,
                    "image_hashes": image_hashes,
                }
                video_hashes_dict[video_path] = item_dict
            return {VIDEO_HASHES_RESULT: video_hashes_dict}
        except Exception as e:
            raise RuntimeError(f"video hash {repo_path} failed") from e
