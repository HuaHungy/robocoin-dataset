import json
import logging
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import tqdm
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import and_, or_

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DatasetDB,
    DatasetHardLinkDB,
    EpisodeQcDB,
    TaskStatus,
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
from robocoin_dataset.quality_check.hardlink.make_hardlink import (
    RepoHardLinkCorresp,
    create_hardlinks_from_correspondence,
)
from robocoin_dataset.utils.parquet_paths import get_parquet_paths
from robocoin_dataset.utils.path_utils import (
    get_dataset_video_paths,
    get_episodes_jsonl_file_paths,
    get_episodes_stats_jsonl_file_paths,
    get_meta_info_file_path,
)

BAD_EPISODES = "bad_episodes"
HARD_LINK_PATH = "hard_link_path"

MERGED_FEATURE = "merged"
QCED_FEATURE = "quality_checked"
HL_SUFFIX = "qced_hardlink"


def gen_qced_repo_files(
    repo_path: str | Path,
    bad_episodes: set[int],
    input_feature: str,
    output_feature: str,
) -> dict[str | Path, str | Path]:
    """Remove bad episodes from the dataset repository.

    Args:
        repo_path (str|Path): Path to the dataset repository.
        bad_episodes (set[int]): Set of episode indices to be removed.
        feature_type (str): Type of feature (e.g., 'state', 'action', 'video').
    """
    repo_path = Path(repo_path)
    if not repo_path.exists():
        raise ValueError(f"Repository path does not exist: {repo_path}")

    if repo_path.is_file():
        raise ValueError(f"Repository path is a file: {repo_path}")

    if input_feature == output_feature:
        raise ValueError("Input feature cannot be the same as output feature.")

    _, input_info_file_path = get_meta_info_file_path(repo_path, input_feature)
    _, out_info_file_path = get_meta_info_file_path(repo_path, output_feature)

    input_episodes_jsonl_path, _ = get_episodes_jsonl_file_paths(repo_path, input_feature)
    _, out_episodes_jsonl_path = get_episodes_jsonl_file_paths(repo_path, output_feature)

    _, input_episodes_stats_jsonl_path = get_episodes_stats_jsonl_file_paths(
        repo_path, input_feature
    )
    _, out_episodes_stats_jsonl_path = get_episodes_stats_jsonl_file_paths(
        repo_path, output_feature
    )

    _, input_parquet_paths = get_parquet_paths(repo_path, input_feature)

    episodes_frame_nums = {}
    with open(input_episodes_jsonl_path) as f:
        for line in f:
            data = json.loads(line)
            episode_id = data["episode_index"]
            frame_count = data["length"]
            episodes_frame_nums[episode_id] = frame_count

    sorted_episodes_frame_nums = sorted(episodes_frame_nums.items(), key=lambda x: x[0])
    episodes_frame_nums_list = [frame_num for _, frame_num in sorted_episodes_frame_nums]

    qc_episodes_start_frame_indices = [0]
    for episode_id in range(len(episodes_frame_nums_list)):
        if episode_id in bad_episodes:
            continue
        qc_episodes_start_frame_indices.append(
            qc_episodes_start_frame_indices[-1] + episodes_frame_nums_list[episode_id]
        )

    out_total_frames = sum(
        frame_num
        for ep_idx, frame_num in enumerate(episodes_frame_nums_list)
        if ep_idx not in bad_episodes
    )
    out_total_episodes = len(episodes_frame_nums_list) - len(bad_episodes)

    _gen_output_meta_info_file(
        input_info_file_path, out_info_file_path, out_total_frames, out_total_episodes
    )

    _gen_output_episodes_jsonl_file(
        input_episodes_jsonl_path, out_episodes_jsonl_path, bad_episodes
    )
    _gen_output_episodes_stats_jsonl_file(
        input_episodes_stats_jsonl_path, out_episodes_stats_jsonl_path, bad_episodes
    )

    with open(input_info_file_path) as f:
        data = json.load(f)
        chunks_size = data.get("chunks_size")

    _gen_output_parquet_files(
        repo_path=repo_path,
        input_parquet_paths=input_parquet_paths,
        bad_episodes=bad_episodes,
        qc_episodes_start_frame_indices=qc_episodes_start_frame_indices,
        chunk_size=chunks_size,
        output_feature=output_feature,
    )
    return _gen_video_path_matching_dict(
        input_video_paths=get_dataset_video_paths(repo_path),
        repo_path=repo_path,
        bad_episodes=bad_episodes,
        chunk_size=chunks_size,
    )


