import argparse

from robocoin_dataset.annotation.subtask_annotion.video_match import VideoMatch
from robocoin_dataset.utils.logger import setup_logger

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db_file_path", type=str, required=True)
    parser.add_argument("--log_dir", type=str, default="./logs")
    parser.add_argument("--match_failed_videos", action="store_true")

    args = parser.parse_args()

    logger = setup_logger(name="url_video_hash", log_dir=args.log_dir)
    video_hasher = VideoMatch(args.db_file_path, logger=logger)
    video_hasher.match_videos(args.match_failed_videos)


"""Usage:
python scripts/annotation/subtask_annotation/video_match.py --db_file_path ./db/datasets_new.db --log_dir ./logs --match_failed_videos
"""
