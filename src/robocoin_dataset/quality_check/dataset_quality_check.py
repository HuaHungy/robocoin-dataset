import logging
import traceback
from collections import defaultdict
from pathlib import Path

import av
import mergedeep as merge
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import tqdm
import yaml
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import and_, or_

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DatasetDB,
    EpisodeQcDB,
    TaskStatus,
)
from robocoin_dataset.distribution_computation.constant import (
    DATASET_UUID,
    DEVICE_MODEL,
    DEVICE_MODEL_VERSION,
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
from robocoin_dataset.quality_check.checker_registry import (
    DATASET_DATA_CHECKERS,
    EPISODE_DATA_CHECKERS,
    EPISODE_VIDEO_CHECKERS,
)
from robocoin_dataset.utils.le_path import get_episodes_frames, get_parquet_files, get_video_files

QC_CONFIG = "qc_config"
QC_RESULT = "qc_result"
MERGED_DATA_FEATURE = "merged"


def get_checker_config(
    device_model: str, device_model_version: str, device_verison_config_file: str | Path
) -> dict:
    device_verison_config_file = Path(device_verison_config_file)
    checker_root_path = device_verison_config_file.parent
    device_verison_checker_config = yaml.safe_load(device_verison_config_file.open())
    default_config_path = checker_root_path / "default_checker_config.yaml"
    default_config = yaml.safe_load(default_config_path.open())
    if device_model not in device_verison_checker_config:
        return default_config

    if device_model_version not in device_verison_checker_config[device_model]:
        device_model_version = "default_version"

    version_idx = 0
    for i, v in enumerate(device_verison_checker_config[device_model]):
        if v == device_model_version:
            version_idx = i
            break

    base_config_path = (
        checker_root_path
        / device_verison_checker_config[device_model][version_idx]["base_config_path"]
    )
    specific_config_path = (
        checker_root_path
        / device_verison_checker_config[device_model][version_idx]["specific_config_path"]
    )

    base_config = yaml.safe_load(base_config_path.open())
    specific_config = yaml.safe_load(specific_config_path.open())

    return merge.merge(base_config, specific_config)


def check_length_consistency(
    repo_path: str | Path, data_feature: str | None, video_feature: str | None = None
) -> set[int]:
    bad_episodes = set()
    parquet_files = get_parquet_files(repo_path, data_feature)
    video_files = get_video_files(repo_path, video_feature)
    episode_nums = get_episodes_frames(repo_path)
    if len(parquet_files) != len(video_files):
        raise ValueError(
            f"The number of parquet files ({len(parquet_files)}) does not match the number of video files ({len(video_files)})."
        )

    for ep_idx in tqdm.tqdm(
        range(len(parquet_files)), desc="Checking Length Consistency", unit="episode"
    ):
        metadata = pq.read_metadata(parquet_files[ep_idx])
        row_num = metadata.num_rows
        if row_num != episode_nums[ep_idx]:
            bad_episodes.add(ep_idx)
            break
        for video_file in video_files[ep_idx]:
            container = av.open(video_file)
            stream = container.streams.video[0]  # 假设第一个视频流
            frame_count = stream.frames  # 可能为 0 或 None（如果未知）
            if frame_count != episode_nums[ep_idx]:
                bad_episodes.add(ep_idx)
                break
            container.close()

    return bad_episodes


def quality_check_pipeline(
    repo_path: str | Path, configs: dict, data_feature: str
) -> tuple[dict, dict]:
    dataset_data_checkers_config = configs.get("dataset_data_checkers", None)
    if not dataset_data_checkers_config:
        raise ValueError("No dataset_data_checkers config found.")

    episode_data_checkers_config = configs.get("episode_data_checkers", None)
    if not episode_data_checkers_config:
        raise ValueError("No episode_data_checkers config found.")

    episode_video_checkers_config = configs.get("episode_video_checkers", None)

    try:
        episode_nums = get_episodes_frames(repo_path)
        bad_data_episodes = check_length_consistency(repo_path, data_feature)
        print("Bad data episodes: ", bad_data_episodes)
        for checker_cfg in dataset_data_checkers_config:
            name = checker_cfg["name"]
            func = DATASET_DATA_CHECKERS[name]
            params = checker_cfg.get("params", {})
            bad_data_episodes = func(episode_nums, bad_data_episodes, **params)

        state_data_scores = {}
        action_data_scores = {}
        parquet_files = get_parquet_files(repo_path, data_feature)
        state_data_scores_perchecker = defaultdict(dict)
        action_data_scores_perchecker = defaultdict(dict)

        for idx, parquet_path in tqdm.tqdm(
            enumerate(parquet_files),
            desc="Checking episodes",
            total=len(parquet_files),
            unit="episode",
        ):
            if idx in bad_data_episodes:
                continue

            df = pd.read_parquet(parquet_path)
            state_data = np.array(df["observation.state"].tolist())
            action_data = np.array(df["action"].tolist())
            state_score = 0
            action_score = 0
            total_weight = 0
            checked = False
            for checker_cfg in episode_data_checkers_config:
                name = checker_cfg.get("name")
                weight = checker_cfg.get("score_weight")
                checker_flag = checker_cfg.get("should_check", False)
                if checker_flag:
                    total_weight += weight
                    if not name or not weight:
                        raise ValueError(
                            "Each episode_data_checker config must have 'name' and 'weight'."
                        )
                    if weight <= 0.001:
                        raise ValueError(
                            "Each episode_data_checker config must have valid 'weight'."
                        )
                    func = EPISODE_DATA_CHECKERS[name]
                    params = checker_cfg.get("params", {})
                    state_checker_score = 1 - func(state_data, **params)
                    state_score += state_checker_score * weight

                    action_checker_score = 1 - func(action_data, **params)

                    action_score += action_checker_score * weight
                    state_data_scores_perchecker[idx][name] = state_checker_score
                    action_data_scores_perchecker[idx][name] = action_checker_score
                    checked = True
            if not checked:
                continue
            state_data_scores[idx] = state_score / total_weight
            action_data_scores[idx] = action_score / total_weight

        if not episode_video_checkers_config:
            return (
                {
                    "bad_data_episodes": list(bad_data_episodes),
                    "state_data_scores": state_data_scores,
                    "action_data_scores": action_data_scores,
                },
                {
                    "state_data_scores_perchecker": state_data_scores_perchecker,
                    "action_data_scores_perchecker": action_data_scores_perchecker,
                },
            )
        video_scores = {}
        video_scores_perchecker = defaultdict(dict)
        video_paths = get_video_files(repo_path)
        for idx, paths in tqdm.tqdm(
            enumerate(video_paths), desc="Checking videos", unit="video", total=len(video_paths)
        ):
            if idx in bad_data_episodes:
                continue
            total_weight = 0
            video_score = 0
            for checker_cfg in episode_video_checkers_config:
                name = checker_cfg.get("name")
                func = EPISODE_VIDEO_CHECKERS[name]
                params = checker_cfg.get("params", {})
                weight = checker_cfg.get("score_weight")
                checker_flag = checker_cfg.get("should_check", False)
                if checker_flag:
                    total_weight += weight
                    if not name:
                        raise ValueError("Each episode_video_checker config must have 'name'.")

                    video_checker_score = 1 - func(paths, **params)
                    video_score += video_checker_score * weight
                    video_scores_perchecker[idx][name] = video_checker_score
            video_score /= total_weight
            video_scores[idx] = video_score

        return (
            {
                "bad_data_episodes": list(bad_data_episodes),
                "state_data_scores": state_data_scores,
                "action_data_scores": action_data_scores,
                "video_scores": video_scores,
            },
            {
                "state_data_scores_perchecker": state_data_scores_perchecker,
                "action_data_scores_perchecker": action_data_scores_perchecker,
                "video_scores_perchecker": video_scores_perchecker,
            },
        )

    except Exception:
        raise


def _gen_one_dataset_quality_check_task(
    session: Session,
) -> tuple[str | None, str | None, str | None, str | None]:
    query = session.query(DatasetDB).filter(
        and_(
            DatasetDB.data_merge_status == TaskStatus.COMPLETED,
            or_(
                # 分支1: 正在排队
                DatasetDB.qc_status == TaskStatus.PENDING,
                # 分支2: 已完成但版本过期
                and_(
                    DatasetDB.qc_status == TaskStatus.COMPLETED,
                    DatasetDB.qc_version_ps != DatasetDB.data_merge_status,
                ),
            ),
        )
    )
    item = query.first()
    if not item:
        return None, None, None, None
    item.motion_annotation_status = TaskStatus.PROCESSING
    session.commit()
    return item.dataset_uuid, item.convert_path, item.device_model, item.device_model_version


def _build_episode_qc_summary(
    bad_data_episodes: list[int] | None = None,
    state_data_scores: dict[int, float] | None = None,
    action_data_scores: dict[int, float] | None = None,
    video_scores: dict[int, float] | None = None,
) -> dict[int, dict]:
    # 转为 set 加速查找
    if bad_data_episodes is None:
        bad_data_episodes = []
    bad_set = set(bad_data_episodes)
    if state_data_scores is None:
        state_data_scores = {}
    if action_data_scores is None:
        action_data_scores = {}
    if video_scores is None:
        video_scores = {}

    # 假设所有 score 列表长度一致，取其一作为总 episode 数

    # 构建字典
    episode_summary = defaultdict(dict)
    for episode_idx in bad_data_episodes:
        episode_summary[episode_idx].update(
            {
                "is_bad": 1,
                "state_data_score": state_data_scores.get(episode_idx, 0),
                "action_data_score": action_data_scores.get(episode_idx, 0),
                "video_score": video_scores.get(episode_idx, 1),
            }
        )
    for episode_idx in (
        set(state_data_scores.keys()) | set(action_data_scores.keys()) | set(video_scores.keys())
    ):
        episode_summary[episode_idx].update(
            {
                "is_bad": episode_idx in bad_set,
                "state_data_score": state_data_scores.get(episode_idx, 1),
                "action_data_score": action_data_scores.get(episode_idx, 1),
                "video_score": video_scores.get(episode_idx, 1),
            }
        )
    return episode_summary


def _sync_quality_check_tasks(
    session: Session, device_model: str | None = None, device_model_version: str | None = None
) -> None:
    query = session.query(DatasetDB).filter(
        and_(
            # 必要前提：convert必须成功
            DatasetDB.data_merge_status == TaskStatus.COMPLETED,
            # 两个触发分支
            or_(
                # 分支1: 正在排队
                DatasetDB.qc_status == TaskStatus.PENDING,
                # 分支2: 已完成但版本过期
                and_(
                    DatasetDB.qc_status == TaskStatus.COMPLETED,
                    DatasetDB.qc_version_ps < DatasetDB.data_merge_version,
                ),
            ),
        )
    )
    items = query.all()

    if not items:
        return

    for item in items:
        item.qc_status = TaskStatus.PENDING
        item.qc_version_ps = item.data_merge_version

    session.commit()


def _gen_one_dataset_quality_check_task_without_sync(
    session: Session,
) -> tuple[str | None, str | None, str | None, str | None]:
    query = session.query(DatasetDB).filter(
        and_(
            # 必要前提：convert必须成功
            DatasetDB.data_merge_status == TaskStatus.COMPLETED,
            DatasetDB.qc_status == TaskStatus.PENDING,
        )
    )
    item = query.first()

    if not item:
        return None, None, None, None

    item.qc_status = TaskStatus.PROCESSING

    item.qc_version = item.qc_version + 1
    session.commit()

    # 获取 sim_replay 配置
    device_model = item.device_model
    device_model_version = item.device_model_version

    return item.dataset_uuid, item.convert_path, device_model, device_model_version


def _check_repo(repo_path: str | Path, checker_config: dict, data_feature: str) -> dict[int, dict]:
    qc_results, _ = quality_check_pipeline(repo_path, checker_config, data_feature=data_feature)
    bad_episodes, state_data_scores, action_data_scores, video_scores = (
        qc_results.get("bad_data_episodes", []),
        qc_results.get("state_data_scores", {}),
        qc_results.get("action_data_scores", {}),
        qc_results.get("video_scores", {}),
    )

    return _build_episode_qc_summary(
        bad_episodes,
        state_data_scores=state_data_scores,
        action_data_scores=action_data_scores,
        video_scores=video_scores,
    )


class DatasetQualityCheck:
    def __init__(
        self,
        db_file_path: str | Path,
        qc_config_path: str | Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)
        self.qc_config_path: Path = Path(qc_config_path).expanduser().absolute()

    def check_one_repo(self) -> None:
        with self.db.with_session() as session:
            _sync_quality_check_tasks(session=session)
            dataset_uuid, repo_path, device_model, device_model_version = (
                _gen_one_dataset_quality_check_task_without_sync(session=session)
            )

        if not dataset_uuid:
            return

        checker_config = get_checker_config(
            device_model,
            device_model_version,
            self.qc_config_path,
        )

        try:
            qc_results = _check_repo(repo_path, checker_config, MERGED_DATA_FEATURE)

            with self.db.with_session() as session:
                item = (
                    session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
                )
                if item:
                    item.qc_status = TaskStatus.COMPLETED
                else:
                    return
                session.query(EpisodeQcDB).filter(EpisodeQcDB.dataset_uuid == dataset_uuid).delete()
                for episode_idx, summary in qc_results.items():
                    episode_qc_item = EpisodeQcDB(
                        dataset_uuid=dataset_uuid,
                        episode_idx=episode_idx,
                        is_bad_episode=summary["is_bad"],
                        state_data_score=summary["state_data_score"],
                        action_data_score=summary["action_data_score"],
                        video_score=summary["video_score"],
                    )
                    session.add(episode_qc_item)
                session.commit()
        except Exception:
            with self.db.with_session() as session:
                item = (
                    session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
                )
                if item:
                    item.qc_status = TaskStatus.FAILED
                    item.qc_err_msg = traceback.format_exc()
                else:
                    return
                session.commit()
            self.logger.info(traceback.format_exc())


class DatasetQualityCheckServer(TaskServer):
    def __init__(
        self,
        db_file_path: str | Path,
        qc_config_path: str | Path,
        host: str = "0.0.0.0",
        port: int = 2010,
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

        self.qc_config_path = Path(qc_config_path).expanduser().absolute()
        if not self.qc_config_path.exists():
            raise FileNotFoundError(f"QC config file {self.qc_config_path} not found.")

    def get_task_category(self) -> str:
        return "dataset quality check"

    def generate_task_content(self) -> dict | None:
        with self.db.with_session() as session:
            _sync_quality_check_tasks(session=session)
            dataset_uuid, repo_path, device_model, device_model_version = (
                _gen_one_dataset_quality_check_task_without_sync(session=session)
            )

        if not dataset_uuid:
            self.logger.info("No dataset quality check task available.")
            return None

        checker_config = get_checker_config(
            device_model,
            device_model_version,
            self.qc_config_path,
        )
        return {
            DATASET_UUID: dataset_uuid,
            LEFORMAT_PATH: repo_path,
            DEVICE_MODEL: device_model,
            DEVICE_MODEL_VERSION: device_model_version,
            QC_CONFIG: checker_config,
        }

    def handle_task_result(self, task_content: dict, task_result_content: dict) -> None:
        ds_uuid = task_content.get(DATASET_UUID)

        task_status = task_result_content.get(TASK_RESULT_STATUS)
        task_status_msg = task_result_content.get(ERR_MSG)

        qc_results = task_result_content.get(TASK_RESULT_CONTENT).get(QC_RESULT)

        err_msg = task_result_content.get(ERR_MSG)

        if task_status == TASK_SUCCESS:
            with self.db.with_session() as session:
                item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == ds_uuid).first()
                if item:
                    item.qc_status = TaskStatus.COMPLETED
                else:
                    return
                session.query(EpisodeQcDB).filter(EpisodeQcDB.dataset_uuid == ds_uuid).delete()
                for episode_idx, summary in qc_results.items():
                    episode_qc_item = EpisodeQcDB(
                        dataset_uuid=ds_uuid,
                        episode_idx=int(episode_idx),
                        is_bad_episode=summary["is_bad"],
                        state_data_score=summary["state_data_score"],
                        action_data_score=summary["action_data_score"],
                        video_score=summary["video_score"],
                    )
                    session.add(episode_qc_item)
                session.commit()
        else:
            with self.db.with_session() as session:
                item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == ds_uuid).first()
                if item:
                    item.qc_status = TaskStatus.FAILED
                    item.qc_err_msg = err_msg
                else:
                    return
                session.commit()

            self.logger.info(
                f"Upsert {item.convert_path} dataset quality check status to {item.qc_status}, "
                f"update_message: {task_status_msg}"
            )


class DatasetQualityCheckClient(TaskClient):
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
        return "dataset quality check"

    def generate_task_request_desc(self) -> dict:
        """客户端可自定义任务请求参数"""
        return {}

    def _sync_process_task(self, task_content: dict) -> dict:
        try:
            repo_path = task_content.get(LEFORMAT_PATH)

            results = _check_repo(
                repo_path,
                task_content.get(QC_CONFIG),
                data_feature=MERGED_DATA_FEATURE,
            )

            results_send = {str(episode_idx): v for episode_idx, v in results.items()}

            return {QC_RESULT: results_send}
        except Exception as e:
            raise RuntimeError(f"dataset quality check {repo_path} failed") from e
