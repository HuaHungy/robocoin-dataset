import logging
import traceback
from pathlib import Path

import tqdm
from sqlalchemy import and_, or_

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DatasetDB,
    TaskStatus,
    UrlVideoStAnnotationDB,
    VideoMatchDB,
    VideoStAnnotationDB,
)


class DatasetSubtaskAnnotation:
    def __init__(
        self,
        db_file_path: str | Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)

    def sync_dataset_subtask_annotation_status(self) -> None:
        with self.db.with_session() as session:
            query = session.query(DatasetDB).filter(
                and_(
                    # 必要前提：convert必须成功
                    DatasetDB.video_match_status == TaskStatus.COMPLETED,
                    # 两个触发分支
                    or_(
                        # 分支1: 正在排队
                        DatasetDB.video_ori_subtask_annotation_status == TaskStatus.PENDING,
                        # 分支2: 已完成但版本过期
                        and_(
                            DatasetDB.video_ori_subtask_annotation_status == TaskStatus.COMPLETED,
                            DatasetDB.video_ori_subtask_annotation_version_ps
                            < DatasetDB.video_match_version,
                        ),
                    ),
                )
            )

            for item in query.all():
                item.video_ori_subtask_annotation_status = TaskStatus.PENDING
                item.video_ori_subtask_annotation_version_ps = item.video_match_version
            session.commit()

    def gen_one_dataset_subtask_annotation_task(self) -> str:
        with self.db.with_session() as session:
            query = session.query(DatasetDB).filter(
                and_(
                    DatasetDB.video_match_status == TaskStatus.COMPLETED,
                    DatasetDB.video_ori_subtask_annotation_status == TaskStatus.PENDING,
                )
            )
            item = query.first()
            if not item:
                return None

            item.video_ori_subtask_annotation_version = (
                item.video_ori_subtask_annotation_version + 1
            )
            item.video_ori_subtask_annotation_status = TaskStatus.PROCESSING
            session.commit()
            return item.dataset_uuid

    def _annotate_subtask(self, dataset_uuid: str) -> None:
        with self.db.with_session() as session:
            session.query(VideoStAnnotationDB).filter(
                VideoStAnnotationDB.dataset_uuid == dataset_uuid
            ).delete()
            items = (
                session.query(VideoMatchDB).filter(VideoMatchDB.dataset_uuid == dataset_uuid).all()
            )
            if not items:
                session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).update(
                    {
                        DatasetDB.video_ori_subtask_annotation_status: TaskStatus.FAILED,
                        DatasetDB.video_ori_subtask_annotation_err_msg: "No video match result found",
                    }
                )
                session.commit()
                return
            try:
                for item in items:
                    url_anno_items = (
                        session.query(UrlVideoStAnnotationDB)
                        .filter(UrlVideoStAnnotationDB.video_id == item.url_video_id)
                        .all()
                    )
                    for url_anno_item in url_anno_items:
                        video_anno_item = VideoStAnnotationDB(
                            dataset_uuid=dataset_uuid,
                            episode_idx=item.episode_idx,
                            start_frame_idx=url_anno_item.start_frame_idx,
                            end_frame_idx=url_anno_item.end_frame_idx,
                            annotation=url_anno_item.annotation,
                        )
                        session.add(video_anno_item)

                session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).update(
                    {
                        DatasetDB.video_ori_subtask_annotation_status: TaskStatus.COMPLETED,
                    }
                )
                session.commit()
            except Exception:
                session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).update(
                    {
                        DatasetDB.video_ori_subtask_annotation_status: TaskStatus.FAILED,
                        DatasetDB.video_ori_subtask_annotation_err_msg: traceback.format_exc(),
                    }
                )
                session.commit()

    def annotate_subtask(self) -> None:
        self.sync_dataset_subtask_annotation_status()

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
            self._annotate_subtask(dataset_uuid=dataset_uuid)
            pbar.update(1)

        pbar.close()
