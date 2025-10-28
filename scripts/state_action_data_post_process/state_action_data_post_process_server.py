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

    parser.add_argument(
        "--log_dir",
        type=str,
        default="",
        help="Path to the log directory",
    )

    args = parser.parse_args()
    db_file_path = Path(args.db_file_path).expanduser().absolute()
    state_action_data_post_process_factory_config_path = (
        Path(args.state_action_data_post_process_factory_config_path).expanduser().absolute()
    )
    device_model = args.device_model
    device_model_version = args.device_model_version

    if not db_file_path.exists():
        print(f"{db_file_path} does not exist")
        exit(1)

    logger = setup_logger(
        name="state action data post process server",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )

    processor_server = StateActionDataPostProcessServer(
        db_file_path=db_file_path,
        state_action_dpp_classes_config_path=state_action_data_post_process_factory_config_path,
        host="0.0.0.0",
        port=8767,
        heartbeat_interval=30.0,
        device_model=device_model,
        device_model_version=device_model_version,
        timeout=15.0,
        logger=logger,
    )

    await processor_server.start()


if __name__ == "__main__":
    asyncio.run(main())

"""usage:
# realman_rmc_aidal
python scripts/state_action_data_post_process/state_action_data_post_process_server.py \
    --db_file_path ./db/datasets_new.db \
    --state_action_data_post_process_factory_config_path ./scripts/state_action_data_post_process/configs/state_action_data_post_process_factory_config.yaml \
    --device_model realman_rmc_aidal \
    --device_model_version default_version \
    --log_dir ./logs/stat_action_data_post_process
"""
