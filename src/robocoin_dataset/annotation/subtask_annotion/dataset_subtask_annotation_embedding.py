import logging
import traceback
from collections import defaultdict
from pathlib import Path

import numpy as np
import tqdm
from sqlalchemy import and_, or_

from robocoin_dataset.data_post_process import DataPostProcessorBase
from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DatasetDB,
    TaskStatus,
    VideoHashDB,
    VideoOptStAnnotationDB,
)


def annotations_to_frame_array(
    annotations: list[tuple[int, int, int, int]],
    annotation_num: int,
    episode_frame_nums: dict[int, int],
    max_st_num: int = 5,
) -> list[np.ndarray]:
    episodes = defaultdict(list)
    for ann in annotations:
        ep_idx, start, end, data = ann
        episodes[ep_idx].append((start, end, data))

    result = []
    episode_indices = sorted(episodes.keys())

    for ep_idx in episode_indices:
        anns = episodes[ep_idx]

        max_frame = episode_frame_nums[ep_idx]

        # 明确指定 dtype=np.int32
        frame_array = np.full(
            (max_frame, max_st_num),
            annotation_num,
            dtype=np.int32,  # 👈 指定为 int32
        )

        for start, end, data in anns:
            if isinstance(data, int):
                data = [data]
            elif isinstance(data, (list, tuple)):
                data = list(data)
            else:
                raise ValueError("int_data must be int or list/tuple of int")

            # 截断到 n
            data = data[:max_st_num]
            # 转为 int32 数组
            data_arr = np.array(data, dtype=np.int32)

            for frame_idx in range(start, end - 1):
                if frame_idx < max_frame:
                    frame_array[frame_idx, : len(data_arr)] = data_arr

        result.append(frame_array)

    return result


