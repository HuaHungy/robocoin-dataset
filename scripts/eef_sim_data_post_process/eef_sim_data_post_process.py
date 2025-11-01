import argparse
import logging
from pathlib import Path

from robocoin_dataset.eef_sim_data_post_process.eef_sim_data_post_process import (
    EefSimDataProcess,
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
        "--sim_replay_factory_config_path",
        type=str,
        default="",
        help="Path to the sim replay factory config file",
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
    sim_replay_factory_config_path = (
        Path(args.sim_replay_factory_config_path).expanduser().absolute()
    )
    device_model = args.device_model
    device_model_version = args.device_model_version

    if not db_file_path.exists():
        print(f"{db_file_path} does not exist")
        exit(1)

    logger = setup_logger(
        name="eef_sim",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )

    processor = EefSimDataProcess(
        db_file_path=db_file_path,
        sim_replay_config_path=sim_replay_factory_config_path,
        logger=logger,
    )

    processor.eef_sim_data_post_process_one_dataset(
        device_model, device_model_version=device_model_version
    )


"""usage:
# realman_rmc_aidal
python scripts/eef_sim_data_post_process/eef_sim_data_post_process.py \
    --db_file_path ./db/datasets_new.db \
    --sim_replay_factory_config_path ./scripts/sim_replay/configs/sim_replay_config_path.yaml \
    --device_model realman_rmc_aidal \
    --device_model_version default_version \
    --log_dir ./logs/eef_sim_data_post_process
"""
