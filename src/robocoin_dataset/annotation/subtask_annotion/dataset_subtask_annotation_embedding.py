import logging
import traceback
from pathlib import Path

import tqdm
from sqlalchemy import and_, or_

from robocoin_dataset.data_post_process import DataPostProcessorBase
from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DatasetDB,
    TaskStatus,
    VideoOptStAnnotationDB,
)


class StAnnotationDataPostProcessor(DataPostProcessorBase):
    def __init__(
        self,
        convert_path: str | Path,
    ) -> None:
        super().__init__(
            convert_path=convert_path,
            data_post_process_type="subtask_annotation",
            data_feature_keys=["subtask_annotation"],
        )

        


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

    def gen_one_dataset_subtask_annotation_optimization_task(self) -> str:
        with self.db.with_session() as session:
            query = session.query(DatasetDB).filter(
                and_(
                    DatasetDB.video_opt_subtask_annotation_status == TaskStatus.COMPLETED,
                    DatasetDB.video_embed_subtask_annotation_status == TaskStatus.PENDING,
                )
            )
            item = query.first()
            if not item:
                return None

            item.video_embed_subtask_annotation_status = TaskStatus.PROCESSING
            return item.dataset_uuid

    def _embed_subtask_annotation(self, dataset_uuid: str) -> None:
        with self.db.with_session() as session:
            items = (
                session.query(VideoStAnnotationDB)
                .filter(VideoStAnnotationDB.dataset_uuid == dataset_uuid)
                .all()
            )
            if not items:
                return
            original_subtask_annotations = set([item.annotation for item in items])

        try:
            optimized_annotation_dict = optimize_annotation(
                annotation_set=original_subtask_annotations, ds_api_key=self.ds_api_key
            )
            with self.db.with_session() as session:
                session.query(VideoOptStAnnotationDB).filter(
                    VideoOptStAnnotationDB.dataset_uuid == dataset_uuid
                ).delete()

                ori_items = (
                    session.query(VideoStAnnotationDB)
                    .filter(VideoStAnnotationDB.dataset_uuid == dataset_uuid)
                    .all()
                )
                for ori_item in ori_items:
                    new_annotation = optimized_annotation_dict.get(ori_item.annotation)
                    if new_annotation:
                        session.add(
                            VideoOptStAnnotationDB(
                                dataset_uuid=dataset_uuid,
                                episode_idx=ori_item.episode_idx,
                                start_frame_idx=ori_item.start_frame_idx,
                                end_frame_idx=ori_item.end_frame_idx,
                                annotation=ori_item.annotation,
                            )
                        )
                session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).update(
                    {
                        DatasetDB.video_opt_subtask_annotation_status: TaskStatus.COMPLETED,
                    }
                )
                session.commit()

        except Exception as e:
            self.logger.error(f"Failed to optimize annotation for {dataset_uuid}: {e}")
            with self.db.with_session() as session:
                session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).update(
                    {
                        DatasetDB.video_opt_subtask_annotation_status: TaskStatus.FAILED,
                        DatasetDB.video_opt_subtask_annotation_err_msg: traceback.format_exc(),
                    }
                )
                session.commit()

    def optimize_subtask_annotation(self) -> None:
        with self.db.with_session() as session:
            task_num = (
                session.query(DatasetDB)
                .filter(
                    and_(
                        DatasetDB.video_ori_subtask_annotation_status == TaskStatus.COMPLETED,
                        DatasetDB.video_opt_subtask_annotation_status == TaskStatus.PENDING,
                    )
                )
                .count()
            )
        pbar = tqdm.tqdm(total=task_num, desc="Annotate subtask for datasets", unit="dataset")
        while True:
            dataset_uuid = self.gen_one_dataset_subtask_annotation_optimization_task()
            if dataset_uuid is None:
                break
            self._optimize_subtask_annotation(dataset_uuid=dataset_uuid)
            pbar.update(1)

        pbar.close()