class StAnnotationDataPostProcessor(DataPostProcessorBase):
    def __init__(
        self,
        convert_path: str | Path,
        subtask_annotations: list[str],
        episode_st_indices: list[np.ndarray],
    ) -> None:
        self.feature_key = "subtask_annotation"
        super().__init__(
            convert_path=convert_path,
            data_post_process_type=self.feature_key,
            data_feature_keys=[self.feature_key],
        )

        self.subtask_annotations = subtask_annotations
        self.episode_st_indices = episode_st_indices

    def prepare_processing(self) -> None:
        self.write_subtask_jsonl_file()

    def process_episode_data(self, ori_data: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        ep_idx = self.episode_idx

        if ep_idx >= len(self.episode_st_indices):
            raise ValueError(
                f"ep_idx: {ep_idx} >= len(self.episode_st_indices): {len(self.episode_st_indices)}"
            )

        return {self.feature_key: self.episode_st_indices[ep_idx]}

    def get_modified_feature_names(self) -> dict[str, list[str]]:
        return {self.feature_key: None}

    def write_subtask_jsonl_file(self) -> None:
        subtask_jsonl_file_path = self.convert_path / "annotations/subtask_annotations.jsonl"
        subtask_jsonl_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(subtask_jsonl_file_path, "w") as f:
            for i, annotation in enumerate(self.subtask_annotations):
                f.write(f'{{"subtask_index": {i}, "subtask": "{annotation}"}}\n')
            f.write(f'{{"subtask_index": {len(self.subtask_annotations)}, "subtask": "null"}}\n')


class DatasetSubtaskAnnotationEmbedding:
    def __init__(
        self,
        db_file_path: str | Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)

    def sync_dataset_subtask_annotation_embedding_status(self) -> None:
        with self.db.with_session() as session:
            query = session.query(DatasetDB).filter(
                and_(
                    # 必要前提：convert必须成功
                    DatasetDB.video_opt_subtask_annotation_status == TaskStatus.COMPLETED,
                    # 两个触发分支
                    or_(
                        # 分支1: 正在排队
                        DatasetDB.video_embed_subtask_annotation_status == TaskStatus.PENDING,
                        # 分支2: 已完成但版本过期
                        and_(
                            DatasetDB.video_embed_subtask_annotation_status == TaskStatus.COMPLETED,
                            DatasetDB.video_embed_subtask_annotation_version_ps
                            < DatasetDB.video_opt_subtask_annotation_version,
                        ),
                    ),
                )
            )

            for item in query.all():
                item.video_embed_subtask_annotation_status = TaskStatus.PENDING
                item.video_embed_subtask_annotation_version = (
                    item.video_embed_subtask_annotation_version + 1
                )
                item.video_embed_subtask_annotation_version_ps = (
                    item.video_opt_subtask_annotation_version
                )
            session.commit()

    def gen_one_dataset_subtask_annotation_optimization_task(self) -> tuple[str, str]:
        with self.db.with_session() as session:
            query = session.query(DatasetDB).filter(
                and_(
                    DatasetDB.video_opt_subtask_annotation_status == TaskStatus.COMPLETED,
                    DatasetDB.video_embed_subtask_annotation_status == TaskStatus.PENDING,
                )
            )
            item = query.first()
            if not item:
                return None, None

            item.video_embed_subtask_annotation_status = TaskStatus.PROCESSING
            session.commit()
            return item.dataset_uuid, item.convert_path

    def _embed_subtask_annotation(self, dataset_uuid: str, repo_path: str | Path) -> None:
        repo_path = Path(repo_path).expanduser().absolute()
        with self.db.with_session() as session:
            items = (
                session.query(VideoOptStAnnotationDB)
                .filter(VideoOptStAnnotationDB.dataset_uuid == dataset_uuid)
                .all()
            )
            if not items:
                return
            optimized_subtask_annotations_list = list(set([item.annotation for item in items]))
            optimized_subtask_annotations_dict = {
                annotation: i for i, annotation in enumerate(optimized_subtask_annotations_list)
            }

            annotations = []
            for item in items:
                annotation_idx = optimized_subtask_annotations_dict[item.annotation]
                annotations.append(
                    (item.episode_idx, item.start_frame_idx, item.end_frame_idx, annotation_idx)
                )

            ep_items = (
                session.query(VideoHashDB).filter(VideoHashDB.dataset_uuid == dataset_uuid).all()
            )
            episode_frame_nums = {}

            for ep_item in ep_items:
                episode_frame_nums[ep_item.ep_idx] = ep_item.frame_num

        try:
            annotation_datas = annotations_to_frame_array(
                annotations=annotations,
                annotation_num=len(optimized_subtask_annotations_dict),
                max_st_num=5,
                episode_frame_nums=episode_frame_nums,
            )

            processor = StAnnotationDataPostProcessor(
                convert_path=repo_path,
                subtask_annotations=optimized_subtask_annotations_list,
                episode_st_indices=annotation_datas,
            )
            processor.process()
            with self.db.with_session() as session:
                session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).update(
                    {
                        DatasetDB.video_embed_subtask_annotation_status: TaskStatus.COMPLETED,
                    }
                )
                session.commit()
        except Exception:
            self.logger.error(
                f"Error when embedding subtask annotation for dataset {dataset_uuid}: {traceback.format_exc()}"
            )
            with self.db.with_session() as session:
                session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).update(
                    {
                        DatasetDB.video_embed_subtask_annotation_status: TaskStatus.FAILED,
                        DatasetDB.video_embed_subtask_annotation_err_msg: traceback.format_exc(),
                    }
                )

    def embed_subtask_annotation(self) -> None:
        self.sync_dataset_subtask_annotation_embedding_status()
        with self.db.with_session() as session:
            task_num = (
                session.query(DatasetDB)
                .filter(
                    and_(
                        DatasetDB.video_opt_subtask_annotation_status == TaskStatus.COMPLETED,
                        DatasetDB.video_embed_subtask_annotation_status == TaskStatus.PENDING,
                    )
                )
                .count()
            )
        pbar = tqdm.tqdm(
            total=task_num, desc="Embed subtask annotation for datasets", unit="dataset"
        )
        while True:
            dataset_uuid, repo_path = self.gen_one_dataset_subtask_annotation_optimization_task()
            if dataset_uuid is None:
                break
            self._embed_subtask_annotation(dataset_uuid=dataset_uuid, repo_path=repo_path)
            pbar.update(1)

        pbar.close()
