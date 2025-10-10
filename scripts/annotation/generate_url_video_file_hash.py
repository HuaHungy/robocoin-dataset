import argparse
import logging
import traceback
from pathlib import Path

from robocoin_dataset.annotation.subtask_annotion.video_subtask_annotation import (
    VideoSubtaskAnnotation,
)
from robocoin_dataset.utils.logger import setup_logger

if __name__ == "__main__":
    argparser = argparse.ArgumentParser()
    argparser.add_argument(
        "--db_file",
        type=str,
        default="",
        help="db file path",
    )

    argparser.add_argument(
        "--json_src_dir",
        type=str,
        default="",
        help="json src dir",
    )

    argparser.add_argument(
        "--passed_json_dst_dir",
        type=str,
        default="",
        help="dir to save passed json files",
    )

    argparser.add_argument(
        "--impassed_json_dst_dir",
        type=str,
        default="",
        help="dir to save impassed json files",
    )

    argparser.add_argument(
        "--video_download_dir",
        type=str,
        default="",
        help="video download dir",
    )

    argparser.add_argument(
        "--log_dir",
        type=str,
        default="outputs/logs/",
        help="Path to log file.",
    )

    argparser.add_argument(
        "--api_key",
        type=str,
        default="sk-a3c8736391cf43809957329f28cac287",
        help="api key",
    )
    args = argparser.parse_args()

    log = setup_logger(
        name="video_subtask_annotation",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )

    video_subtask_annotation = VideoSubtaskAnnotation(
        db_file_path=args.db_file,
        json_src_dir=args.json_src_dir,
        passed_json_dst_dir=args.passed_json_dst_dir,
        impassed_json_dst_dir=args.impassed_json_dst_dir,
        video_dl_dir=args.video_download_dir,
        logger=log,
    )
    try:
        video_subtask_annotation.generate_url_video_file_hashes_multi_threads()

    except Exception:
        print(traceback.format_exc())

"""usages:
python -m scripts.annotation.generate_url_video_file_hash \
    --db_file ./db/datasets.db \
    --json_src_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/files-to-process \
    --passed_json_dst_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/passed-files \
    --impassed_json_dst_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/impassed-files \
    --video_download_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/download-videos 
"""
