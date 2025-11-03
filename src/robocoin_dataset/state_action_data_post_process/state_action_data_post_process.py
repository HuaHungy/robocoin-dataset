import importlib
import logging
import traceback
from pathlib import Path

import yaml
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import and_, or_

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
from robocoin_dataset.state_action_data_post_process.processors.state_action_data_processor_base import (
    StateActionDataPostProcessorBase,
)

PROCESSOR_MODULE_PATH = "processor_module_path"
PROCESSOR_CLASS_NAME = "processor_class_name"
PROCESSOR_LOG_DIR = "processor_log_dir"
PROCESSOR_LOG_NAME = "processor_log_name"
DEVICE_MODEL_VERSION = "device_model_version"


def _get_config_classes_dict(
    state_action_dpp_classes_config_file_path: str | Path,
) -> dict[tuple[str, str], tuple[str, str]]:
    if not state_action_dpp_classes_config_file_path.exists():
        raise FileNotFoundError(
            f"processor_class_config_path {state_action_dpp_classes_config_file_path} not exists"
        )
    with open(state_action_dpp_classes_config_file_path) as f:
        yaml_dict = yaml.safe_load(f)

    processor_config_dict = {}
    for device_model_name, configs in yaml_dict.items():
        for config in configs:
            device_version = config["version"]
            class_module_path = config.get("post_processor_module", None)
            if class_module_path is None:
                continue
            class_name = config.get("post_processor_class", None)
            if class_name is None:
                continue
            processor_config_dict[(device_model_name, device_version)] = (
                class_module_path,
                class_name,
            )

    return processor_config_dict


