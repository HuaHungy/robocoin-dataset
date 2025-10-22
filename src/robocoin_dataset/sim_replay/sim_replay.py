import logging
import uuid
from pathlib import Path
import traceback

# For gripper value visualization
import matplotlib.pyplot as plt

from sqlalchemy import not_
from sqlalchemy.orm import Session

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DmvAnnotationDB,
    LeFormatConvertDB,
    LeformatDatasetSimReplayStatusDB,
    LeformatDateasetStateActionPostProcessingStatusDB,
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


        device_model = item.device_model
        device_model_version = item.device_model_version
        replay_config = self._get_config(device_model, device_model_version)

        convert_path = self._get_convert_path(dataset_uuid)

        simulator = LerobotSimReplayer(replay_config, convert_path)
        simulator.start_viewer()
        print(f"开始回放数据集数据，数据集地址为: {convert_path}")
        print("正在准备 replay...，请在mujoco中调整好观察视角")
        input("请按回车键开始 state replay...")
        # --- Gripper value collection for visualization ---
        gripper_values_state = []

        def gripper_plot_callback(gripper_history, ax, lines):
            import numpy as np
            arr = np.array(gripper_history)
            if arr.ndim == 1:
                arr = arr[:, None]
            if not lines:
                for i in range(arr.shape[1]):
                    (line,) = ax.plot(arr[:, i], label=f"gripper_{i}")
                    lines.append(line)
                ax.legend()
            else:
                for i, line in enumerate(lines):
                    line.set_ydata(arr[:, i])
                    line.set_xdata(np.arange(arr.shape[0]))
                ax.relim()
                ax.autoscale_view()

        while True:
            simulator.replay_episode(0, is_state=True, sleep_time_ms=30, enable_gripper_plot=True, gripper_plot_callback=gripper_plot_callback)
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
                simulator.replay_episode(10, is_state=True, sleep_time_ms=30)
                print(
                    "Relay已完成，按c键回车表示确认replay state结果正确，按r键回车后系统会再次replay state，按e键或其他键回车后可输入错误信息"
                )
                error_message = input("请输入state replay错误信息: ").strip()
                print(f"收到state replay错误信息: {error_message}")
                choice = input("确认请按回车键，修改state replay错误信息请按其他键后回车")
                if choice == "":
                    simulator.close_viewer()
                    raise RuntimeError(f"state replay发生错误: {error_message}")
                continue

        # --- Plot gripper values for state ---

        input("请按回车键开始 action replay...")
        gripper_values_action = []

        while True:
            simulator.replay_episode(0, is_state=False, sleep_time_ms=30, enable_gripper_plot=True, gripper_plot_callback=gripper_plot_callback)
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

        input("请按回车键开始 action replay...")
        while True:
                simulator.replay_episode(10, is_state=False, sleep_time_ms=30)
                print(
                    "Replay已完成，按c键回车表示确认replay action结果正确，按r键回车后系统会再次replay action，按e键回车后可输入错误信息"
                )


    @staticmethod
    def plot_gripper_values(gripper_values, title="Gripper Values"):
        if not gripper_values or not any(gripper_values):
            print("[可视化] 没有可用的 gripper 数据，不进行绘图。")
            return
        import numpy as np
        gripper_values = np.array(gripper_values)
        if gripper_values.ndim == 1:
            gripper_values = gripper_values[:, None]
        plt.figure(figsize=(10, 4))
        for i in range(gripper_values.shape[1]):
            plt.plot(gripper_values[:, i], label=f"gripper_{i}")
        plt.xlabel("Step")
        plt.ylabel("Gripper Value")
        plt.title(title)
        plt.legend()
        plt.tight_layout()
        plt.show()


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
        prestage_version_uuid: str,
        device_model: str,
        device_model_version: str,
        err_msg: str = "",
    ) -> None:
        item = (
            session.query(LeformatDatasetSimReplayStatusDB)
            .filter(LeformatDatasetSimReplayStatusDB.dataset_uuid == dataset_uuid)
            .first()
        )
        version_uuid = str(uuid.uuid4())
        if item:
            item.convert_path = convert_path
            item.status = status
            item.prestage_version_uuid = prestage_version_uuid
            item.device_model = device_model
            item.device_model_version = device_model_version
            item.version_uuid = version_uuid
            item.err_msg = err_msg
        else:
            item = LeformatDatasetSimReplayStatusDB(
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

    def _sync_sim_replay_tasks(
        self, device_model: str | None = None, device_model_version: str | None = None
    ) -> None:
        with self.db.with_session() as session:
            query = (
                session.query(LeformatDateasetStateActionPostProcessingStatusDB)
                .filter(
                    LeformatDateasetStateActionPostProcessingStatusDB.status == TaskStatus.COMPLETED
                )
                .filter(
                    not_(
                        session.query(LeformatDateasetStateActionPostProcessingStatusDB)
                        .filter(
                            LeformatDateasetStateActionPostProcessingStatusDB.dataset_uuid
                            == LeformatDatasetSimReplayStatusDB.dataset_uuid
                        )
                        .filter(
                            LeformatDateasetStateActionPostProcessingStatusDB.prestage_version_uuid
                            == LeformatDateasetStateActionPostProcessingStatusDB.version_uuid
                        )
                        .exists()
                    )
                )
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

        items = query.all()
        for item in items:
            with self.db.with_session() as session:
                self._upsert_leformat_dataset_simulation_replay_status(
                    session,
                    dataset_uuid=item.dataset_uuid,
                    convert_path=item.convert_path,
                    status=TaskStatus.PENDING,
                    prestage_version_uuid=item.version_uuid,
                    device_model=item.device_model,
                    device_model_version=item.device_model_version,
                )

    def _gen_one_sim_replay_task(
        self, device_model: str, device_model_version: str | None = None
    ) -> tuple[str, str, str, str]:
        with self.db.with_session() as session:
            query = session.query(LeformatDatasetSimReplayStatusDB).filter(
                LeformatDatasetSimReplayStatusDB.status == TaskStatus.PENDING,
            )
            if device_model:
                query = query.filter(LeformatDatasetSimReplayStatusDB.device_model == device_model)
                if device_model_version:
                    query = query.filter(
                        LeformatDatasetSimReplayStatusDB.device_model_version
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

    def sim_replay_datasets(self, device_model: str, device_model_version: str = "") -> None:
        self._sync_sim_replay_tasks(device_model)
        dataset_uuid, prestage_version_uuid, device_model, device_model_version = (
            self._gen_one_sim_replay_task(
                device_model=device_model, device_model_version=device_model_version
            )
        )

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
                    prestage_version_uuid=prestage_version_uuid,
                    device_model=device_model,
                    device_model_version=device_model_version,
                    status=TaskStatus.COMPLETED,
                )

        except Exception as e:
            self.logger.error(traceback.format_exc())
            with self.db.with_session() as session:
                self._upsert_leformat_dataset_simulation_replay_status(
                    session=session,
                    dataset_uuid=dataset_uuid,
                    convert_path=convert_path,
                    status=TaskStatus.FAILED,
                    prestage_version_uuid=prestage_version_uuid,
                    device_model=device_model,
                    device_model_version=device_model_version,
                    err_msg=str(e),
                    err_msg=traceback.format_exc(),
                )
