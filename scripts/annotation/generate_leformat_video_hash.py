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
    # argparser.add_argument(
    #     "--dataset_uuids",
    #     type=str,
    #     nargs="*",  # 零个或多个
    #     default=None,
    #     help="Specify zero or more dataset UUIDs",
    # )

    argparser.add_argument(
        "--dataset_convert_paths",
        type=str,
        nargs="*",  # 零个或多个
        default=None,
        help="Specify zero or more dataset data path",
    )
    argparser.add_argument(
        "--ignore_file_hash",
        action="store_true",
        default=False,
        help="If specified, ignore file hash. Default is False (file hash is checked).",
    )
    argparser.add_argument(
        "--ignore_image_hash",
        action="store_true",
        default=False,
        help="If specified, ignore image hash. Default is False (image hash is checked).",
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
        video_subtask_annotation.sync_leformat_episode_video_hash_status()
        video_subtask_annotation.compute_leformat_episode_video_image_hashes_threas_pool(
            num_workers=32
        )

    except Exception:
        print(traceback.format_exc())

    """_summary_
python -m scripts.annotation.generate_leformat_video_hash\
    --db_file ./db/datasets.db \
    --json_src_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/files-to-process \
    --passed_json_dst_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/passed-files \
    --impassed_json_dst_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/impassed-files \
    --video_download_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/download-videos 
    """
