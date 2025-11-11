#!/usr/bin/env python3
"""
Page Sync Orchestration Module

This module contains the main orchestration logic for syncing dataset information
to the page project. It coordinates the following workflow:
1. Detect and create directory structure (assets/dataset_info, assets/videos, assets/info)
2. Loop through pending tasks:
   - Sync task status (mark eligible datasets as PENDING)
   - Generate one task (mark PENDING -> PROCESSING)
   - Copy YAML file to dataset_info
   - Sample and compress video to videos directory
   - Align video name to match dataset name
   - Mark task as COMPLETED or FAILED
3. Generate consolidated metadata files:
   - consolidated_datasets.json: All metadata in one file
   - data_index.json: List of all YAML files

The actual business logic is implemented in page_sync_utils.py.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from robocoin_dataset.database.database import DatasetDatabase


def construce_target_file(
    db: "DatasetDatabase",
    session: "Session",
    target_dir: str,
    target_size_kb: int = 500,
    logger: logging.Logger | None = None,
) -> None:
    """
    Construct target file structure with upsert logic.
    The main orchestration function for page-needed-data construction.

    Target structure:
    target_dir/ (root of page project)
        assets/
            dataset_info/
                *.yml files
            videos/
                *.mp4 files
            info/
                consolidated_datasets.json
                data_index.json

    Args:
        db: Database connection
        session: SQLAlchemy session
        target_dir: Root directory of the page project
        target_size_kb: Target size for compressed videos in KB (default: 500)
        logger: Optional logger instance
    """
    from robocoin_dataset.page_sync.page_sync_utils import (
        _align_video_name_with_yaml,
        _compress_video_to_dst,
        _copy_yaml_file_from_db,
        _gen_consolidation,
        _gen_data_index,
        _gen_one_page_sync_task,
        _get_dataset_name,
        _mark_task_completed,
        _mark_task_failed,
        _sample_one_video_path,
        _sync_page_sync_status,
        _validate_exist,
    )

    _logger = logger or logging.getLogger(__name__)
    target_root = Path(target_dir)

    # 1. Detect and create assets folder if it doesn't exist
    assets_dir = target_root / "assets"
    if not assets_dir.exists():
        assets_dir.mkdir(parents=True, exist_ok=True)
        _logger.debug(f"Created assets directory: {assets_dir}")
    else:
        _logger.debug(f"Assets directory already exists: {assets_dir}")

    # 2. Detect and create dataset_info and videos folders if they don't exist
    dataset_info_dir = assets_dir / "dataset_info"
    if not dataset_info_dir.exists():
        dataset_info_dir.mkdir(parents=True, exist_ok=True)
        _logger.debug(f"Created dataset_info directory: {dataset_info_dir}")
    else:
        _logger.debug(f"Dataset_info directory already exists: {dataset_info_dir}")

    videos_dir = assets_dir / "videos"
    if not videos_dir.exists():
        videos_dir.mkdir(parents=True, exist_ok=True)
        _logger.debug(f"Created videos directory: {videos_dir}")
    else:
        _logger.debug(f"Videos directory already exists: {videos_dir}")

    info_dir = assets_dir / "info"
    if not info_dir.exists():
        info_dir.mkdir(parents=True, exist_ok=True)
        _logger.debug(f"Created info directory: {info_dir}")
    else:
        _logger.debug(f"Info directory already exists: {info_dir}")

    # 3-8. Main loop: sync -> generate task -> copy yaml -> copy & compress videos -> align video name -> mark completed
    task_count = 0
    while True:
        # 3. Sync the task status
        _logger.debug("Syncing page sync status...")
        _sync_page_sync_status(db, session, _logger)

        # 4. Generate one task
        _logger.debug("Generating next task...")
        yaml_path, hardlink_path, dataset_uuid = _gen_one_page_sync_task(session)

        if yaml_path is None:
            _logger.info("No more pending tasks to process")
            break

        if not dataset_uuid:
            _logger.error("No dataset_uuid returned from task generation")
            continue

        task_count += 1
        _logger.info(f"Processing task {task_count}: dataset_uuid={dataset_uuid}")
        _logger.debug(f"  yaml_path: {yaml_path}")
        _logger.debug(f"  hardlink_path: {hardlink_path}")

        # Validate that both yaml_path and hardlink_path exist
        if not _validate_exist(yaml_path, hardlink_path):
            _logger.error(
                f"Validation failed for dataset {dataset_uuid}: "
                f"yaml_path={yaml_path}, hardlink_path={hardlink_path}. "
                f"Both paths must exist. Marking as FAILED."
            )
            _mark_task_failed(session, dataset_uuid)
            continue

        try:

            # 5. Copy yaml
            _logger.debug(f"Getting dataset name for {dataset_uuid}...")
            dataset_name = _get_dataset_name(session)
            if not dataset_name:
                _logger.error(f"Failed to get dataset name for dataset {dataset_uuid}")
                _mark_task_failed(session, dataset_uuid)
                continue

            _logger.info(f"Dataset name: {dataset_name}")
            yaml_dst = dataset_info_dir / f"{dataset_name}.yml"

            _logger.debug(f"Copying YAML from {yaml_path} to {yaml_dst}...")
            _copy_yaml_file_from_db(yaml_path, str(yaml_dst))
            _logger.info(f"Copied YAML file to {yaml_dst}")

            # 6. Sample and compress videos
            _logger.debug(f"Sampling video from hardlink path: {hardlink_path}...")
            sampled_video_path = _sample_one_video_path(hardlink_path)
            if not sampled_video_path:
                _logger.error(f"Failed to sample video from {hardlink_path}")
                _mark_task_failed(session, dataset_uuid)
                continue

            _logger.info(f"Sampled video: {sampled_video_path}")
            _logger.debug(f"Starting video compression (target: {target_size_kb}KB)...")
            _compress_video_to_dst(sampled_video_path, str(videos_dir), target_size_kb)
            _logger.info(f"Compressed video from {sampled_video_path} into {videos_dir}")

            # 7. Alighment-Rename videos
            _logger.debug("Aligning video name with dataset name...")
            compressed_video_name = Path(sampled_video_path).name
            compressed_video_path = videos_dir / compressed_video_name
            _align_video_name_with_yaml(str(yaml_dst), str(compressed_video_path), dataset_name)
            _logger.info(f"Aligned video name to {dataset_name}")

            # 8. Update task status to COMPLETED
            _mark_task_completed(session, dataset_uuid)
            _logger.info(f"Successfully processed dataset: {dataset_name} ({dataset_uuid})")

        except Exception as e:
            _logger.error(f"Error processing task {dataset_uuid}: {e}", exc_info=True)
            _mark_task_failed(session, dataset_uuid)

    # 9. Generate consolidated datasets and data index files
    _logger.info("Generating consolidated metadata files...")
    try:
        consolidated_path = info_dir / "consolidated_datasets.json"
        _logger.debug(f"Generating consolidated datasets at: {consolidated_path}")
        _gen_consolidation(str(dataset_info_dir), str(consolidated_path))

        data_index_path = info_dir / "data_index.json"
        _logger.debug(f"Generating data index at: {data_index_path}")
        _gen_data_index(str(dataset_info_dir), str(data_index_path))

        _logger.info("Successfully generated consolidated metadata files")
    except Exception as e:
        _logger.error(f"Error generating consolidated metadata files: {e}", exc_info=True)

    _logger.info(f"Target file structure construction completed at: {target_dir}")


def main(
    db_path: str,
    target_dir: str,
    target_size_kb: int = 500,
    log_level: str = "INFO",
) -> None:
    """
    Main entry point for page sync operation.

    Args:
        db_path: Path to the SQLite database
        target_dir: Root directory of the page project
        target_size_kb: Target size for compressed videos in KB (default: 500)
        log_level: Logging level (default: INFO)
    """
    from robocoin_dataset.database.database import DatasetDatabase

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    # Initialize database
    db = DatasetDatabase(db_path)
    logger.info(f"Initialized database at: {db_path}")

    # Run the sync operation
    with db.with_session() as session:
        construce_target_file(
            db=db,
            session=session,
            target_dir=target_dir,
            target_size_kb=target_size_kb,
            logger=logger,
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Sync dataset information to page project"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        required=True,
        help="Path to the SQLite database",
    )
    parser.add_argument(
        "--target-dir",
        type=str,
        required=True,
        help="Root directory of the page project",
    )
    parser.add_argument(
        "--target-size-kb",
        type=int,
        default=500,
        help="Target size for compressed videos in KB (default: 500)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    main(
        db_path=args.db_path,
        target_dir=args.target_dir,
        target_size_kb=args.target_size_kb,
        log_level=args.log_level,
    )
