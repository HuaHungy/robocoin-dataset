import logging
import traceback
import uuid
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import not_
from tqdm import tqdm

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DmvAnnotationDB,
    LeFormatConvertDB,
    LeformatDateasetStateActionPostProcessingStatusDB,
    TaskStatus,
)
from robocoin_dataset.state_action_data_post_process.processors.state_action_data_processor_base import (
    StateActionDataPostProcessorBase,
)


class StateActionDataPostProcess:
    def __init__(
        self,
        db_file_path: str | Path,
        processor_classes: dict[tuple[str, str], StateActionDataPostProcessorBase],
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.processor_classes = processor_classes
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

    def _get_dataset_device_model_info(self, dataset_uuid: str) -> tuple[str, str]:
        with self.db.with_session() as session:
            item = (
                session.query(DmvAnnotationDB)
                .filter(LeFormatConvertDB.dataset_uuid == dataset_uuid)
                .first()
            )
            if item:
                return item.device_model, item.device_model_version
            return None, None

    def _upsert_parquet_post_process_status(
        self,
        session: Session,
        dataset_uuid: str,
        convert_path: str,
        status: TaskStatus,
        device_model: str,
        device_model_version: str,
        err_msg: str = "",
        prestage_version_uuid: str = "",
    ) -> None:
        item = (
            session.query(LeformatDateasetStateActionPostProcessingStatusDB)
            .filter(LeformatDateasetStateActionPostProcessingStatusDB.dataset_uuid == dataset_uuid)
            .first()
        )

        version_uuid = str(uuid.uuid4())
        if item:
            item.convert_path = convert_path
            item.status = status
            item.err_msg = err_msg
            item.device_model = device_model
            item.device_model_version = device_model_version
            item.prestage_version_uuid = prestage_version_uuid
            item.version_uuid = version_uuid
        else:
            item = LeformatDateasetStateActionPostProcessingStatusDB(
                dataset_uuid=dataset_uuid,
                convert_path=convert_path,
                status=status,
                err_msg=err_msg,
                device_model=device_model,
                device_model_version=device_model_version,
                prestage_version_uuid=prestage_version_uuid,
                version_uuid=version_uuid,
            )
            session.add(item)
        session.commit()

    def _copy_data_and_info(self, convert_path: str) -> None:
        convert_path: Path = Path(convert_path).expanduser().absolute()
        if not convert_path.exists():
            raise FileNotFoundError(f"convert_path {convert_path} not exists")

        import shutil

        data_dir = convert_path / "data"
        new_data_dir = convert_path / "ppp_data"
        if new_data_dir.exists():
            shutil.rmtree(new_data_dir)

        shutil.copytree(data_dir, new_data_dir)

        shutil.copyfile(convert_path / "meta/info.json", convert_path / "meta/ppp_info.json")

    def _sync_parquet_post_processing_tasks(
        self, device_model: str | None = None, device_model_version: str | None = None
    ) -> None:
        with self.db.with_session() as session:
            query = (
                session.query(LeFormatConvertDB)
                .join(
                    DmvAnnotationDB,
                    LeFormatConvertDB.dataset_uuid == DmvAnnotationDB.dataset_uuid,
                )
                .filter(LeFormatConvertDB.convert_status == TaskStatus.COMPLETED)
                .filter(
                    not_(
                        session.query(LeformatDateasetStateActionPostProcessingStatusDB)
                        .filter(
                            LeformatDateasetStateActionPostProcessingStatusDB.dataset_uuid
                            == LeFormatConvertDB.dataset_uuid
                        )
                        .filter(
                            LeformatDateasetStateActionPostProcessingStatusDB.prestage_version_uuid
                            == LeFormatConvertDB.version_uuid
                        )
                        .exists()
                    )
                )
            )
            if device_model is not None:
                query = query.filter(DmvAnnotationDB.device_model == device_model)

            if device_model_version is not None:
                query = query.filter(DmvAnnotationDB.device_model_version == device_model_version)

            convert_items = query.all()

        if not convert_items:
            return
        for convert_item in convert_items:
            with self.db.with_session() as session:
                dmv_item = (
                    session.query(DmvAnnotationDB)
                    .filter(DmvAnnotationDB.dataset_uuid == convert_item.dataset_uuid)
                    .first()
                )
                if dmv_item is None:
                    dmv_device_model = None
                    dmv_device_model = None
                else:
                    dmv_device_model = dmv_item.device_model
                    dmv_device_model_version = dmv_item.device_model_version
                self._upsert_parquet_post_process_status(
                    session,
                    dataset_uuid=convert_item.dataset_uuid,
                    convert_path=convert_item.convert_path,
                    status=TaskStatus.PENDING,
                    prestage_version_uuid=convert_item.version_uuid,
                    device_model=dmv_device_model,
                    device_model_version=dmv_device_model_version,
                )

    def _gen_one_parquet_post_process_task(
        self, device_model: str | None = None, device_model_version: str | None = None
    ) -> tuple[str, str, str, str]:
        with self.db.with_session() as session:
            query = session.query(LeformatDateasetStateActionPostProcessingStatusDB).filter(
                LeformatDateasetStateActionPostProcessingStatusDB.status == TaskStatus.PENDING,
            )
            if device_model is not None:
                query = query.filter(
                    LeformatDateasetStateActionPostProcessingStatusDB.device_model == device_model
                )

            if device_model_version is not None:
                query = query.filter(
                    LeformatDateasetStateActionPostProcessingStatusDB.device_model_version
                    == device_model_version
                )
            item = query.first()
            if not item:
                return None, None, None, None
            item.status = TaskStatus.PROCESSING
            session.commit()
            return (
                item.dataset_uuid,
                item.prestage_version_uuid,
                item.device_model,
                item.device_model_version,
            )

    def _post_process_parquet(
        self, convert_path: str | Path, device_model: str, device_model_version: str
    ) -> None:
        processor_class = self.processor_classes.get((device_model, device_model_version), None)
        if processor_class is None:
            raise RuntimeError(
                f"No post processor found for device model {device_model} and device model version {device_model_version}"
            )
        processor: StateActionDataPostProcessorBase = processor_class(convert_path=convert_path)
        processor.process()

    def _get_parquet_post_process_task_num(
        self,
        device_model: str | None = None,
        device_model_version: str | None = None,
    ) -> int:
        with self.db.with_session() as session:
            query = session.query(LeformatDateasetStateActionPostProcessingStatusDB).filter(
                LeformatDateasetStateActionPostProcessingStatusDB.status == TaskStatus.PENDING,
            )
            if device_model is not None:
                query = query.filter(
                    LeformatDateasetStateActionPostProcessingStatusDB.device_model == device_model
                )
                if device_model_version is not None:
                    query = query.filter(
                        LeformatDateasetStateActionPostProcessingStatusDB.device_model_version
                        == device_model_version
                    )
            return query.count()

    def post_process_parquet(
        self, device_model: str | None, device_model_version: str | None
    ) -> None:
        self._sync_parquet_post_processing_tasks(
            device_model, device_model_version=device_model_version
        )
        task_num = self._get_parquet_post_process_task_num(
            device_model=device_model, device_model_version=device_model_version
        )
        if task_num == 0:
            return
        for _ in tqdm(range(task_num), desc="state and action post process", unit="dataset"):
            dataset_uuid, prestage_version_uuid, device_model, device_model_version = (
                self._gen_one_parquet_post_process_task(
                    device_model=device_model, device_model_version=device_model_version
                )
            )
            if dataset_uuid is None:
                break
            convert_path = self._get_convert_path(dataset_uuid)
            try:
                self._post_process_parquet(
                    convert_path=convert_path,
                    device_model=device_model,
                    device_model_version=device_model_version,
                )
                with self.db.with_session() as session:
                    self._upsert_parquet_post_process_status(
                        session=session,
                        dataset_uuid=dataset_uuid,
                        convert_path=convert_path,
                        status=TaskStatus.COMPLETED,
                        device_model=device_model,
                        device_model_version=device_model_version,
                        prestage_version_uuid=prestage_version_uuid,
                    )

            except Exception:
                self.logger.error(
                    f"Failed to post process state and action data for dataset {dataset_uuid}, traceback: {traceback.format_exc()}"
                )
                with self.db.with_session() as session:
                    self._upsert_parquet_post_process_status(
                        session=session,
                        dataset_uuid=dataset_uuid,
                        convert_path=convert_path,
                        status=TaskStatus.FAILED,
                        prestage_version_uuid=prestage_version_uuid,
                        device_model=device_model,
                        device_model_version=device_model_version,
                        err_msg=traceback.format_exc(),
                    )
