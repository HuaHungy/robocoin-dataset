import argparse
import logging
from pathlib import Path

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB
from robocoin_dataset.quality_check.qced_repo_generator import (
    _get_bad_episodes,
    gen_qced_repo,
)
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

    parser.add_argument(
        "--repo_path",
        type=str,
        required=True,
        help="Path to the repo",
    )
    parser.add_argument("--state_data_score_threshold", type=float, default=0.85)
    parser.add_argument("--action_data_score_threshold", type=float, default=0.85)
    parser.add_argument("--video_score_threshold", type=float, default=0.9)
    parser.add_argument("--min_episodes_num_threshold", type=int, default=10)
    parser.add_argument("--ds_api_key", type=str, default="sk-a3c8736391cf43809957329f28cac287")

    args = parser.parse_args()

    logger = setup_logger(
        name="quality check",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )

    db = DatasetDatabase(args.db_file_path)
    with db.with_session() as session:
        dataset_uuid = (
            session.query(DatasetDB)
            .filter(DatasetDB.convert_path == args.repo_path)
            .first()
            .dataset_uuid
        )
        bad_episodes = _get_bad_episodes(
            session=session,
            dataset_uuid=dataset_uuid,
            state_data_score_threshold=args.state_data_score_threshold,
            action_data_score_threshold=args.action_data_score_threshold,
            video_score=args.video_score_threshold,
        )

    hardlink_repo_path = gen_qced_repo(
        repo_path=args.repo_path,
        bad_episodes=bad_episodes,
        min_episodes_num=args.min_episodes_num_threshold,
        ds_api_key=args.ds_api_key,
    )


"""Usage:
python scripts/quality_check/qced_repo_gen_test.py --db_file_path ./db/datasets_new.db --log_dir ./logs/qced_repo_gen, --repo_path /mnt/nas/synnas/docker2/robocoin-datasets/discover_robotics_aitbot_mmk2_the_cup_is_put_into_the_bucket
"""
