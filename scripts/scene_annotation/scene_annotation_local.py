import argparse
import logging
from pathlib import Path

from robocoin_dataset.annotation.scene_annotation.scene_annotation import (
    SceneAnnotationLocal,
)
from robocoin_dataset.utils.logger import setup_logger

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db_file_path",
        type=str,
        default="",
        help="Path to the database file",
    )

    parser.add_argument(
        "--log_dir",
        type=str,
        default="",
        help="Path to the log directory",
    )

    parser.add_argument(
        "--folder_path",
        type=str,
        default="",
        help="Local result folder",
    )

    args = parser.parse_args()
    db_file_path = Path(args.db_file_path).expanduser().absolute()

    if not db_file_path.exists():
        print(f"{db_file_path} does not exist")
        exit(1)
    
    logger = setup_logger(
        name="scene_annotation",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )

    scene_annotation = SceneAnnotationLocal(db_file_path, logger=logger)
    scene_annotation.syn_scene_annotation_task()
    local_forder_path = Path(args.folder_path).expanduser().absolute()
    scene_annotation.process_folder(local_forder_path)

"""usage:
# local
python scripts/scene_annotation/scene_annotation_local.py \
    --db_file_path ./db/datasets_new.db \
    --folder_path /mnt/nas/synnas/docker2/scene_annotation \
    --log_dir ./logs/scene_annotation/
"""