def _gen_output_meta_info_file(
    input_info_file_path: Path,
    output_info_file_path: Path,
    total_frames: int,
    total_episodes: int,
) -> None:
    with open(input_info_file_path) as f:
        with open(output_info_file_path, "w") as out_f:
            data = json.load(f)
            input_total_videos = data.get("total_videos")
            input_total_episodes = data.get("total_episodes")
            chunks_size = data.get("chunks_size")
            videos_per_episode = input_total_videos // input_total_episodes

            data["total_frames"] = total_frames
            data["total_episodes"] = total_episodes
            data["total_videos"] = total_episodes * videos_per_episode
            data["total_chunks"] = (total_episodes + chunks_size - 1) // chunks_size
            json.dump(data, out_f)


def _gen_output_episodes_jsonl_file(
    input_episodes_jsonl_path: Path,
    output_episodes_jsonl_path: Path,
    bad_episodes: set[int],
) -> None:
    out_ep_idx = 0
    with open(
        input_episodes_jsonl_path,
    ) as f:
        with open(output_episodes_jsonl_path, "w") as out_f:
            for line in f:
                data = json.loads(line)
                episode_id = data["episode_index"]
                if episode_id in bad_episodes:
                    continue
                data["episode_index"] = out_ep_idx
                out_f.write(json.dumps(data) + "\n")
                out_ep_idx += 1


def _gen_output_episodes_stats_jsonl_file(
    input_episodes_stats_jsonl_path: Path,
    output_episodes_stats_jsonl_path: Path,
    bad_episodes: set[int],
) -> None:
    out_ep_idx = 0
    with open(
        input_episodes_stats_jsonl_path,
    ) as f:
        with open(output_episodes_stats_jsonl_path, "w") as out_f:
            for line in f:
                data = json.loads(line)
                episode_id = data["episode_index"]
                if episode_id in bad_episodes:
                    continue
                data["episode_index"] = out_ep_idx
                out_f.write(json.dumps(data) + "\n")
                out_ep_idx += 1


def _gen_output_parquet_files(
    repo_path: str | Path,
    input_parquet_paths: list[Path],
    bad_episodes: set[int],
    qc_episodes_start_frame_indices: list[int],
    chunk_size: int,
    output_feature: str,
) -> None:
    out_episode_idx = 0
    repo_path = Path(repo_path).expanduser().absolute()

    def get_output_parquet_path(out_ep_idx: int) -> Path:
        chunk_idx = ep_idx // chunk_size
        output_parquet_path = (
            repo_path
            / f"{output_feature}_data"
            / f"chunk-{chunk_idx:03d}"
            / f"episode_{out_ep_idx:06d}.parquet"
        )
        output_parquet_path.parent.mkdir(parents=True, exist_ok=True)
        return output_parquet_path

    for ep_idx, input_parquet_path in tqdm.tqdm(
        enumerate(input_parquet_paths),
        total=len(input_parquet_paths),
        desc="Generating output parquet files",
        unit="episode",
    ):
        if ep_idx in bad_episodes:
            continue
        df = pd.read_parquet(input_parquet_path)
        indices_data = np.array(df["index"].to_list(), dtype=int)
        indices_data = (
            indices_data - indices_data[0] + qc_episodes_start_frame_indices[out_episode_idx]
        )
        df["index"] = indices_data.tolist()
        df["episode_index"] = out_episode_idx
        output_parquet_path = get_output_parquet_path(out_episode_idx)
        df.to_parquet(output_parquet_path, engine="pyarrow")
        out_episode_idx += 1


def _gen_video_path_matching_dict(
    input_video_paths: list[list[Path]],
    repo_path: str | Path,
    bad_episodes: set[int],
    chunk_size: int,
) -> dict[int, list[Path]]:
    repo_path = Path(repo_path).expanduser().absolute()

    def get_video_new_path(ep_video_paths: list[Path], output_ep_idx: int) -> dict[str, str]:
        chunk_idx = output_ep_idx // chunk_size
        results = {}
        for video_path in ep_video_paths:
            new_video_path = (
                repo_path
                / "videos"
                / f"chunk-{chunk_idx:03d}"
                / video_path.parent.name
                / f"episode_{output_ep_idx:06d}.mp4"
            )
            results[str(video_path)] = str(new_video_path)
        return results

    matching_dict = {}

    out_episode_idx = 0
    for ep_idx, video_paths in enumerate(input_video_paths):
        if ep_idx in bad_episodes:
            continue

        matching_dict.update(get_video_new_path(video_paths, out_episode_idx))
        out_episode_idx += 1

    return matching_dict


