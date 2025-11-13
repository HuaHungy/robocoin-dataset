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

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db_file_path", type=str, default="db/datasets_new.db")
    parser.add_argument("--device_model", type=str, default="all")
    parser.add_argument("--cam-keyword", type=str, default="high")
    parser.add_argument("--output_dir", type=str, default="high")
    args = parser.parse_args()

    db = DatasetDatabase(args.db_file_path)
    with db.with_session() as session:
        query = session.query(DatasetDB).filter(DatasetDB.video_match_status == TaskStatus.FAILED)
        if args.device_model != "all":
            print(f"Processing {args.device_model} datasets")
            query = query.filter(DatasetDB.device_model == args.device_model)

        items = query.all()

    if not items:
        print("No items to process")
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

        output_repo_dir: Path = Path(args.output_dir) / Path(item.convert_path).name

        if output_repo_dir.exists():
            print(f"{output_repo_dir} exists, please select another output_dir")
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

                if args.cam_keyword in camera_dir.name:
                    print(f"found {camera_dir}")
                    featured_dirs.append(camera_dir)

        if not featured_dirs:
            print(f"No {args.cam_keyword} camera found in {repo_path}")
            continue

        video_files: list[Path] = []
        for cam_dir in featured_dirs:
            for lost_ep in unmatched_eps:
                video_file = cam_dir / f"episode_{lost_ep:06d}.mp4"
                if video_file.exists():
                    print(f"found {video_file}")
                    video_files.append(video_file)

        new_video_files = [
            output_repo_dir / "videos" / video_file.relative_to(repo_path / "videos")
            for video_file in video_files
        ]

        print(f"found {len(video_files)} videos, press enter to copy them")
        for video_file, new_video_file in tqdm.tqdm(
            zip(video_files, new_video_files),
            desc="Copying videos",
            unit="video",
            total=len(video_files),
        ):
            new_video_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(video_file, new_video_file)

"""
python scripts/annotation/subtask_annotation/download_st_unannotated_episodes.py --db_file_path /mnt/nas/db/datasets_new.db --device_model realman_rmc_aidal --cam-keyword high_rgb --output_dir datas/unannotated_episodes
"""
