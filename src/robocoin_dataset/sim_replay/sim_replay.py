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
from robocoin_dataset.sim_replay.configs.lerobot_sim_replay_config import LerobotSimReplayConfig
from robocoin_dataset.sim_replay.lerobot_sim_replayer import LerobotSimReplayer


class SimReplay:
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

    def _sim_replay_dataset(self, dataset_uuid: str) -> None:
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
            replay_config = self._get_config(device_model, device_model_version)

            convert_path = self._get_convert_path(dataset_uuid)

            simulator = LerobotSimReplayer(replay_config, convert_path)
            simulator.start_viewer()
            print(f"开始回放数据集数据，数据集地址为: {convert_path}")
            print("正在准备 replay...，请在mujoco中调整好观察视角")
            input("请按回车键开始 state replay...")
            while True:
                simulator.replay_episode(0, is_state=True, sleep_time_ms=30)
                print(
                    "Relay已完成，按c键回车表示确认replay state结果正确，按r键回车后系统会再次replay state，按e键或其他键回车后可输入错误信息"
                )

                choice = input("请输入 (r/e/c): ").strip().lower()

                if choice == "c":
                    break

                if choice == "r":
                    print("正在准备重新 replay state...")
                    continue

                while True:
                    error_message = input("请输入state replay错误信息: ").strip()
                    print(f"收到state replay错误信息: {error_message}")
                    choice = input("确认请按回车键，修改state replay错误信息请按其他键后回车")
                    if choice == "":
                        simulator.close_viewer()
                        raise RuntimeError(f"state replay发生错误: {error_message}")
                    continue

            input("请按回车键开始 action replay...")
            while True:
                simulator.replay_episode(0, is_state=False, sleep_time_ms=30)
                print(
                    "Replay已完成，按c键回车表示确认replay action结果正确，按r键回车后系统会再次replay action，按e键回车后可输入错误信息"
                )

                choice = input("请输入 (r/e/c): ").strip().lower()

                if choice == "c":
                    break

                if choice == "r":
                    print("正在准备重新 replay actoin...")
                    continue

                while True:
                    if choice == "e":
                        error_message = input("请输入action replay错误信息: ").strip()
                        print(f"收到action replay错误信息: {error_message}")
                        choice = input("确认请按回车键，修改action replay错误信息请按其他键后回车")
                        if choice == "":
                            simulator.close_viewer()
                            raise RuntimeError(f"action replay发生错误: {error_message}")
                        continue
            simulator.close_viewer()

        except Exception as e:
            raise e

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
            print(e)
            with self.db.with_session() as session:
                self._upsert_leformat_dataset_simulation_replay_status(
                    session=session,
                    dataset_uuid=dataset_uuid,
                    convert_path=convert_path,
                    status=TaskStatus.FAILED,
                    err_msg=str(e),
                )
