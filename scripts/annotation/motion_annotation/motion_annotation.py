import argparse
import logging
from pathlib import Path

from robocoin_dataset.annotation.motion_annotation.motion_annotation_data_post_process import (
    MotionAnnotationDataPostProcess,
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
        "--sim_replay_config_path",
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
        "--device_model_version",
        type=str,
        default="",
        help="Device model version to simulate",
    )

    parser.add_argument(
        "--log_dir",
        type=str,
        default="",
        help="Path to the log directory",
    )

    args = parser.parse_args()
    db_file_path = Path(args.db_file_path).expanduser().absolute()
    sim_replay_config_path = Path(args.sim_replay_config_path).expanduser().absolute()
    device_model = args.device_model
    device_model_version = args.device_model_version

    if not db_file_path.exists():
        print(f"{db_file_path} does not exist")
        exit(1)

    logger = setup_logger(
        name="motion_annotation",
        log_dir=Path(args.log_dir),
        level=logging.ERROR,
    )

    motion_annotation_processor = MotionAnnotationDataPostProcess(
        db_file_path=db_file_path,
        sim_replay_config_path=sim_replay_config_path,
        logger=logger,
    )

    motion_annotation_processor.motion_annotation_data_post_process_one_dataset(
        device_model=device_model, device_model_version=device_model_version
    )


"""usage:
# realman_rmc_aidal
python scripts/annotation/motion_annotation/motion_annotation.py \
    --db_file_path ./db/datasets_new.db \
    --sim_replay_config_path ./scripts/sim_replay/configs/sim_replay_config_path.yaml \
    --device_model realman_rmc_aidal \
    --device_model_version default_version \
    --log_dir ./logs/motion_annotation
"""