def gen_qced_repo(
    repo_path: str | Path,
    bad_episodes: set[int],
    input_feature: str = MERGED_FEATURE,
    qced_feature: str = QCED_FEATURE,
    hl_suffix: str = HARD_LINK_PATH,
) -> str:
    repo_path = Path(repo_path).expanduser().absolute()

    video_path_corresp = gen_qced_repo_files(
        repo_path=repo_path,
        bad_episodes=bad_episodes,
        input_feature=input_feature,
        output_feature=qced_feature,
    )
    hard_link_repo_path = repo_path.parent / f"{str(repo_path.name)}_{hl_suffix}"
    file_corresp, dir_corresp = RepoHardLinkCorresp(
        input_feature=qced_feature,
        source_repo_path=repo_path,
        hard_link_repo_path=hard_link_repo_path,
        video_path_corresp=video_path_corresp,
    ).get_hard_link_corresp()
    create_hardlinks_from_correspondence(file_corresp=file_corresp, dir_corresp=dir_corresp)
    return str(hard_link_repo_path)


def _sync_qced_repo_gen_tasks(session: Session) -> None:
    query = session.query(DatasetDB).filter(
        and_(
            # 必要前提：convert必须成功
            DatasetDB.qc_status == TaskStatus.COMPLETED,
            # 两个触发分支
            or_(
                # 分支1: 正在排队
                DatasetDB.qced_repo_gen_status == TaskStatus.PENDING,
                # 分支2: 已完成但版本过期
                and_(
                    DatasetDB.qced_repo_gen_status == TaskStatus.COMPLETED,
                    DatasetDB.qced_repo_gen_version_ps < DatasetDB.qc_version,
                ),
            ),
        )
    )
    items = query.all()

    if not items:
        return

    for item in items:
        if item.qced_repo_gen_status == TaskStatus.COMPLETED:
            item.qced_repo_gen_version = item.qced_repo_gen_version + 1
            continue
        item.qced_repo_gen_status = TaskStatus.PENDING
        item.qced_repo_gen_version_ps = item.qc_version

    session.commit()


def _gen_one_qced_repo_gen_task(
    session: Session,
) -> tuple[str | None, str | None, str | None, str | None]:
    query = session.query(DatasetDB).filter(
        and_(
            # 必要前提：convert必须成功
            DatasetDB.qc_status == TaskStatus.COMPLETED,
            DatasetDB.qced_repo_gen_status == TaskStatus.PENDING,
        )
    )
    item = query.first()

    if not item:
        return None, None

    item.qced_repo_gen_status = TaskStatus.PROCESSING

    session.commit()

    return item.dataset_uuid, item.convert_path


def _get_bad_episodes(
    session: Session,
    dataset_uuid: str,
    state_data_score_threshold: float = 0.85,
    action_data_score_threshold: float = 0.85,
    video_score: float = 0.9,
) -> set[int]:
    items = (
        session.query(EpisodeQcDB)
        .filter(
            EpisodeQcDB.dataset_uuid == dataset_uuid,
        )
        .all()
    )
    if not items:
        return set()

    bad_episodes = set()
    for item in items:
        if item.is_bad_episode:
            bad_episodes.add(item.episode_idx)
            continue
        if item.state_data_score < state_data_score_threshold:
            bad_episodes.add(item.episode_idx)
            continue
        if item.action_data_score < action_data_score_threshold:
            bad_episodes.add(item.episode_idx)
            continue
        if item.video_score < video_score:
            bad_episodes.add(item.episode_idx)

    return bad_episodes


class QualityCheckedRepoGenerator:
    def __init__(
        self,
        db_file_path: str | Path,
        state_data_score_threshold: float = 0.85,
        action_data_score_threshold: float = 0.85,
        video_score_threshold: float = 0.9,
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)
        self.state_data_score_threshold = state_data_score_threshold
        self.action_data_score_threshold = action_data_score_threshold
        self.video_score_threshold = video_score_threshold

    def gen_one_qced_repo(self) -> None:
        with self.db.with_session() as session:
            _sync_qced_repo_gen_tasks(session=session)
            dataset_uuid, repo_path = _gen_one_qced_repo_gen_task(session=session)
            bad_episodes = _get_bad_episodes(
                session=session,
                dataset_uuid=dataset_uuid,
                state_data_score_threshold=self.state_data_score_threshold,
                action_data_score_threshold=self.action_data_score_threshold,
                video_score=self.video_score_threshold,
            )

        if not dataset_uuid:
            return

        try:
            hardlink_repo_path = gen_qced_repo(repo_path=repo_path, bad_episodes=bad_episodes)
            with self.db.with_session() as session:
                ds_item = (
                    session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
                )
                if not ds_item:
                    return
                ds_item.qced_repo_gen_status = TaskStatus.COMPLETED
                hardlink_item = (
                    session.query(DatasetHardLinkDB)
                    .filter(DatasetHardLinkDB.dataset_uuid == dataset_uuid)
                    .first()
                )
                if hardlink_item:
                    hardlink_item.hard_link_path = hardlink_repo_path
                else:
                    session.add(
                        DatasetHardLinkDB(
                            dataset_uuid=dataset_uuid,
                            hard_link_path=hardlink_repo_path,
                        )
                    )
                session.commit()
        except Exception:
            with self.db.with_session() as session:
                ds_item = (
                    session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
                )
                if ds_item:
                    ds_item.qced_repo_gen_status = TaskStatus.FAILED
                    ds_item.qced_repo_gen_err_msg = traceback.format_exc()
                else:
                    return
                session.commit()
            self.logger.info(traceback.format_exc())


