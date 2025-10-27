import logging
import traceback
import uuid
from pathlib import Path

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

        def gripper_plot_callback(gripper_history, ax, lines) -> None:
            import numpy as np

            arr = np.array(gripper_history)
            if arr.ndim == 1:
                arr = arr[:, None]

            # 检查是否已经创建了窗口（使用全局状态避免重复创建）
            if not hasattr(gripper_plot_callback, "figs"):
                gripper_plot_callback.figs = []
                gripper_plot_callback.axes = []
                gripper_plot_callback.lines = []

                # 假设有两个gripper：gripper_left 和 gripper_right
                gripper_names = ["gripper_left", "gripper_right"]
                gripper_colors = ["green", "red"]  # gripper_left用绿色，gripper_right用红色

                # 检测每个gripper的子数据数量
                total_grippers = arr.shape[1]
                grippers_per_side = (
                    total_grippers // 2 if total_grippers % 2 == 0 else (total_grippers + 1) // 2
                )

                print(f"[Gripper可视化] 检测到总共 {total_grippers} 个gripper数据")
                print(f"[Gripper可视化] 每个gripper预计包含 {grippers_per_side} 个子数据")

                # 为每个gripper类型创建一个窗口
                for gripper_idx, gripper_name in enumerate(gripper_names):
                    if gripper_idx * grippers_per_side >= total_grippers:
                        break

                    fig, ax_sub = plt.subplots(figsize=(10, 6))
                    fig.suptitle(f"{gripper_name} Values")

                    # 在这个窗口中绘制该gripper的所有子数据，使用相同颜色
                    gripper_lines = []
                    start_idx = gripper_idx * grippers_per_side
                    end_idx = min(start_idx + grippers_per_side, total_grippers)

                    base_color = gripper_colors[gripper_idx]  # 使用gripper对应的基础颜色

                    for sub_idx in range(start_idx, end_idx):
                        local_sub_idx = sub_idx - start_idx
                        label = f"{gripper_name}_{local_sub_idx}"
                        (line,) = ax_sub.plot(arr[:, sub_idx], color=base_color, label=label)
                        gripper_lines.append(line)

                    ax_sub.set_xlabel("Step")
                    ax_sub.set_ylabel("Gripper Value")
                    ax_sub.legend()
                    ax_sub.grid(True, alpha=0.3)

                    gripper_plot_callback.figs.append(fig)
                    gripper_plot_callback.axes.append(ax_sub)
                    gripper_plot_callback.lines.extend(gripper_lines)

                    plt.show(block=False)

                    print(
                        f"[Gripper可视化] 已创建 {gripper_name} 窗口，包含 {len(gripper_lines)} 条曲线"
                    )

                # 将创建的lines返回给调用者
                lines.extend(gripper_plot_callback.lines)
            else:
                # 更新现有的线条数据
                for i, line in enumerate(gripper_plot_callback.lines):
                    if i < arr.shape[1]:
                        line.set_ydata(arr[:, i])
                        line.set_xdata(np.arange(arr.shape[0]))

                # 更新每个axes的显示范围
                for ax_sub in gripper_plot_callback.axes:
                    ax_sub.relim()
                    ax_sub.autoscale_view()

                # 重绘所有图表
                for fig in gripper_plot_callback.figs:
                    fig.canvas.draw_idle()

        try:
            # 启动界面
            simulator.start_viewer()
            print(f"[数据集回放] 开始回放数据集数据，数据集地址为: {convert_path}")
            print("[数据集回放] 正在准备 replay...，请在mujoco中调整好观察视角")
            input("[数据集回放] 请按回车键开始 state replay...")

            # State replay 循环
            while True:
                print("[State Replay] 开始播放状态数据...")
                simulator.replay_episode(
                    0,
                    is_state=True,
                    sleep_time_ms=30,
                    enable_gripper_plot=True,
                    gripper_plot_callback=gripper_plot_callback,
                )
                print("[State Replay] 状态数据播放完成")

                choice = (
                    input(
                        "[State Replay] 按c键确认结果正确，按r键重新播放，按e键输入错误信息 (r/e/c): "
                    )
                    .strip()
                    .lower()
                )

                if choice == "c":
                    print("[State Replay] 用户确认状态结果正确，继续action replay")
                    break
                if choice == "r":
                    print("[State Replay] 正在准备重新播放状态数据...")
                    continue
                if choice == "e":
                    error_message = input("[State Replay] 请输入state replay错误信息: ").strip()
                    print(f"[State Replay] 收到错误信息: {error_message}")
                    confirm = input(
                        "[State Replay] 确认错误请按回车键，修改错误信息请按其他键后回车: "
                    )
                    if confirm == "":
                        raise RuntimeError(f"state replay发生错误: {error_message}")
                else:
                    print("[State Replay] 无效输入，请输入 c、r 或 e")

            input("[Action Replay] 请按回车键开始 action replay...")

            # Action replay 循环
            while True:
                print("[Action Replay] 开始播放动作数据...")
                simulator.replay_episode(
                    0,
                    is_state=False,
                    sleep_time_ms=30,
                    enable_gripper_plot=True,
                    gripper_plot_callback=gripper_plot_callback,
                )
                print("[Action Replay] 动作数据播放完成")

                choice = (
                    input(
                        "[Action Replay] 按c键确认结果正确，按r键重新播放，按e键输入错误信息 (r/e/c): "
                    )
                    .strip()
                    .lower()
                )

                if choice == "c":
                    print("[Action Replay] 用户确认动作结果正确，回放完成")
                    break
                if choice == "r":
                    print("[Action Replay] 正在准备重新播放动作数据...")
                    continue
                if choice == "e":
                    error_message = input("[Action Replay] 请输入action replay错误信息: ").strip()
                    print(f"[Action Replay] 收到错误信息: {error_message}")
                    confirm = input(
                        "[Action Replay] 确认错误请按回车键，修改错误信息请按其他键后回车: "
                    )
                    if confirm == "":
                        raise RuntimeError(f"action replay发生错误: {error_message}")
                else:
                    print("[Action Replay] 无效输入，请输入 c、r 或 e")

            print("[数据集回放] 所有回放完成")

        finally:
            # 确保界面被关闭
            simulator.close_viewer()
            print("[数据集回放] 界面已关闭")

    @staticmethod
    def plot_gripper_values(gripper_values, title="Gripper Values"):
        """
        静态方法：绘制gripper值的图表，支持gripper_left和gripper_right各自包含1-5个子数据

        Args:
            gripper_values: gripper值的数组或列表
            title: 图表标题
        """
        import matplotlib.pyplot as plt
        import numpy as np

        arr = np.array(gripper_values)
        if arr.ndim == 1:
            arr = arr[:, None]

        # 假设有两个gripper：gripper_left 和 gripper_right
        gripper_names = ["gripper_left", "gripper_right"]
        gripper_colors = ["green", "red"]  # gripper_left用绿色，gripper_right用红色

        # 检测每个gripper的子数据数量
        total_grippers = arr.shape[1]
        grippers_per_side = (
            total_grippers // 2 if total_grippers % 2 == 0 else (total_grippers + 1) // 2
        )

        print(f"[静态Gripper可视化] 检测到总共 {total_grippers} 个gripper数据")
        print(f"[静态Gripper可视化] 每个gripper预计包含 {grippers_per_side} 个子数据")

        # 为每个gripper类型创建一个窗口
        for gripper_idx, gripper_name in enumerate(gripper_names):
            if gripper_idx * grippers_per_side >= total_grippers:
                break

            fig, ax = plt.subplots(figsize=(10, 6))
            fig.suptitle(f"{gripper_name} Values")

            # 在这个窗口中绘制该gripper的所有子数据，使用相同颜色
            start_idx = gripper_idx * grippers_per_side
            end_idx = min(start_idx + grippers_per_side, total_grippers)

            base_color = gripper_colors[gripper_idx]  # 使用gripper对应的基础颜色

            for sub_idx in range(start_idx, end_idx):
                local_sub_idx = sub_idx - start_idx
                label = f"{gripper_name}_{local_sub_idx}"
                ax.plot(arr[:, sub_idx], color=base_color, label=label)

            ax.set_xlabel("Step")
            ax.set_ylabel("Gripper Value")
            ax.legend()
            ax.grid(True, alpha=0.3)
            plt.show()

            print(
                f"[静态Gripper可视化] 已创建 {gripper_name} 窗口，包含 {end_idx - start_idx} 条曲线"
            )

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
        print(f"[数据库更新] 正在更新数据集 {dataset_uuid} 的状态为 {status.name}")
        item = (
            session.query(LeformatDatasetSimReplayStatusDB)
            .filter(LeformatDatasetSimReplayStatusDB.dataset_uuid == dataset_uuid)
            .first()
        )
        version_uuid = str(uuid.uuid4())
        if item:
            print("[数据库更新] 找到已存在记录，正在更新...")
            item.convert_path = convert_path
            item.status = status
            item.prestage_version_uuid = prestage_version_uuid
            item.device_model = device_model
            item.device_model_version = device_model_version
            item.version_uuid = version_uuid
            item.err_msg = err_msg
        else:
            print("[数据库更新] 未找到已存在记录，正在创建新记录...")
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

        print("[数据库更新] 正在提交事务...")
        session.commit()
        print(f"[数据库更新] 事务提交成功，状态已更新为 {status.name}")

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
                        session.query(LeformatDatasetSimReplayStatusDB)
                        .filter(
                            LeformatDatasetSimReplayStatusDB.dataset_uuid
                            == LeformatDateasetStateActionPostProcessingStatusDB.dataset_uuid
                        )
                        .filter(LeformatDatasetSimReplayStatusDB.status == TaskStatus.COMPLETED)
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
            print(f"[数据库状态] 开始回放数据集: {dataset_uuid}")
            self._sim_replay_dataset(dataset_uuid)
            print("[数据库状态] 回放完成，正在更新状态为COMPLETED...")
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
            print(f"[数据库状态] 成功更新数据集 {dataset_uuid} 状态为COMPLETED")

        except Exception:
            print("[数据库状态] 回放过程中发生异常，正在更新状态为FAILED...")
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
                    err_msg=traceback.format_exc(),
                )
            print(f"[数据库状态] 成功更新数据集 {dataset_uuid} 状态为FAILED")
            raise  # 重新抛出异常以便上层处理
