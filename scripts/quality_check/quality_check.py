import argparse
import logging
from pathlib import Path

from robocoin_dataset.quality_check.dataset_quality_check import DatasetQualityCheck
from robocoin_dataset.utils.logger import setup_logger

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db_file_path", type=str, required=True)

    parser.add_argument(
        "--log_dir",
        type=str,
        default="",
        help="Path to the log directory",
    )

    parser.add_argument(
        "--qc_config_path",
        type=str,
        default="",
        help="Path to the quality check config file",
    )

    args = parser.parse_args()

    logger = setup_logger(
        name="quality check",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )
    args = parser.parse_args()

    checker = DatasetQualityCheck(
        args.db_file_path, qc_config_path=args.qc_config_path, logger=logger
    )
    checker.check_one_repo()

"""Usage:
python scripts/quality_check/quality_check.py --db_file_path ./db/datasets_new.db --log_dir ./logs/quality_check --qc_config_path ./scripts/quality_check/configs/device_version_checker_config.yaml
"""
