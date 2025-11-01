import importlib
import logging
import traceback
from pathlib import Path

import yaml
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import and_, or_

from robocoin_dataset.annotation.motion_annotation.processors.motion_annotation_data_post_processor import (
    MotionAnnotationDataPostProcessor,
)
from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DatasetDB,
    TaskStatus,
)
from robocoin_dataset.distribution_computation.constant import (
    DATASET_UUID,
    DEVICE_MODEL,
    ERR_MSG,
    TASK_RESULT_STATUS,
    TASK_SUCCESS,
)
from robocoin_dataset.distribution_computation.task_client import TaskClient
from robocoin_dataset.distribution_computation.task_server import TaskServer
from robocoin_dataset.format_converter.tolerobot.constant import (
    LEFORMAT_PATH,
)
from robocoin_dataset.sim_replay.configs.lerobot_sim_replay_config import (
    LerobotSimReplayConfig,
)

DEVICE_MODEL_VERSION = "device_model_version"
SIM_REPLAY_CONFIG_MODULE_PATH = "sim_replay_config_module_path"
SIM_REPLAY_CONFIG_CLASS_NAME = "sim_replay_config_class_name"


def _get_sim_replay_config_classes_dict(
    sim_replay_config_file_path: str | Path,
) -> dict[tuple[str, str], tuple[str, str]]:
    """获取 sim_replay 配置字典"""
    if not sim_replay_config_file_path.exists():
        raise FileNotFoundError(f"sim_replay_config_path {sim_replay_config_file_path} not exists")
    with open(sim_replay_config_file_path) as f:
        yaml_dict = yaml.safe_load(f)

    replay_config_dict = {}
    for device_model_name, configs in yaml_dict.items():
        for config in configs:
            device_version = config["version"]
            class_module_path = config.get("mujoco_sim_replay_config_module", None)
            if class_module_path is None:
                continue
            class_name = config.get("mujoco_sim_replay_config_class", None)
            if class_name is None:
                continue
            replay_config_dict[(device_model_name, device_version)] = (
                class_module_path,
                class_name,
            )

    return replay_config_dict


def _sync_motion_annotation_data_post_processing_tasks(
    session: Session, device_model: str | None = None, device_model_version: str | None = None
) -> None:
    query = session.query(DatasetDB).filter(
        and_(
            # 必要前提：convert必须成功
            DatasetDB.sim_replay_status == TaskStatus.COMPLETED,
            # 两个触发分支
            or_(
                # 分支1: 正在排队
                DatasetDB.motion_annotation_status == TaskStatus.PENDING,
                # 分支2: 已完成但版本过期
                and_(
                    DatasetDB.motion_annotation_status == TaskStatus.COMPLETED,
                    DatasetDB.motion_annotation_version_ps < DatasetDB.sim_replay_version,
                ),
            ),
        )
    )
    if device_model:
        query = query.filter(
            DatasetDB.device_model == device_model,
        )

        if device_model_version:
            query = query.filter(DatasetDB.device_model_version == device_model_version)

    items = query.all()

    if not items:
        return
    for item in items:
        item.motion_annotation_status = TaskStatus.PENDING
        item.motion_annotation_version = item.motion_annotation_version + 1
        item.motion_annotation_version_ps = item.sim_replay_version

    session.commit()


def _gen_one_motion_annotation_data_post_processing_task(
    session: Session, device_model: str = "", device_model_version: str = ""
) -> tuple[str | None, str | None, str | None, str | None]:
    query = session.query(DatasetDB).filter(
        DatasetDB.sim_replay_status == TaskStatus.COMPLETED,
        DatasetDB.motion_annotation_status == TaskStatus.PENDING,
    )
    if device_model:
        query = query.filter(
            DatasetDB.device_model == device_model,
        )

        if device_model_version:
            query = query.filter(DatasetDB.device_model_version == device_model_version)

    item = query.first()
    if not item:
        return None, None, None, None
    item.motion_annotation_status = TaskStatus.PROCESSING
    item.motion_annotation_version_ps = item.sim_replay_version
    item.motion_annotation_version = item.motion_annotation_version + 1
    session.commit()
    return item.dataset_uuid, item.convert_path, item.device_model, item.device_model_version


