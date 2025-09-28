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
        video_subtask_annotation.sync_dataset_annotation_corresponding_task()
        video_subtask_annotation.correspond_dataset_subtask_annotations(
            args.dataset_convert_paths, not args.ignore_file_hash, not args.ignore_image_hash
        )

    except Exception:
        print(traceback.format_exc())

"""usages:
该程序功能为：通过视频指纹识别，为转换好的数据集的Episode，对齐json标注条目
# 可以指定数据集 uuid，前提是数据集已经完成格式转换，如果不设定uuid，则默认处理所有数据集

python -m scripts.annotation.dataset_subtask_annotation_corresponding \
    --db_file ./db/datasets.db \
    --json_src_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/files-to-process \
    --passed_json_dst_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/passed-files \
    --impassed_json_dst_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/impassed-files \
    --video_download_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/download-videos 
    --datset_convert_paths \
    --ignore_file_hash \
    /mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_basket_storage_banana \
    /mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_basket_storage_egg_yolk_pastry \
    /mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_basket_storage_long_bread \
    /mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_basket_storage_orange

python -m scripts.annotation.dataset_subtask_annotation_corresponding \
    --db_file ./db/datasets.db \
    --json_src_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/source-files \
    --json_dst_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/destination-files \
    --video_download_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/download-videos \
    --datset_convert_paths /mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_basket_storage_banana \
    /mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_basket_storage_egg_yolk_pastry \
    /mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_basket_storage_long_bread \
    /mnt/nas/synnas/docker2/robocoin-datasets/realman_rmc_aidal_basket_storage_orange
"""
