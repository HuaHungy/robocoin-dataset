import logging
import re
import traceback
import uuid
from pathlib import Path

import pandas as pd
import tqdm
from natsort import natsorted
from sqlalchemy import not_
from sqlalchemy.orm import Session

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    LeformatDatasetEefSimAnnotationStatusDB,
    LeformatDatasetSimReplayStatusDB,
    TaskStatus,
)
from robocoin_dataset.sim_replay.configs.lerobot_sim_replay_config import LerobotSimReplayConfig
from robocoin_dataset.sim_replay.lerobot_sim_replayer import LerobotSimReplayer


class EefSimAnnotation:
    def __init__(
        self,
        db_file_path: str | Path,
        replay_config_classes: dict[tuple[str, str], LerobotSimReplayConfig],
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.replay_config_classes = replay_config_classes
        self.logger = logger or logging.getLogger(__name__)

    def _get_config(self, device_model: str, device_model_version: str) -> LerobotSimReplayConfig:
        config_class = self.replay_config_classes.get((device_model, device_model_version), None)
        if not issubclass(config_class, LerobotSimReplayConfig):
            raise RuntimeError(
                f"No sim replay config found for device model {device_model} and device model version {device_model_version}"
            )
        return config_class()

    def _annotate_dataset(self, dataset_uuid: str) -> None:
        with self.db.with_session() as session:
            item = (
                session.query(LeformatDatasetSimReplayStatusDB)
                .filter(LeformatDatasetSimReplayStatusDB.dataset_uuid == dataset_uuid)
                .first()
            )
            if item is None:
                raise RuntimeError(
                    f"No device model version annotation found for dataset {dataset_uuid}"
                )

        device_model = item.device_model
        device_model_version = item.device_model_version
        replay_config = self._get_config(device_model, device_model_version)
        convert_path = Path(item.convert_path).expanduser().absolute()
        parquet_files: list[Path] = []

        regex = re.compile(r"episode_(?P<idx>\d{6})\.parquet$")
        for file_path in (convert_path / "ppp_data").rglob("episode_*.parquet"):
            match = regex.match(file_path.name)
            if match:
                parquet_files.append(file_path)

        parquet_files = natsorted(parquet_files, key=lambda x: x.name)
        simulator = LerobotSimReplayer(replay_config, convert_path)
        for parquet_file in tqdm.tqdm(
            parquet_files, desc="EEF Simulation Annotating Episode", unit="episode"
        ):
            df = pd.read_parquet(parquet_file)
            state_eef_sim_result, state_gripper_result = simulator._replay_episode_parquet(
                df, is_state=True
            )
            action_eef_sim_result, action_gripper_result = simulator._replay_episode_parquet(
                df, is_state=False
            )
            df["state_eef_sim_pose"] = state_eef_sim_result
            df["action_eef_sim_pose"] = action_eef_sim_result
            df["state_gripper_open"] = state_gripper_result
            df["action_gripper_open"] = action_gripper_result
            df.to_parquet(parquet_file)

    def _upsert_leformat_dataset_eef_sim_annotation_status(
        self,
        session: Session,
        dataset_uuid: str,
        convert_path: str,
        status: TaskStatus,
        prestage_version_uuid: str,
        device_model: str,
        device_model_version: str,
        err_msg: str = "",
    ) -> None:
        item = (
            session.query(LeformatDatasetEefSimAnnotationStatusDB).filter(
                LeformatDatasetEefSimAnnotationStatusDB.dataset_uuid == dataset_uuid
            )
        ).first()
        version_uuid = str(uuid.uuid4())
        if item:
            item.convert_path = convert_path
            item.status = status
            item.prestage_version_uuid = prestage_version_uuid
            item.device_model = device_model
            item.device_model_version = device_model_version
            item.err_msg = err_msg
            item.version_uuid = version_uuid
        else:
            item = LeformatDatasetEefSimAnnotationStatusDB(
                dataset_uuid=dataset_uuid,
                convert_path=convert_path,
                status=status,
                prestage_version_uuid=prestage_version_uuid,
                device_model=device_model,
                device_model_version=device_model_version,
                version_uuid=version_uuid,
                err_msg=err_msg,
            )
            session.add(item)
        session.commit()

    def _sync_eef_sim_annotation_tasks(
        self, device_model: str | None = None, device_model_version: str | None = None
    ) -> None:
        with self.db.with_session() as session:
            query = (
                session.query(LeformatDatasetSimReplayStatusDB)
                .filter(LeformatDatasetSimReplayStatusDB.status == TaskStatus.COMPLETED)
                .filter(
                    not_(
                        session.query(LeformatDatasetSimReplayStatusDB)
                        .filter(
                            LeformatDatasetSimReplayStatusDB.dataset_uuid
                            == LeformatDatasetEefSimAnnotationStatusDB.dataset_uuid
                        )
                        .filter(
                            LeformatDatasetEefSimAnnotationStatusDB.prestage_version_uuid
                            == LeformatDatasetSimReplayStatusDB.version_uuid
                        )
                        .exists()
                    )
                )
            )
            if device_model is not None:
                query = query.filter(LeformatDatasetSimReplayStatusDB.device_model == device_model)

            if device_model_version is not None:
                query = query.filter(
                    LeformatDatasetSimReplayStatusDB.device_model_version == device_model_version
                )

        items = query.all()
        for item in items:
            with self.db.with_session() as session:
                self._upsert_leformat_dataset_eef_sim_annotation_status(
                    session,
                    dataset_uuid=item.dataset_uuid,
                    convert_path=item.convert_path,
                    status=TaskStatus.PENDING,
                    prestage_version_uuid=item.version_uuid,
                    device_model=item.device_model,
                    device_model_version=item.device_model_version,
                )

    def _gen_one_eef_sim_annotation_task(
        self, device_model: str, device_model_version: str | None = None
    ) -> tuple[str, str, str, str, str]:
        with self.db.with_session() as session:
            query = session.query(LeformatDatasetEefSimAnnotationStatusDB).filter(
                LeformatDatasetEefSimAnnotationStatusDB.status == TaskStatus.PENDING,
            )
            if device_model:
                query = query.filter(
                    LeformatDatasetEefSimAnnotationStatusDB.device_model == device_model
                )
                if device_model_version:
                    query = query.filter(
                        LeformatDatasetEefSimAnnotationStatusDB.device_model_version
                        == device_model_version
                    )
            item = query.first()
            if not item:
                return None, None, None, None, None
            item.status = TaskStatus.PROCESSING
            session.commit()
            return (
                item.dataset_uuid,
                item.convert_path,
                item.prestage_version_uuid,
                item.device_model,
                item.device_model_version,
            )

    def annotate_eef_sim_datasets(
        self, device_model: str = "", device_model_version: str = ""
    ) -> None:
        self._sync_eef_sim_annotation_tasks(device_model)
        with self.db.with_session() as session:
            query = session.query(LeformatDatasetEefSimAnnotationStatusDB).filter(
                LeformatDatasetEefSimAnnotationStatusDB.status == TaskStatus.PENDING,
            )
            if device_model:
                query = query.filter(
                    LeformatDatasetEefSimAnnotationStatusDB.device_model == device_model
                )
                if device_model_version:
                    query = query.filter(
                        LeformatDatasetEefSimAnnotationStatusDB.device_model_version
                        == device_model_version
                    )
            task_num = query.count()

        for _ in tqdm.tqdm(
            range(task_num), desc="EEF Simulation Annotating Dataset", unit="dataset"
        ):
            (
                dataset_uuid,
                convert_path,
                prestage_version_uuid,
                device_model,
                device_model_version,
            ) = self._gen_one_eef_sim_annotation_task(
                device_model=device_model, device_model_version=device_model_version
            )
            if dataset_uuid is None:
                break

            try:
                self._annotate_dataset(dataset_uuid)
                with self.db.with_session() as session:
                    self._upsert_leformat_dataset_eef_sim_annotation_status(
                        session=session,
                        dataset_uuid=dataset_uuid,
                        convert_path=convert_path,
                        prestage_version_uuid=prestage_version_uuid,
                        device_model=device_model,
                        device_model_version=device_model_version,
                        status=TaskStatus.COMPLETED,
                    )

            except Exception:
                with self.db.with_session() as session:
                    self._upsert_leformat_dataset_eef_sim_annotation_status(
                        session=session,
                        dataset_uuid=dataset_uuid,
                        convert_path=convert_path,
                        status=TaskStatus.FAILED,
                        prestage_version_uuid=prestage_version_uuid,
                        device_model=device_model,
                        device_model_version=device_model_version,
                        err_msg=str(traceback.format_exc()),
                    )