def _motion_annotation_data_post_process(
    repo_path: str | Path,
    sim_replay_config: LerobotSimReplayConfig,
) -> None:
    processor: MotionAnnotationDataPostProcessor = MotionAnnotationDataPostProcessor(
        convert_path=repo_path, sim_replay_config=sim_replay_config
    )
    processor.process()


class MotionAnnotationDataPostProcess:
    def __init__(
        self,
        db_file_path: str | Path,
        sim_replay_config_path: str | Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)
        self.sim_replay_config_dict = _get_sim_replay_config_classes_dict(sim_replay_config_path)

    def motion_annotation_data_post_process_one_dataset(
        self, device_model: str = "", device_model_version: str = ""
    ) -> None:
        with self.db.with_session() as session:
            _sync_motion_annotation_data_post_processing_tasks(
                session, device_model, device_model_version
            )
            dataset_uuid, convert_path, device_model, device_model_version = (
                _gen_one_motion_annotation_data_post_processing_task(
                    session, device_model, device_model_version
                )
            )
            if dataset_uuid is None:
                self.logger.info("No dataset to process")
                return

        try:
            key = (device_model, device_model_version)

            # 获取 sim_replay 配置
            sim_replay_module_path, sim_replay_class_name = self.sim_replay_config_dict.get(
                key, (None, None)
            )
            if sim_replay_module_path is None or sim_replay_class_name is None:
                raise ValueError(
                    f"sim_replay_config not found for {device_model} {device_model_version}"
                )

            sim_replay_config_class = importlib.import_module(
                sim_replay_module_path
            ).__getattribute__(sim_replay_class_name)
            sim_replay_config = sim_replay_config_class()

            _motion_annotation_data_post_process(convert_path, sim_replay_config)
            with self.db.with_session() as session:
                item = (
                    session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
                )
                item.motion_annotation_status = TaskStatus.COMPLETED
                session.commit()
        except Exception:
            with self.db.with_session() as session:
                item = (
                    session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
                )
                if item is None:
                    raise ValueError(f"Dataset {dataset_uuid} not found")
                item.motion_annotation_status = TaskStatus.FAILED
                item.motion_annotation_err_msg = str(traceback.format_exc())
                session.commit()
            self.logger.error(
                f"State Action Data post process dataset {convert_path} failed: {traceback.format_exc()}"
            )


