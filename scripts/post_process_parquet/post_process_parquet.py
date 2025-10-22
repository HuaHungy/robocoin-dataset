import argparse
import importlib
import logging
from pathlib import Path

import yaml

from robocoin_dataset.parquet_post_process.post_process_parquet import (
    PostProcessParquet,
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
        "--parquet_post_processing_factory_config_path",
        type=str,
        default="",
        help="Path to the factory config file",
    )

    parser.add_argument(
        "--device_model",
        type=str,
        default=None,
        help="Device model to post process parquet",
    )

    parser.add_argument(
        "--device_model_version",
        type=str,
        default=None,
        help="Device model version to post process parquet",
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
        Path(args.parquet_post_processing_factory_config_path).expanduser().absolute()
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
            class_module_path = config.get("parquet_post_processor_module", None)
            if class_module_path is None:
                continue
            class_name = config.get("parquet_post_processor_class", None)
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

    Processor = PostProcessParquet(
        db_file_path=db_file_path,
        processor_classes=processor_classes_dict,
        logger=logger,
    )

    Processor.post_process_parquet(device_model, device_model_version=device_model_version)


"""usage:
# agilex_cobot_decoupled_magic
python scripts/post_process_parquet/post_process_parquet.py \
    --db_file_path ./db/datasets.db \
    --parquet_post_processing_factory_config_path ./scripts/post_process_parquet/configs/parquet_post_processing_factory_config.yaml \
    --device_model agilex_cobot_decoupled_magic \
    --log_dir ./logs/sim_replay

# realman_rmc_aidal
python scripts/post_process_parquet/post_process_parquet.py \
    --db_file_path /mnt/db/datasets.db \
    --parquet_post_processing_factory_config_path ./scripts/post_process_parquet/configs/parquet_post_processing_factory_config.yaml \
    --device_model realman_rmc_aidal \
    --log_dir ./logs/parquet_post_processing

"""
