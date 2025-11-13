import argparse
import json
import shutil
from pathlib import Path

import tqdm

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DatasetDB,
    TaskStatus,
    VideoOptStAnnotationDB,
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db_file_path", type=str, default="db/datasets_new.db")
    parser.add_argument("--device_model", type=str, default="all")
    parser.add_argument("--cam-keyword", type=str, default="high")
    parser.add_argument("--output_dir", type=str, default="high")
    args = parser.parse_args()

    print(args.db_file_path)
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

    print(f"output_dir: {args.output_dir}")

    for item in tqdm.tqdm(items, desc="Copying Datasets Files", unit="dataset"):
        repo_path = Path(item.convert_path)
        info_file_path = repo_path / "meta/info.json"
        with open(info_file_path) as f:
            info = json.load(f)
            total_episodes = info["total_episodes"]
        with db.with_session() as session:
            anno_items = session.query(VideoOptStAnnotationDB).filter(
                VideoOptStAnnotationDB.dataset_uuid == item.dataset_uuid
            )

        eps = {anno_item.episode_idx for anno_item in anno_items}

        lost_eps = set(range(total_episodes)) - eps
        if not lost_eps:
            continue

        output_repo_dir: Path = Path(args.output_dir) / Path(item.convert_path).name

        if output_repo_dir.exists():
            print(f"{output_repo_dir} exists, please select another output_dir")
            continue

        anno_labels = {anno_item.annotation for anno_item in anno_items}
        print(f"found {len(anno_labels)} labels: {anno_labels}")
        output_repo_dir.mkdir(parents=True)

        with open(output_repo_dir / "labels.txt", "w") as f:
            for label in anno_labels:
                f.write(label + "\n")

        input("Copied labels.txt, press enter to continue")

        shutil.copytree(repo_path / "meta", output_repo_dir / "meta")

        video_dirs: list[Path] = [
            chunk_dir
            for chunk_dir in (output_repo_dir / "videos").glob("chunk_*")
            if chunk_dir.is_dir()
        ]
        input(f"found {len(video_dirs)} video dirs: {video_dirs}")
        featured_dirs = []
        for video_dir in video_dirs:
            for camera_dir in video_dir.glob():
                if not camera_dir.is_dir():
                    continue

                if args.cam_keyword in camera_dir.name:
                    featured_dirs.append(camera_dir)

        if not featured_dirs:
            print(f"No {args.cam_keyword} camera found in {repo_path}")
            continue

        video_files: list[Path] = []
        for cam_dir in featured_dirs:
            for lost_ep in lost_eps:
                video_file = cam_dir / f"episode_{lost_ep:06d}.mp4"
                if video_file.exists():
                    video_files.append(video_file)

        new_video_files = [
            output_repo_dir / "videos" / video_file.relative_to(repo_path / "videos")
            for video_file in video_files
        ]

        input(f"found {len(video_files)} videos, press enter to copy them")
        for video_file, new_video_file in tqdm.tqdm(
            zip(video_files, new_video_files), desc="Copying videos", unit="video"
        ):
            new_video_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(video_file, new_video_file)

"""
python scripts/annotation/subtask_annotation/download_st_unannotated_episodes.py --db_file_path /mnt/nas/db/datasets_new.db --device_model realman_rmc_aidal --cam-keyword high_rgb --output_dir datas/unannotated_episodes
"""
