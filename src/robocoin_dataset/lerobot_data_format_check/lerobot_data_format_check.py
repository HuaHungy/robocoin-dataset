import logging
from pathlib import Path

from sqlalchemy import and_, not_
from sqlalchemy.orm import Session

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DmvAnnotationDB,
    LeFormatConvertDB,
    LeformatDatasetSimReplayStatusDB,
    TaskStatus,
)


class LerobotDataFormatCheck:
    def __init__(
        self,
        db_file_path: str | Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)

    def _get_convert_path(self, dataset_uuid: str) -> str:
        with self.db.with_session() as session:
            item = (
                session.query(LeFormatConvertDB)
                .filter(LeFormatConvertDB.dataset_uuid == dataset_uuid)
                .first()
            )
            if item:
                return item.convert_path
            return None

    def _upsert_leformat_dataset_simulation_replay_status(
        self,
        session: Session,
        dataset_uuid: str,
        convert_path: str,
        status: TaskStatus,
        err_msg: str = "",
    ) -> None:
        item = (
            session.query(LeformatDatasetSimReplayStatusDB)
            .filter(LeformatDatasetSimReplayStatusDB.dataset_uuid == dataset_uuid)
            .first()
        )
        if item:
            item.convert_path = convert_path
            item.status = status
            item.err_msg = err_msg
        else:
            item = LeformatDatasetSimReplayStatusDB(
                dataset_uuid=dataset_uuid,
                convert_path=convert_path,
                status=status,
                err_msg=err_msg,
            )
            session.add(item)
        session.commit()

    def _sync_sim_replay_tasks(self, device_model: str | None = None) -> None:
        with self.db.with_session() as session:
            if device_model is not None:
                items = (
                    session.query(LeFormatConvertDB)
                    .join(
                        DmvAnnotationDB,
                        LeFormatConvertDB.dataset_uuid == DmvAnnotationDB.dataset_uuid,
                    )
                    .filter(LeFormatConvertDB.convert_status == TaskStatus.COMPLETED)
                    .filter(
                        not_(
                            session.query(LeformatDatasetSimReplayStatusDB)
                            .filter(
                                LeformatDatasetSimReplayStatusDB.dataset_uuid
                                == LeFormatConvertDB.dataset_uuid
                            )
                            .exists()
                        )
                    )
                    .filter(
                        DmvAnnotationDB.device_model == device_model  # 新增：设备型号筛选
                    )
                ).all()
            else:
                items = (
                    session.query(LeFormatConvertDB)
                    .filter(LeFormatConvertDB.convert_status == TaskStatus.COMPLETED)
                    .filter(
                        not_(
                            session.query(LeformatDatasetSimReplayStatusDB)
                            .filter(
                                LeformatDatasetSimReplayStatusDB.dataset_uuid
                                == LeFormatConvertDB.dataset_uuid
                            )
                            .exists()
                        )
                    )
                ).all()
        items = list(items)
        for item in items:
            with self.db.with_session() as session:
                self._upsert_leformat_dataset_simulation_replay_status(
                    session,
                    dataset_uuid=item.dataset_uuid,
                    convert_path=item.convert_path,
                    status=TaskStatus.PENDING,
                )

    def _gen_one_sim_replay_task(self, device_model: str) -> str | None:
        with self.db.with_session() as session:
            item = (
                session.query(LeformatDatasetSimReplayStatusDB)
                .join(
                    DmvAnnotationDB,
                    LeformatDatasetSimReplayStatusDB.dataset_uuid == DmvAnnotationDB.dataset_uuid,
                )
                .filter(
                    and_(
                        LeformatDatasetSimReplayStatusDB.status == TaskStatus.PENDING,
                        DmvAnnotationDB.device_model == device_model,
                    )
                )
                .first()
            )
            if not item:
                return None
            item.status = TaskStatus.PROCESSING
            session.commit()
            return item.dataset_uuid

    def sim_replay_datasets(self, device_model: str) -> None:
        self._sync_sim_replay_tasks(device_model)
        dataset_uuid = self._gen_one_sim_replay_task(device_model=device_model)
        if dataset_uuid is None:
            return
        convert_path = self._get_convert_path(dataset_uuid)
        try:
            self._sim_replay_dataset(dataset_uuid)
            with self.db.with_session() as session:
                self._upsert_leformat_dataset_simulation_replay_status(
                    session=session,
                    dataset_uuid=dataset_uuid,
                    convert_path=convert_path,
                    status=TaskStatus.COMPLETED,
                )

        except Exception as e:
            with self.db.with_session() as session:
                self._upsert_leformat_dataset_simulation_replay_status(
                    session=session,
                    dataset_uuid=dataset_uuid,
                    convert_path=convert_path,
                    status=TaskStatus.FAILED,
                    err_msg=str(e),
                )
