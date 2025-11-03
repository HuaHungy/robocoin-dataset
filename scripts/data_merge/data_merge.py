import argparse
import logging
from pathlib import Path

from robocoin_dataset.data_merge.data_merger import DataMerger
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

    args = parser.parse_args()

    logger = setup_logger(
        name="data_merge",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )
    args = parser.parse_args()

    data_merger = DataMerger(args.db_file_path, logger=logger)
    data_merger.merge_data_one_dataset()

"""Usage:
python scripts/data_merge/data_merge.py --db_file_path ./db/datasets_new.db --log_dir ./logs/data_merge
"""
