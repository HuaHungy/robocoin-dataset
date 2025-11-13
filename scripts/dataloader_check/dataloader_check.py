import argparse
import logging
from pathlib import Path

from robocoin_dataset.dataloader_check.dataloader_checker import DataLoaderChecker
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
        "--num_workers",
        type=int,
        default=8,
        help="",
    )

    parser.add_argument(
        "--sample_rate",
        type=float,
        default=0.1,
        help="",
    )
    args = parser.parse_args()

    logger = setup_logger(
        name="dataloader_check",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )
    args = parser.parse_args()

    checker = DataLoaderChecker(
        args.db_file_path, logger=logger, num_workers=args.num_workers, sample_rate=args.sample_rate
    )
    checker.check_one_repo()

"""Usage:
python scripts/dataloader_check/dataloader_check.py --db_file_path ./db/datasets_new.db --log_dir ./logs/dataloader_check
"""
