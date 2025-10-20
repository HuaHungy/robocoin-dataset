import argparse
import importlib
import logging
from pathlib import Path

import yaml

from robocoin_dataset.annotation.motion_annotation.motion_annotation import MotionAnnotation
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
        "--converter_factory_config_path",
        type=str,
        default="",
        help="Path to the annotation config classes",
    )

    parser.add_argument(
        "--device_model",
        type=str,
        default="",
        help="Device model to simulate",
    )

    parser.add_argument(
        "--log_dir",
        type=str,
        default="",
        help="Path to the log directory",
    )

    args = parser.parse_args()
    db_file_path = Path(args.db_file_path).expanduser().absolute()
    converter_factory_config_path = Path(args.converter_factory_config_path).expanduser().absolute()
    device_model = args.device_model
    print(device_model)

    if not db_file_path.exists():
        print(f"{db_file_path} does not exist")
        exit(1)

    if not converter_factory_config_path.exists():
        print(f"{converter_factory_config_path} does not exist")
        exit(1)

    converter_factory_config: dict[str, list[dict]] = {}

    with converter_factory_config_path.open() as f:
        converter_factory_config = yaml.safe_load(f)

    config_classes_dict = {}
    for device_model_name, configs in converter_factory_config.items():
        for config in configs:
            device_version = config["version"]
            class_module_path = config.get("mujoco_sim_config_module", None)
            if class_module_path is None:
                continue
            class_name = config.get("mujoco_sim_config_class", None)
            if class_name is None:
                continue
            config_class = importlib.import_module(class_module_path).__getattribute__(class_name)
            config_classes_dict[(device_model_name, device_version)] = config_class

    logger = setup_logger(
        name="video_subtask_annotation",
        log_dir=Path(args.log_dir),
        level=logging.ERROR,
    )
    motion_annotation = MotionAnnotation(
        db_file_path=db_file_path,
        annotation_config_classes=config_classes_dict,
        logger=logger,
    )

    motion_annotation.fk_simulate_datasets(device_model)


"""usage:
python scripts/motion_annotation/motion_annotation.py \
    --db_file_path ./db/datasets.db \
    --converter_factory_config_path ./scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --device_model realman_rmc_aidal\
    --log_dir ./logs/motion_annotation
"""