def _sync_state_action_data_post_processing_tasks(
    session: Session, device_model: str | None = None, device_model_version: str | None = None
) -> None:
    query = session.query(DatasetDB).filter(
        and_(
            # 必要前提：convert必须成功
            DatasetDB.convert_status == TaskStatus.COMPLETED,
            # 两个触发分支
            or_(
                # 分支1: 正在排队
                DatasetDB.sa_dpp_status == TaskStatus.PENDING,
                # 分支2: 已完成但版本过期
                and_(
                    DatasetDB.sa_dpp_status == TaskStatus.COMPLETED,
                    DatasetDB.sa_dpp_version_ps < DatasetDB.convert_version,
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
        item.sa_dpp_status = TaskStatus.PENDING
        item.sa_dpp_version = item.sa_dpp_version + 1
        item.sa_dpp_version_ps = item.convert_version

    session.commit()


def _gen_one_state_action_data_post_processing_task(
    session: Session, device_model: str = "", device_model_version: str = ""
) -> tuple[str | None, str | None, str | None, str | None]:
    query = session.query(DatasetDB).filter(
        DatasetDB.sa_dpp_status == TaskStatus.PENDING,
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
    item.sa_dpp_status = TaskStatus.PROCESSING
    item.sa_dpp_version_ps = item.convert_version
    item.sa_dpp_version = item.sa_dpp_version + 1
    session.commit()
    return item.dataset_uuid, item.convert_path, item.device_model, item.device_model_version


def _state_action_data_post_process(
    convert_path: str | Path,
    processor_class: type[StateActionDataPostProcessorBase],
) -> None:
    if processor_class is None:
        raise ValueError("processor_class is None")
    processor: StateActionDataPostProcessorBase = processor_class(convert_path=convert_path)
    processor.process()


class StateActionDataPostProcess:
    def __init__(
        self,
        db_file_path: str | Path,
        processor_class_config_path: str | Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)
        self.processor_classes_dict = _get_config_classes_dict(processor_class_config_path)

    def state_action_data_post_process_one_dataset(
        self, device_model: str = "", device_model_version: str = ""
    ) -> None:
        with self.db.with_session() as session:
            _sync_state_action_data_post_processing_tasks(
                session, device_model, device_model_version
            )
            dataset_uuid, convert_path, device_model, device_model_version = (
                _gen_one_state_action_data_post_processing_task(
                    session, device_model, device_model_version
                )
            )
            if dataset_uuid is None:
                self.logger.info("No dataset to process")
                return

        try:
            key = (device_model, device_model_version)
            processor_module_path, processor_class_name = self.processor_classes_dict[key]
            processor_class = importlib.import_module(processor_module_path).__getattribute__(
                processor_class_name
            )
            if processor_class is None:
                raise ValueError(
                    f"processor_class not found for {device_model} {device_model_version}"
                )
            _state_action_data_post_process(convert_path, processor_class)
            with self.db.with_session() as session:
                item = (
                    session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
                )
                item.sa_dpp_status = TaskStatus.COMPLETED
                session.commit()
        except Exception as e:
            with self.db.with_session() as session:
                item = (
                    session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
                )
                if item is None:
                    raise ValueError(f"Dataset {dataset_uuid} not found")
                item.sa_dpp_status = TaskStatus.FAILED
                item.sa_dpp_err_msg = str(traceback.format_exc())
                session.commit()
            self.logger.error(f"State Action Data post process dataset {convert_path} failed: {e}")


class StateActionDataPostProcessServer(TaskServer):
    def __init__(
        self,
        db_file_path: str | Path,
        state_action_dpp_classes_config_path: str | Path,
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
        state_action_dpp_classes_config_path = (
            Path(state_action_dpp_classes_config_path).expanduser().absolute()
        )
        if not state_action_dpp_classes_config_path.exists():
            raise FileNotFoundError(
                f"processor_classes_file_path {state_action_dpp_classes_config_path} not exists"
            )

        self.processor_classes_config_dict = _get_config_classes_dict(
            state_action_dpp_classes_config_path
        )

        self.logger.info(
            f"State Action Data Post Process Server started, "
            f"device_model={self.device_model}, "
            f"device_model_version={self.device_model_version}"
        )

    def get_task_category(self) -> str:
        return "state_action_data_post_process"

    def generate_task_content(self) -> dict | None:
        with self.db.with_session() as session:
            query = session.query(DatasetDB).filter(
                and_(
                    # 必要前提：convert必须成功
                    DatasetDB.convert_status == TaskStatus.COMPLETED,
                    # 两个触发分支
                    or_(
                        # 分支1: 正在排队
                        DatasetDB.sa_dpp_status == TaskStatus.PENDING,
                        # 分支2: 已完成但版本过期
                        and_(
                            DatasetDB.sa_dpp_status == TaskStatus.COMPLETED,
                            DatasetDB.sa_dpp_version_ps < DatasetDB.convert_version,
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

            item.sa_dpp_status = TaskStatus.PROCESSING
            item.sa_dpp_version = item.sa_dpp_version + 1
            item.sa_dpp_version_ps = item.convert_version

            session.commit()
            converter_module_path, converter_class_name = self.processor_classes_config_dict.get(
                (item.device_model, item.device_model_version),
                (None, None),
            )
            if converter_module_path is None or converter_class_name is None:
                raise ValueError(
                    f"No processor config found for device model {item.device_model} and version {item.device_model_version}"
                )

            return {
                DATASET_UUID: item.dataset_uuid,
                LEFORMAT_PATH: item.convert_path,
                DEVICE_MODEL: item.device_model,
                DEVICE_MODEL_VERSION: item.device_model_version,
                PROCESSOR_MODULE_PATH: converter_module_path,
                PROCESSOR_CLASS_NAME: converter_class_name,
            }

    def handle_task_result(self, task_content: dict, task_result_content: dict) -> None:
        ds_uuid = task_content.get(DATASET_UUID)

        task_status = task_result_content.get(TASK_RESULT_STATUS)
        task_status_msg = task_result_content.get(ERR_MSG)

        sa_dpp_status = TaskStatus.COMPLETED if task_status == TASK_SUCCESS else TaskStatus.FAILED

        # 🆕 合并为单个session，保证原子性
        with self.db.with_session() as session:
            # 查询 device_model_version
            item = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == ds_uuid).first()
            if item is None:
                self.logger.error(f"Dataset {ds_uuid} not found in dataset DB.")

            # 在同一个session中更新转换状态
            item.sa_dpp_status = sa_dpp_status
            item.sa_dpp_err_msg = task_status_msg
            session.commit()
            self.logger.info(
                f"Upsert {item.convert_path} state action data post process status to {sa_dpp_status}, "
                f"update_message: {task_status_msg}"
            )


class StateActionDataPostProcessClient(TaskClient):
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
        return "state_action_data_post_process"

    def generate_task_request_desc(self) -> dict:
        """客户端可自定义任务请求参数"""
        return {}

    def _sync_process_task(self, task_content: dict) -> dict:
        try:
            convert_path = task_content.get(LEFORMAT_PATH)
            processor_module_path = task_content.get(PROCESSOR_MODULE_PATH)
            processor_class_name = task_content.get(PROCESSOR_CLASS_NAME)

            processor_class = importlib.import_module(processor_module_path).__getattribute__(
                processor_class_name
            )

            _state_action_data_post_process(
                convert_path=convert_path, processor_class=processor_class
            )

            return {}
        except Exception as e:
            raise RuntimeError(
                f"state action data post process dataset {convert_path} failed"
            ) from e
