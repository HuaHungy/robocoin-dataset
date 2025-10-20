import logging
from pathlib import Path

from sqlalchemy import not_
from sqlalchemy.orm import Session
from tqdm import tqdm

from robocoin_dataset.annotation.motion_annotation.compute_lerobot_eef import LerobotFkSolver
from robocoin_dataset.annotation.motion_annotation.lerobot_sim_replay import (
    MotionAnnotationConfig,
)
from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DmvAnnotationDB,
    LeFormatConvertDB,
    LeformatDatasetFkSimulationStatusDB,
    TaskStatus,
)


class MotionAnnotation:
    def __init__(
        self,
        db_file_path: str | Path,
        annotation_config_classes: dict[tuple[str, str], MotionAnnotationConfig],
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.annotation_config_classes = annotation_config_classes
        self.logger = logger or logging.getLogger(__name__)

    def _get_config(self, device_model: str, device_model_version: str) -> MotionAnnotationConfig:
        config_class = self.annotation_config_classes.get(
            (device_model, device_model_version), None
        )
        if not issubclass(config_class, MotionAnnotationConfig):
            raise RuntimeError(
                f"No motion annotation config found for device model {device_model} and device model version {device_model_version}"
            )
        return config_class()

    def _fk_simulation_dataset(self, dataset_uuid: str) -> None:
        with self.db.with_session() as session:
            item = (
                session.query(DmvAnnotationDB)
                .filter(DmvAnnotationDB.dataset_uuid == dataset_uuid)
                .first()
            )
            if item is None:
                raise RuntimeError(
                    f"No device model version annotation found for dataset {dataset_uuid}"
                )

        try:
            device_model = item.device_model
            device_model_version = item.device_model_version
            config = self._get_config(device_model, device_model_version).fk_solver_config

            convert_path = self._get_convert_path(dataset_uuid)

            fk_solver = LerobotFkSolver(config, convert_path)
            episode_num = fk_solver.get_episode_num()
            for episode_idx in tqdm(
                range(episode_num), desc="Simulating Episode FK", unit="episode"
            ):
                state_fk_sim_data = fk_solver.episode_fk(
                    episode_idx,
                )
                action_fk_sim_data = fk_solver.episode_fk(episode_idx, is_state=False)
                fk_solver._embed_episode_fk_sim_data(
                    episode_idx, state_fk_sim_data, action_fk_sim_data
                )
        except Exception as e:
            raise RuntimeError(f"Error when fk simulate dataset {dataset_uuid}: {e}")

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

    def _upsert_leformat_dataset_fk_simulation_status(
        self,
        session: Session,
        dataset_uuid: str,
        convert_path: str,
        status: TaskStatus,
        err_msg: str = "",
    ) -> None:
        item = (
            session.query(LeformatDatasetFkSimulationStatusDB)
            .filter(LeformatDatasetFkSimulationStatusDB.dataset_uuid == dataset_uuid)
            .first()
        )
        if item:
            item.convert_path = convert_path
            item.status = status
            err_msg = err_msg
        else:
            item = LeformatDatasetFkSimulationStatusDB(
                dataset_uuid=dataset_uuid,
                convert_path=convert_path,
                status=status,
                err_msg=err_msg,
            )
            session.add(item)
        session.commit()
        print(f"更新 fk 模拟任务状态为 {status}")

    def _sync_fk_sim_tasks(self, device_model: str | None = None) -> None:
        with self.db.with_session() as session:
            if device_model is not None:
                print(f"同步 {device_model} 设备型号的 fk 模拟任务...")
                items = (
                    session.query(LeFormatConvertDB)
                    .join(
                        DmvAnnotationDB,
                        LeFormatConvertDB.dataset_uuid == DmvAnnotationDB.dataset_uuid,
                    )
                    .filter(LeFormatConvertDB.convert_status == TaskStatus.COMPLETED)
                    .filter(
                        not_(
                            session.query(LeformatDatasetFkSimulationStatusDB)
                            .filter(
                                LeformatDatasetFkSimulationStatusDB.dataset_uuid
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
                            session.query(LeformatDatasetFkSimulationStatusDB)
                            .filter(
                                LeformatDatasetFkSimulationStatusDB.dataset_uuid
                                == LeFormatConvertDB.dataset_uuid
                            )
                            .exists()
                        )
                    )
                ).all()
        items = list(items)
        for item in items:
            with self.db.with_session() as session:
                self._upsert_leformat_dataset_fk_simulation_status(
                    session,
                    dataset_uuid=item.dataset_uuid,
                    convert_path=item.convert_path,
                    status=TaskStatus.PENDING,
                )

    def _gen_one_fk_sim_task(self) -> str | None:
        with self.db.with_session() as session:
            item = (
                session.query(LeformatDatasetFkSimulationStatusDB)
                .filter(LeformatDatasetFkSimulationStatusDB.status == TaskStatus.PENDING)
                .first()
            )
            if not item:
                return None
            item.status = TaskStatus.PROCESSING
            session.commit()
            return item.dataset_uuid

    def _get_fk_sim_task_num(self) -> int:
        with self.db.with_session() as session:
            return (
                session.query(LeformatDatasetFkSimulationStatusDB)
                .filter(LeformatDatasetFkSimulationStatusDB.status == TaskStatus.PENDING)
                .count()
            )

    def fk_simulate_datasets(self, model_device: str) -> None:
        self._sync_fk_sim_tasks(model_device)
        task_num = self._get_fk_sim_task_num()
        for _ in tqdm(range(task_num), desc="fk simulate datasets", unit="dataset"):
            dataset_uuid = self._gen_one_fk_sim_task()
            if dataset_uuid is None:
                break
            convert_path = self._get_convert_path(dataset_uuid)
            try:
                self._fk_simulation_dataset(dataset_uuid)
                with self.db.with_session() as session:
                    self._upsert_leformat_dataset_fk_simulation_status(
                        session=session,
                        dataset_uuid=dataset_uuid,
                        convert_path=convert_path,
                        status=TaskStatus.COMPLETED,
                    )

            except Exception as e:
                with self.db.with_session() as session:
                    self._upsert_leformat_dataset_fk_simulation_status(
                        session=session,
                        dataset_uuid=dataset_uuid,
                        convert_path=convert_path,
                        status=TaskStatus.FAILED,
                        err_msg=str(e),
                    )
