import argparse
import logging
from pathlib import Path

from robocoin_dataset.quality_check.qced_repo_generator import QualityCheckedRepoGenerator
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
    parser.add_argument("--state_data_score_threshold", type=float, default=0.85)
    parser.add_argument("--action_data_score_threshold", type=float, default=0.85)
    parser.add_argument("--video_score_threshold", type=float, default=0.9)
    parser.add_argument("--min_episodes_num", type=int, default=10)

    args = parser.parse_args()

    logger = setup_logger(
        name="quality check",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )

    generator = QualityCheckedRepoGenerator(
        args.db_file_path,
        state_data_score_threshold=args.state_data_score_threshold,
        action_data_score_threshold=args.action_data_score_threshold,
        video_score_threshold=args.video_score_threshold,
        min_episodes_num=args.min_episodes_num,
        logger=logger,
    )
    generator.gen_one_qced_repo()

"""Usage:
python scripts/quality_check/qced_repo_gen.py --db_file_path ./db/datasets_new.db --log_dir ./logs/qced_repo_gen
"""
