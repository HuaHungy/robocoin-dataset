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
        "--dataset_uuids",
        type=str,
        nargs="*",  # 零个或多个
        default=None,
        help="Specify zero or more dataset UUIDs",
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
        video_subtask_annotation.correspond_dataset_subtask_annotations(args.dataset_uuids)

    except Exception:
        print(traceback.format_exc())

"""usages:
该程序功能为：通过视频指纹识别，为转换好的数据集的Episode，对齐json标注条目
# 可以指定数据集 uuid，前提是数据集已经完成格式转换，如果不设定uuid，则默认处理所有数据集
python -m scripts.annotation.dataset_subtask_annotation_corresponding \
    --db_file ./db/datasets.db \
    --json_src_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/source-files \
    --json_dst_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/destination-files \
    --video_download_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/download-videos \
    --dataset_uuid 3f805357-8df7-41c3-aa00-a08b08e0915c \
      4363efec-236f-4495-a86b-14c3a5d20345 \
      666a0109-3399-4955-b2fb-66509139637f \
      2a2cc6a7-ac07-494e-9b05-0a437532bdb1 \
      3448d8ea-8209-43cf-bfcc-550863a26b13 \
      59eb8786-4e0e-4c5e-b129-aec36ec1eda9 \
      8276223a-988a-4a97-8459-97f7c498cbb5 \
      88e35314-80f0-4a2b-a92e-5b0e769483ae \
      aa202f76-162f-44a2-aa83-c8448ab991e2 \
      e095217a-10c3-44e6-9a26-08a1758a1243 \
      f217b0c1-9f1e-4598-9845-0a85906dadf6 \
      95db1bea-22a4-4ba9-9097-ef3711a084d0 \
      66922d94-1a12-4281-bddf-1da6a26caf4c \
      bbe55f1a-041d-4956-b4a9-17c9457510aa \
      c79b49bf-cadf-4094-831d-bbf6403956c6 \
      25f997d1-8e07-4035-b14f-0b3219460e17 \
      8c203fd8-2988-4e8f-8ddc-eedbb69dcdfe \
      d4c26606-f766-48ca-befd-dbdeead83a95 \
      40947b8c-339b-414f-94d9-6d5f24520362 \
      928d5a84-eae7-4fae-b272-9356c151aa6d \
      257289bb-b38e-411f-a2d0-d787e9f12419 \
      327e0fe7-1be9-4724-b1ae-f511d8ab7f6b \
      a46926fb-7a26-4e5e-a5ff-1109548c473e \
      6fed3c85-39db-4ff9-81e4-d5b813bc0577 \
      ee676d19-f3d4-4c11-bb83-9a2474cf77c5 \
      d27ed137-4947-4948-b818-a02094cab254 \
      f60ef2d6-fc04-4276-b75e-e8b54ab7602c \
      fe0a75c5-bab5-4e43-9502-081da6770b61 
"""
