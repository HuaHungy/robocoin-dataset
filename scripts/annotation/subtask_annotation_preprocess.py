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

    args = argparser.parse_args()

    log = setup_logger(
        name="video_subtask_annotation",
        log_dir=Path(args.log_dir),
        level=logging.ERROR,
    )

    video_subtask_annotation = VideoSubtaskAnnotation(
        db_file_path=args.db_file,
        json_src_dir=args.json_src_dir,
        json_dst_dir=args.json_dst_dir,
        video_dl_dir=args.video_download_dir,
        logger=log,
    )
    try:
        video_subtask_annotation.process_video_subtask_annotation_json_files()
        video_subtask_annotation.sync_download_tasks()
        video_subtask_annotation.download_videos_multi_threads()
        video_subtask_annotation.sync_filehash_tasks()
        video_subtask_annotation.compute_file_hashes_multi_threads()
        video_subtask_annotation.sync_imagehash_tasks()
        video_subtask_annotation.compute_image_hashes_multi_threads()
        # video_subtask_annotation.compute_image_hashes_single_threads()

    except Exception:
        print(traceback.format_exc())

"""usages:
# 该程序功能包括：
1. 对子任务标注json文件进行批处理
    通过参数 --json_src_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/source-files 来指定源文件目录
    需要人工将新增的子任务标注json文件复制到该目录下
    程序自动将通过检查的所有json文件移动至 --json_dst_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/destination-files 目录下

2. 自动生成标注视频下载任务、多线程下载，下载目录为 --video_download_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/download-videos 

3. 自动生成文件hash任务、多线程计算文件hash，结果保存在到数据库中

4. 自动生成视频指纹计算任务、多线程计算，结果保存在到数据库中

python -m scripts.annotation.subtask_annotation_preprocess \
    --db_file ./db/datasets.db \
    --json_src_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/files-to-process \
    --json_dst_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/processed-files \
    --video_download_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/download-videos 
"""
