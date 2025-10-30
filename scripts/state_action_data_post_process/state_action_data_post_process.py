import argparse
import importlib
import logging
from pathlib import Path

import yaml

from robocoin_dataset.state_action_data_post_process.state_action_data_post_process import (
    StateActionDataPostProcess,
)
from robocoin_dataset.utils.logger import setup_logger

if __name__ == "__main__":
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
    parquet_post_process_factory_config_path = (
        Path(args.state_action_data_post_process_factory_config_path).expanduser().absolute()
    )
    device_model = args.device_model
    device_model_version = args.device_model_version

    if not db_file_path.exists():
        print(f"{db_file_path} does not exist")
        exit(1)

    if not parquet_post_process_factory_config_path.exists():
        print(f"{parquet_post_process_factory_config_path} does not exist")
        exit(1)

    processor_classes_config: dict[str, list[dict]] = {}

    with parquet_post_process_factory_config_path.open() as f:
        processor_classes_config = yaml.safe_load(f)

    processor_classes_dict = {}
    for device_model_name, configs in processor_classes_config.items():
        for config in configs:
            device_version = config["version"]
            class_module_path = config.get("post_processor_module", None)
            if class_module_path is None:
                continue
            class_name = config.get("post_processor_class", None)
            if class_name is None:
                continue
            processor_class = importlib.import_module(class_module_path).__getattribute__(
                class_name
            )
            processor_classes_dict[(device_model_name, device_version)] = processor_class

    logger = setup_logger(
        name="sim_replay",
        log_dir=Path(args.log_dir),
        level=logging.ERROR,
    )

    Processor = StateActionDataPostProcess(
        db_file_path=db_file_path,
        processor_classes=processor_classes_dict,
        logger=logger,
    )

    Processor.post_process_parquet(device_model, device_model_version=device_model_version)


"""usage:
# realman_rmc_aidal
python scripts/state_action_data_post_process/state_action_data_post_process.py \
    --db_file_path /mnt/db/datasets.db \
    --state_action_data_post_process_factory_config_path ./scripts/state_action_data_post_process/configs/state_action_data_post_process_factory_config.yaml \
    --device_model ruantong_a2d \
    --device_model_version default_version \
    --log_dir ./logs/state_action_data_post_process
"""
