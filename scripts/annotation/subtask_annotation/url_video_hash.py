import argparse

from robocoin_dataset.annotation.subtask_annotion.url_video_hash import UrlVideoHash
from robocoin_dataset.utils.logger import setup_logger

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db_file_path", type=str, required=True)
    parser.add_argument("--logger_path", type=str, default="./logs")
    args = parser.parse_args()

    logger = setup_logger(name="url_video_hash", log_dir=args.logger_path)
    url_video_hasher = UrlVideoHash(args.db_file_path, batch_size=2, logger=logger)
    url_video_hasher.compute_url_video_hashes()

"""Usage:
python scripts/annotation/subtask_annotation/url_video_hash.py --db_file_path ./db/datasets_new.db --logger_path ./logs
"""
