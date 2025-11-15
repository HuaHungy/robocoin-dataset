import argparse
import logging
from pathlib import Path

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
    state_action_data_post_process_factory_config_path = (
        Path(args.state_action_data_post_process_factory_config_path).expanduser().absolute()
    )
    device_model = args.device_model
    device_model_version = args.device_model_version

    if not db_file_path.exists():
        print(f"{db_file_path} does not exist")
        exit(1)

    logger = setup_logger(
        name="sim_replay",
        log_dir=Path(args.log_dir),
        level=logging.ERROR,
    )

    processor = StateActionDataPostProcess(
        db_file_path=db_file_path,
        processor_class_config_path=state_action_data_post_process_factory_config_path,
        logger=logger,
    )

    processor.state_action_data_post_process_one_dataset(
        device_model, device_model_version=device_model_version
    )


"""usage:
# realman_rmc_aidal
python scripts/state_action_data_post_process/state_action_data_post_process.py \
    --db_file_path /mnt/db/datasets_new.db \
    --state_action_data_post_process_factory_config_path ./scripts/state_action_data_post_process/configs/state_action_data_post_process_factory_config.yaml \
    --device_model realman_rmc_aidal \
    --device_model_version default_version \
    --log_dir ./logs/stat_action_data_post_process


python scripts/state_action_data_post_process/state_action_data_post_process.py \
    --db_file_path ./db/datasets_new.db \
    --state_action_data_post_process_factory_config_path ./scripts/state_action_data_post_process/configs/state_action_data_post_process_factory_config.yaml \
    --device_model ruantong_a2d \
    --device_model_version default_version \
    --log_dir ./logs/state_action_data_post_process
"""




"""usage:
# agilex_cobot_decoupled_magic
python scripts/state_action_data_post_process/state_action_data_post_process.py \
    --db_file_path /mnt/db/datasets_new.db \
    --state_action_data_post_process_factory_config_path ./scripts/state_action_data_post_process/configs/state_action_data_post_process_factory_config.yaml \
    --device_model yinhe \
    --device_model_version lite_version \
    --log_dir ./logs/stat_action_data_post_process
"""