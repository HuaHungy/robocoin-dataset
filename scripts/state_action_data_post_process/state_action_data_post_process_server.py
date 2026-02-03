import argparse
import asyncio
import logging
from pathlib import Path

from robocoin_dataset.state_action_data_post_process.state_action_data_post_process import (
    StateActionDataPostProcessServer,
)
from robocoin_dataset.utils.logger import setup_logger


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db_file_path",
        type=str,
        default="",
        help="Path to the database file",
    )

    parser.add_argument(
        "--state_action_data_post_process_factory_config_path",
        type=str,
        default="",
        help="Path to the factory config file",
    )

    parser.add_argument(
        "--device_model",
        type=str,
        default=None,
        help="Device model to post process state and action data",
    )

    parser.add_argument(
        "--device_model_version",
        type=str,
        default=None,
        help="Device model version to post process state and action data",
    )

    # 新增：dataset_uuid 参数（和参考示例命名对齐，支持 target_dataset_uuid 别名）
    parser.add_argument(
        "--target_dataset_uuid",  # 增加别名，和参考示例保持一致
        type=str,
        default=None,
        help="Specific dataset UUID to post process (optional, if not specified, process all qualified datasets)",
    )

    parser.add_argument(
        "--log_dir",
        type=str,
        default="",
        help="Path to the log directory",
    )

    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to run the server",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8767,
        help="Port to run the server",
    )

    args = parser.parse_args()
    db_file_path = Path(args.db_file_path).expanduser().absolute()
    state_action_data_post_process_factory_config_path = (
        Path(args.state_action_data_post_process_factory_config_path).expanduser().absolute()
    )
    device_model = args.device_model
    device_model_version = args.device_model_version
    # 获取 UUID 参数（兼容别名）
    dataset_uuid = args.target_dataset_uuid

    # 校验数据库文件存在
    if not db_file_path.exists():
        print(f"{db_file_path} does not exist")
        exit(1)

    # 初始化日志
    logger = setup_logger(
        name="state action data post process server",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )

    # 核心修改：将 dataset_uuid 传递给 StateActionDataPostProcessServer 实例
    processor_server = StateActionDataPostProcessServer(
        db_file_path=db_file_path,
        state_action_dpp_classes_config_path=state_action_data_post_process_factory_config_path,
        host=args.host,
        port=args.port,
        heartbeat_interval=30.0,
        device_model=device_model,
        device_model_version=device_model_version,
        dataset_uuid=dataset_uuid,  # 传入 UUID
        timeout=15.0,
        logger=logger,
    )

    await processor_server.start()


if __name__ == "__main__":
    asyncio.run(main())
