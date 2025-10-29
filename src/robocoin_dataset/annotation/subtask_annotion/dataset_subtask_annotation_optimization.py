import logging
from pathlib import Path

import tqdm
from sqlalchemy import and_, or_

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DatasetDB,
    TaskStatus,
    UrlVideoStAnnotationDB,
    VideoOptStAnnotationDB,
    VideoStAnnotationDB,
)


class DatasetSubtaskAnnotationOptimization:
    def __init__(
        self,
        db_file_path: str | Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)

    def sync_dataset_subtask_annotation_optimization_status(self) -> None:
        with self.db.with_session() as session:
            query = session.query(DatasetDB).filter(
                and_(
                    # 必要前提：convert必须成功
                    DatasetDB.video_ori_subtask_annotation_status == TaskStatus.COMPLETED,
                    # 两个触发分支
                    or_(
                        # 分支1: 正在排队
                        DatasetDB.video_opt_subtask_annotation_status == TaskStatus.PENDING,
                        # 分支2: 已完成但版本过期
                        and_(
                            DatasetDB.video_opt_subtask_annotation_status == TaskStatus.COMPLETED,
                            DatasetDB.video_opt_subtask_annotation_version_ps
                            < DatasetDB.video_ori_subtask_annotation_version,
                        ),
                    ),
                )
            )

            for item in query.all():
                item.video_opt_subtask_annotation_status = TaskStatus.PENDING
                item.video_opt_subtask_annotation_status = (
                    item.video_opt_subtask_annotation_status + 1
                )
                item.video_opt_subtask_annotation_version_ps = (
                    item.video_ori_subtask_annotation_version
                )
            session.commit()

    def gen_one_dataset_subtask_annotation_optimization_task(self) -> str:
        with self.db.with_session() as session:
            query = session.query(DatasetDB).filter(
                and_(
                    DatasetDB.video_ori_subtask_annotation_status == TaskStatus.COMPLETED,
                    DatasetDB.video_opt_subtask_annotation_status == TaskStatus.PENDING,
                )
            )
            item = query.first()
            if not item:
                return None

            item.video_opt_subtask_annotation_status = TaskStatus.PROCESSING
            return item.dataset_uuid

    def _optimize_subtask_annotation(self, dataset_uuid: str) -> None:
        with self.db.with_session() as session:
            session.query(VideoOptStAnnotationDB).filter(
                VideoOptStAnnotationDB.dataset_uuid == dataset_uuid
            ).delete()
            items = (
                session.query(VideoStAnnotationDB)
                .filter(VideoStAnnotationDB.dataset_uuid == dataset_uuid)
                .all()
            )
            if not items:
                return
            for item in items:
                video_opt_anno_item = VideoOptStAnnotationDB(
                        dataset_uuid=dataset_uuid,
                        episode_idx=item.episode_idx,
                        start_frame_idx=url_anno_item.start_frame_idx,
                        end_frame_idx=url_anno_item.end_frame_idx,
                        annotation=url_anno_item.annotation,
                    )
                    session.add(video_anno_item)
            session.commit()

    def subtask_annotation(self) -> None:
        with self.db.with_session() as session:
            task_num = (
                session.query(DatasetDB)
                .filter(
                    and_(
                        DatasetDB.video_match_status == TaskStatus.COMPLETED,
                        DatasetDB.video_ori_subtask_annotation_status == TaskStatus.PENDING,
                    )
                )
                .count()
            )
        pbar = tqdm.tqdm(total=task_num, desc="Annotate subtask for datasets", unit="dataset")
        while True:
            dataset_uuid = self.gen_one_dataset_subtask_annotation_task()
            if dataset_uuid is None:
                break
            self._subtask_annotate(dataset_uuid=dataset_uuid)
            pbar.update(1)

        pbar.close()
