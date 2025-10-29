import argparse

from robocoin_dataset.annotation.subtask_annotion.url_video_hash import UrlVideoDownload
from robocoin_dataset.utils.logger import setup_logger

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db_file_path", type=str, required=True)
    parser.add_argument("--log_dir", type=str, default="./logs/")
    args = parser.parse_args()

    logger = setup_logger("video_download", args.log_dir)

    video_hasher = UrlVideoDownload(args.db_file_path, logger=logger)
    video_hasher.download_videos_multi_threads()

"""Usage:
python scripts/annotation/subtask_annotation/download_url_videos.py --db_file_path ./db/datasets_new.db --log_dir ./logs
"""