class MotionAnnotationDataPostProcessServer(TaskServer):
    def __init__(
        self,
        db_file_path: str | Path,
        sim_replay_config_path: str | Path,
        host: str = "0.0.0.0",
        port: int = 8765,
        heartbeat_interval: float = 30.0,  # 服务端每30秒发一次 ping
        device_model: str = "",
        device_model_version: str = "",
        timeout: float = 15.0,  # 等待 pong 超过15秒则断开
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(
            logger=logger,
            host=host,
            port=port,
            heartbeat_interval=heartbeat_interval,
            timeout=timeout,
        )
        db_file_path = Path(db_file_path).expanduser().absolute()
        self.device_model = device_model
        self.device_model_version = device_model_version

        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)

        sim_replay_config_path = Path(sim_replay_config_path).expanduser().absolute()
        if not sim_replay_config_path.exists():
            raise FileNotFoundError(f"sim_replay_config_path {sim_replay_config_path} not exists")

        self.sim_replay_config_dict = _get_sim_replay_config_classes_dict(sim_replay_config_path)

        self.logger.info(
            f"EEF Sim Data Post Process Server started, "
            f"device_model={self.device_model}, "
            f"device_model_version={self.device_model_version}"
        )

    def get_task_category(self) -> str:
        return "motion_annotaton_data_post_process"

    def generate_task_content(self) -> dict | None:
        with self.db.with_session() as session:
            query = session.query(DatasetDB).filter(
                and_(
                    # 必要前提：convert必须成功
                    DatasetDB.sim_replay_status == TaskStatus.COMPLETED,
                    # 两个触发分支
                    or_(
                        # 分支1: 正在排队
                        DatasetDB.motion_annotation_status == TaskStatus.PENDING,
                        # 分支2: 已完成但版本过期
                        and_(
                            DatasetDB.motion_annotation_status == TaskStatus.COMPLETED,
                            DatasetDB.motion_annotation_version_ps < DatasetDB.sim_replay_version,
                        ),
                    ),
                )
            )
            if self.device_model is not None:
                query = query.filter(
                    DatasetDB.device_model == self.device_model,
                )

            if self.device_model_version is not None:
                query = query.filter(DatasetDB.device_model_version == self.device_model_version)

            item = query.first()

            if not item:
                return None

            item.motion_annotation_status = TaskStatus.PROCESSING
            item.motion_annotation_version = item.motion_annotation_version + 1
            item.motion_annotation_version_ps = item.sim_replay_version

            session.commit()

            # 获取 sim_replay 配置
            sim_replay_module_path, sim_replay_class_name = self.sim_replay_config_dict.get(
                (item.device_model, item.device_model_version),
                (None, None),
            )
            if sim_replay_module_path is None or sim_replay_class_name is None:
                raise ValueError(
                    f"No sim_replay config found for device model {item.device_model} and version {item.device_model_version}"
                )

            return {
                DATASET_UUID: item.dataset_uuid,
                LEFORMAT_PATH: item.convert_path,
                DEVICE_MODEL: item.device_model,
                DEVICE_MODEL_VERSION: item.device_model_version,
                SIM_REPLAY_CONFIG_MODULE_PATH: sim_replay_module_path,
                SIM_REPLAY_CONFIG_CLASS_NAME: sim_replay_class_name,
            }

    def handle_task_result(self, task_content: dict, task_result_content: dict) -> None:
        ds_uuid = task_content.get(DATASET_UUID)

        task_status = task_result_content.get(TASK_RESULT_STATUS)
        task_status_msg = task_result_content.get(ERR_MSG)

        motion_annotation_status = (
            TaskStatus.COMPLETED if task_status == TASK_SUCCESS else TaskStatus.FAILED
        )

        # 🆕 合并为单个session，保证原子性
        with self.db.with_session() as session:
            # 查询 device_model_version
            item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == ds_uuid).first()
            if item is None:
                self.logger.error(f"Dataset {ds_uuid} not found in dataset DB.")

            # 在同一个session中更新转换状态
            item.motion_annotation_status = motion_annotation_status
            item.motion_annotation_err_msg = task_status_msg
            session.commit()
            self.logger.info(
                f"Upsert {item.convert_path} motion annotation data post process status to {motion_annotation_status}, "
                f"update_message: {task_status_msg}"
            )


class MotionAnnotationDataPostProcessClient(TaskClient):
    def __init__(
        self,
        server_uri: str = "ws://localhost:8767",
        heartbeat_interval: float = 10.0,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(
            server_uri=server_uri,
            heartbeat_interval=heartbeat_interval,
            logger=logger,
        )

    def get_task_category(self) -> str:
        return "motion_annotation_data_post_process"

    def generate_task_request_desc(self) -> dict:
        """客户端可自定义任务请求参数"""
        return {}

    def _sync_process_task(self, task_content: dict) -> dict:
        try:
            repo_path = task_content.get(LEFORMAT_PATH)
            sim_replay_module_path = task_content.get(SIM_REPLAY_CONFIG_MODULE_PATH)
            sim_replay_class_name = task_content.get(SIM_REPLAY_CONFIG_CLASS_NAME)

            sim_replay_config_class = importlib.import_module(
                sim_replay_module_path
            ).__getattribute__(sim_replay_class_name)
            sim_replay_config = sim_replay_config_class()

            _motion_annotation_data_post_process(
                repo_path=repo_path, sim_replay_config=sim_replay_config
            )

            return {}
        except Exception as e:
            raise RuntimeError(f"motion annotation post process dataset {repo_path} failed") from e
