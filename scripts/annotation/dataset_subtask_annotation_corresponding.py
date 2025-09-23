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
        "--json_dst_dir",
        type=str,
        default="",
        help="json dst dir",
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
        "--dataset_uuid", type=str, default=None, help="数据集的UUID（可选，如果不指定则为None）"
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
        json_dst_dir=args.json_dst_dir,
        video_dl_dir=args.video_download_dir,
        logger=log,
    )
    try:
        video_subtask_annotation.sync_dataset_annotation_corresponding_task()
        video_subtask_annotation.correspond_dataset_subtask_annotations(args.dataset_uuid)

    except Exception:
        print(traceback.format_exc())

"""usages:
该程序功能为：通过视频指纹识别，为转换好的数据集的Episode，对齐json标注条目
# 可以指定数据集 uuid，前提是数据集已经完成格式转换，如果不设定uuid，则默认处理所有数据集
python -m scripts.annotation.dataset_subtask_annotation\
    --db_file ./db/datasets.db \
    --json_src_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/source-files \
    --json_dst_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/destination-files \
    --video_download_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/download-videos \
    --dataset_uuid 3f805357-8df7-41c3-aa00-a08b08e0915c
"""