class QualityCheckedRepoGeneratorServer(TaskServer):
    def __init__(
        self,
        db_file_path: str | Path,
        host: str = "0.0.0.0",
        port: int = 2010,
        heartbeat_interval: float = 30.0,  # 服务端每30秒发一次 ping
        timeout: float = 15.0,  # 等待 pong 超过15秒则断开
        logger: logging.Logger | None = None,
        state_data_score_threshold: float = 0.85,
        action_data_score_threshold: float = 0.85,
        video_score_threshold: float = 0.9,
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

        self.state_data_score_threshold = state_data_score_threshold
        self.action_data_score_threshold = action_data_score_threshold
        self.video_score_threshold = video_score_threshold

    def get_task_category(self) -> str:
        return "dataset quality checked repo generation"

    def generate_task_content(self) -> dict | None:
        with self.db.with_session() as session:
            _sync_qced_repo_gen_tasks(session=session)
            dataset_uuid, repo_path = _gen_one_qced_repo_gen_task(session=session)
            bad_episodes = _get_bad_episodes(
                session=session,
                dataset_uuid=dataset_uuid,
                state_data_score_threshold=self.state_data_score_threshold,
                action_data_score_threshold=self.action_data_score_threshold,
                video_score=self.video_score_threshold,
            )
            bad_episodes = list(bad_episodes)

        if not dataset_uuid:
            return None
        return {
            DATASET_UUID: dataset_uuid,
            LEFORMAT_PATH: repo_path,
            BAD_EPISODES: bad_episodes,
        }

    def handle_task_result(self, task_content: dict, task_result_content: dict) -> None:
        ds_uuid = task_content.get(DATASET_UUID)

        task_status = task_result_content.get(TASK_RESULT_STATUS)
        task_status_msg = task_result_content.get(ERR_MSG)

        err_msg = task_result_content.get(ERR_MSG)
        hardlink_path = task_result_content.get(TASK_RESULT_CONTENT).get(HARD_LINK_PATH)

        if task_status == TASK_SUCCESS:
            with self.db.with_session() as session:
                item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == ds_uuid).first()
                if item:
                    item.qced_repo_gen_status = TaskStatus.COMPLETED
                else:
                    return
                hl_item = (
                    session.query(DatasetHardLinkDB)
                    .filter(DatasetHardLinkDB.dataset_uuid == ds_uuid)
                    .first()
                )
                if hl_item:
                    hl_item.hard_link_path = hardlink_path
                else:
                    session.add(
                        DatasetHardLinkDB(
                            dataset_uuid=ds_uuid,
                            hard_link_path=hardlink_path,
                        )
                    )
                session.commit()
        else:
            with self.db.with_session() as session:
                item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == ds_uuid).first()
                if item:
                    item.qced_repo_gen_status = TaskStatus.FAILED
                    item.qced_repo_gen_status = err_msg
                else:
                    return
                session.commit()

            self.logger.info(
                f"Upsert {item.convert_path} dataset quality checked repo generation status to {item.qced_repo_gen_status}, "
                f"update_message: {task_status_msg}"
            )


class QualityCheckedRepoGeneratorClient(TaskClient):
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
        return "dataset quality checked repo generation"

    def generate_task_request_desc(self) -> dict:
        """客户端可自定义任务请求参数"""
        return {}

    def _sync_process_task(self, task_content: dict) -> dict:
        try:
            repo_path = task_content.get(LEFORMAT_PATH)
            bad_episodes = task_content.get(BAD_EPISODES)
            bad_episodes = set(bad_episodes)

            hardlink_repo_path = gen_qced_repo(repo_path=repo_path, bad_episodes=bad_episodes)

            return {HARD_LINK_PATH: hardlink_repo_path}
        except Exception as e:
            raise RuntimeError(f"dataset quality checked repo generation {repo_path} failed") from e
