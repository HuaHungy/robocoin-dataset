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
        "--deepseek_api_key",
        type=str,
        default="sk-a3c8736391cf43809957329f28cac287",
        help="deepseek api key",
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
        passed_json_dst_dir=args.passed_json_dst_dir,
        impassed_json_dst_dir=args.impassed_json_dst_dir,
        video_dl_dir=args.video_download_dir,
        logger=log,
    )
    try:
        # 为lerobot格式的episode视频生成文件Hash和指纹,
        # 从lerobot_format_convert表中查找已经完成转换，但还未生成lerobot视频文件hash和视频指纹的数据集,
        # 生成结果写入到数据表leformat_episode_video_hash_status和leformat_episode_video_hash中
        video_subtask_annotation.generate_leformat_episode_video_hashes_threas_pool()

        # 将baai标注团队的子任务标注json文件入库,结果文件写入到数据表url_video_subtask_annotation中
        video_subtask_annotation.enter_url_video_st_annotation_json_files()

        # 下载json文件中的url video到Nas, 结果写入到数据表download_videos中
        video_subtask_annotation.download_videos_multi_threads()

        # 为url video生成文件Hash和指纹, 结果写入到数据表download_videos中
        video_subtask_annotation.generate_url_video_file_hashes_multi_threads()
        video_subtask_annotation.generate_url_video_image_hashes_multi_threads

        # 将lerobot格式的episode视频与url video进行匹配
        # 结果写入到leformat_episode_url_video_match及leformat_episode_url_video_match_status中
        video_subtask_annotation.match_leformat_episode_with_url_video()

        # 根据匹配结果，生成lerobot格式的子任务标注数据，
        # 结果写入到数据表leformat_dataset_episode_original_subtask_annotation_status和leformat_dataset_episode_original_subtask_annotation中
        video_subtask_annotation.generate_leformat_datasets_original_range_subtask_annotation_baai()

        # 优化子任务标注数据，
        # 结果写入到数据表leformat_dataset_episode_optimized_subtask_annotation_status和leformat_dataset_episode_optimized_subtask_annotation中
        video_subtask_annotation.generate_leformat_datasets_optimized_range_subtask_annotation_baai(
            dp_api_key=args.deepseek_api_key
        )

        # 为lerobot parquet文件注入子任务标注数据，
        # 结果写入到数据表leformat_dataset_episode_subtask_range_annotation_embedding_status
        video_subtask_annotation.embed_leformat_dataset_episode_optimized_subtask_range_annotation_baai()

    except Exception:
        print(traceback.format_exc())

"""usages:
python -m scripts.annotation.subtask_annotation_pipeline_baai \
    --db_file ./db/datasets.db \
    --json_src_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/files-to-process \
    --passed_json_dst_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/passed-files \
    --impassed_json_dst_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/impassed-files \
    --video_download_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/download-videos 
"""
