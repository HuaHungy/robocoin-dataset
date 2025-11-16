import argparse
import json
import shutil
from pathlib import Path

import tqdm

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DatasetDB,
    TaskStatus,
    UrlVideoStAnnotationDB,
    VideoMatchDB,
)
from robocoin_dataset.utils.logger import setup_logger

logger = setup_logger(name="download_unannotated_episodes", log_dir="logs")

main_camera_keywords = [
    "high_rgb",
    "head_rgb",
    "front_rgb",
    "egg_view",
    "left_high",
    "right_high",
    "ego_view",
]

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db_file_path", type=str, default="db/datasets_new.db")
    parser.add_argument("--device_model", type=str, default="all")
    parser.add_argument("--output_dir", type=str, default="./data/unannotated_episodes")
    args = parser.parse_args()

    db = DatasetDatabase(args.db_file_path)
    with db.with_session() as session:
        query = session.query(DatasetDB).filter(DatasetDB.video_match_status == TaskStatus.FAILED)
        query = query.filter(DatasetDB.convert_status == TaskStatus.COMPLETED)
        if args.device_model != "all":
            logger.info(f"Processing {args.device_model} datasets")
            query = query.filter(DatasetDB.device_model == args.device_model)

        items = query.all()

    if not items:
        logger.info("No items to process")
        exit(0)

    for item in tqdm.tqdm(items, desc="Copying Datasets Files", unit="dataset"):
        repo_path = Path(item.convert_path)
        info_file_path = repo_path / "meta/info.json"
        with open(info_file_path) as f:
            info = json.load(f)
            total_episodes = info["total_episodes"]
        with db.with_session() as session:
            matched_items = session.query(VideoMatchDB).filter(
                VideoMatchDB.dataset_uuid == item.dataset_uuid
            )

        matched_eps = {matched_item.episode_idx for matched_item in matched_items}

        unmatched_eps = set(range(total_episodes)) - matched_eps
        if not unmatched_eps:
            continue

        output_repo_dir: Path = (
            Path(args.output_dir) / args.device_model / Path(item.convert_path).name
        )

        if output_repo_dir.exists():
            logger.info(f"{output_repo_dir} exists, please select another output_dir")
            continue

        with db.with_session() as session:
            items = (
                session.query(VideoMatchDB)
                .filter(VideoMatchDB.dataset_uuid == item.dataset_uuid)
                .all()
            )

        url_video_ids = [item.url_video_id for item in items]

        with db.with_session() as session:
            url_anno_items = (
                session.query(UrlVideoStAnnotationDB)
                .filter(UrlVideoStAnnotationDB.video_id.in_(url_video_ids))
                .all()
            )

        url_anno_labels = set([url_anno_item.annotation for url_anno_item in url_anno_items])

        output_repo_dir.mkdir(parents=True)

        with open(output_repo_dir / "labels.txt", "w") as f:
            for label in url_anno_labels:
                f.write(label + "\n")

        shutil.copytree(repo_path / "meta", output_repo_dir / "meta")

        video_chunk_dirs: list[Path] = [
            chunk_dir for chunk_dir in (repo_path / "videos").glob("chunk-*") if chunk_dir.is_dir()
        ]
        featured_dirs = []
        for video_chunk_dir in video_chunk_dirs:
            for camera_dir in video_chunk_dir.glob("*"):
                if not camera_dir.is_dir():
                    continue

                for main_camera_keyword in main_camera_keywords:
                    if main_camera_keyword in camera_dir.name:
                        featured_dirs.append(camera_dir)
                        break

        if not featured_dirs:
            logger.error(f"No camera keywork found in {repo_path}")
            continue

        video_files: list[Path] = []
        for cam_dir in featured_dirs:
            for lost_ep in unmatched_eps:
                video_file = cam_dir / f"episode_{lost_ep:06d}.mp4"
                if video_file.exists():
                    video_files.append(video_file)

        new_video_files = [
            output_repo_dir / "videos" / video_file.relative_to(repo_path / "videos")
            for video_file in video_files
        ]

        logger.info(f"found {len(video_files)} videos")
        for video_file, new_video_file in tqdm.tqdm(
            zip(video_files, new_video_files),
            desc="Copying videos",
            unit="video",
            total=len(video_files),
        ):
            new_video_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(video_file, new_video_file)

"""
python scripts/annotation/subtask_annotation/download_st_unannotated_episodes.py --db_file_path db/datasets_new.db --device_model ruantong_a2d --cam-keyword high_rgb --output_dir datas/unannotated_episodes
"""
