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
import traceback
from pathlib import Path
from typing import TYPE_CHECKING

from robocoin_dataset.prepare_metadata.metadata_service import MetadataSyncService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from robocoin_dataset.database.database import DatasetDatabase


def construce_target_file(
    db: "DatasetDatabase",
    session: "Session",
    target_dir: str,
    crf: int = 18,
    update_videos: bool = False,
    force_regenerate: bool = False,
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
            thumbnails/
                *.jpg files
            info/
                consolidated_datasets.json
                data_index.json

    Args:
        db: Database connection
        session: SQLAlchemy session
        target_dir: Root directory of the page project
        crf: CRF value for video compression (default: 18, range: 0-51, lower = better quality)
        update_videos: If True, always regenerate videos and thumbnails; if False, skip existing ones (default: False)
        force_regenerate: If True, ignore existing COMPLETED status and rebuild assets whenever prerequisites are ready
        logger: Optional logger instance
    """
    from robocoin_dataset.page_sync.page_sync_task import (
        _gen_one_page_sync_task,
        _mark_task_completed,
        _mark_task_failed,
        _reset_comp_to_pend,
        _sync_page_sync_status,
    )
    from robocoin_dataset.page_sync.page_sync_utils import (
        _align_video_name_with_yaml,
        _compress_video_to_dst,
        _copy_robot_aliases_and_exclude,
        _gen_consolidation,
        _gen_data_index,
        _gen_video_thumbnail,
        _get_dataset_name,
        _record_missing_yaml,
        _sample_one_video_path,
        _write_unified_metadata_yaml,
    )

    _logger = logger or logging.getLogger(__name__)
    target_root = Path(target_dir)

    # 1. Detect and create assets folder if it doesn't exist
    assets_dir = target_root / "assets"
    if not assets_dir.exists():
        assets_dir.mkdir(parents=True, exist_ok=True)
        _logger.debug("[page_sync] Created assets directory: %s", assets_dir)
    else:
        _logger.debug("[page_sync] Assets directory already exists: %s", assets_dir)

    # 2. Detect and create dataset_info and videos folders if they don't exist
    dataset_info_dir = assets_dir / "dataset_info"
    if not dataset_info_dir.exists():
        dataset_info_dir.mkdir(parents=True, exist_ok=True)
        _logger.debug("[page_sync] Created dataset_info directory: %s", dataset_info_dir)
    else:
        _logger.debug("[page_sync] Dataset_info directory already exists: %s", dataset_info_dir)

    videos_dir = assets_dir / "videos"
    if not videos_dir.exists():
        videos_dir.mkdir(parents=True, exist_ok=True)
        _logger.debug("[page_sync] Created videos directory: %s", videos_dir)
    else:
        _logger.debug("[page_sync] Videos directory already exists: %s", videos_dir)

    info_dir = assets_dir / "info"
    if not info_dir.exists():
        info_dir.mkdir(parents=True, exist_ok=True)
        _logger.debug("[page_sync] Created info directory: %s", info_dir)
    else:
        _logger.debug("[page_sync] Info directory already exists: %s", info_dir)

    thumbnails_dir = assets_dir / "thumbnails"
    if not thumbnails_dir.exists():
        thumbnails_dir.mkdir(parents=True, exist_ok=True)
        _logger.debug("[page_sync] Created thumbnails directory: %s", thumbnails_dir)
    else:
        _logger.debug("[page_sync] Thumbnails directory already exists: %s", thumbnails_dir)

    # 2.5 出于性能考虑，复用同一个元数据服务实例，避免重复解析 DB 路径
    metadata_service = MetadataSyncService(
        db_file_path=str(db.db_file),
        logger=_logger,
    )
    if force_regenerate:
        _logger.info(
            "[page_sync] Force regenerate requested; resetting completed page-sync tasks to PENDING"
        )
        _reset_comp_to_pend(session, "dataset_info_sync_status", _logger)

    # 3-8. Main loop: sync -> generate task -> copy yaml -> copy & compress videos -> align video name -> mark completed
    task_count = 0
    while True:
        # 3. Sync the task status
        _logger.debug("[page_sync] Syncing page sync status...")
        _sync_page_sync_status(session, _logger)

        # 4. Generate one task
        _logger.debug("[page_sync] Generating next task...")
        yaml_path, hardlink_path, dataset_uuid = _gen_one_page_sync_task(session)

        if dataset_uuid is None:
            _logger.info("[page_sync] No more pending tasks to process")
            break

        task_count += 1
        _logger.info("[page_sync] Processing task %s: dataset_uuid=%s", task_count, dataset_uuid)
        _logger.debug("[page_sync]   yaml_path: %s", yaml_path)
        _logger.debug("[page_sync]   hardlink_path: %s", hardlink_path)

        # Validate paths: hardlink_path is required, yaml_path is optional (will be recorded if missing)
        missing_yaml = False
        yaml_issue = None

        if not yaml_path:
            missing_yaml = True
            yaml_issue = "yaml_path is None"
        elif not Path(yaml_path).exists():
            missing_yaml = True
            yaml_issue = f"yaml_path does not exist: {yaml_path}"

        if missing_yaml:
            _logger.warning(
                "[page_sync] Dataset %s: %s. Continuing without YAML metadata.",
                dataset_uuid,
                yaml_issue
            )
            # Record missing YAML to log file
            _record_missing_yaml(
                dataset_uuid=dataset_uuid,
                yaml_path=yaml_path,
                operation="page_sync",
                log_dir=target_root / "docs",
                logger=_logger,
            )

        # hardlink_path is required - fail if missing
        if not hardlink_path:
            error_msg = f"Page sync validation failed: hardlink_path is None. dataset_uuid={dataset_uuid}"
            _logger.error("[page_sync] Validation failed for dataset %s: hardlink_path is None. Marking as FAILED.", dataset_uuid)
            _mark_task_failed(session, dataset_uuid, error_msg)
            continue
        if not Path(hardlink_path).exists():
            error_msg = f"Page sync validation failed: hardlink_path does not exist: {hardlink_path}. dataset_uuid={dataset_uuid}"
            _logger.error("[page_sync] Validation failed for dataset %s: hardlink_path does not exist: %s. Marking as FAILED.", dataset_uuid, hardlink_path)
            _mark_task_failed(session, dataset_uuid, error_msg)
            continue

        try:

            # 5. Generate YAML via unified metadata
            _logger.debug("[page_sync] Getting dataset name for %s...", dataset_uuid)
            dataset_name = _get_dataset_name(session, dataset_uuid)
            if not dataset_name:
                _logger.error("[page_sync] Failed to get dataset name for dataset %s", dataset_uuid)
                err_msg = f"Failed to get dataset name for dataset_uuid={dataset_uuid}"
                _mark_task_failed(session, dataset_uuid, err_msg)
                continue

            _logger.info("[page_sync] Dataset name: %s", dataset_name)
            yaml_dst = dataset_info_dir / f"{dataset_name}.yml"

            _logger.debug(
                "[page_sync] Generating unified metadata YAML for dataset %s at %s using db %s",
                dataset_uuid,
                yaml_dst,
                db.db_file,
            )
            _write_unified_metadata_yaml(
                metadata_service=metadata_service,
                dst_yaml_path=str(yaml_dst),
                hardlink_path=str(hardlink_path),
                dataset_uuid=dataset_uuid,
            )
            _logger.info("[page_sync] Generated unified metadata YAML at %s", yaml_dst)

            # 6. Sample and compress videos
            _logger.debug("[page_sync] Sampling video from hardlink path: %s...", hardlink_path)
            sampled_video_path = _sample_one_video_path(hardlink_path)
            if not sampled_video_path:
                _logger.error("[page_sync] Failed to sample video from %s", hardlink_path)
                err_msg = (
                    "Failed to sample video for page sync: no suitable video found under "
                    f"hardlink_path={hardlink_path}"
                )
                _mark_task_failed(session, dataset_uuid, err_msg)
                continue

            _logger.info("[page_sync] Sampled video: %s", sampled_video_path)
            _logger.debug("[page_sync] Starting video compression with CRF=%s...", crf)
            _compress_video_to_dst(sampled_video_path, str(videos_dir), crf=crf, force_update=update_videos)
            _logger.info("[page_sync] Compressed video from %s into %s", sampled_video_path, videos_dir)

            # 7. Alighment-Rename videos
            _logger.debug("[page_sync] Aligning video name with dataset name...")
            compressed_video_name = Path(sampled_video_path).name
            compressed_video_path = videos_dir / compressed_video_name
            _align_video_name_with_yaml(str(yaml_dst), str(compressed_video_path), dataset_name)
            _logger.info("[page_sync] Aligned video name to %s", dataset_name)

            # 7.5. Generate thumbnail after video is renamed
            video_suffix = compressed_video_path.suffix
            final_video_path = videos_dir / f"{dataset_name}{video_suffix}"
            _gen_video_thumbnail(str(final_video_path), str(thumbnails_dir), force_update=update_videos)
            _logger.info("[page_sync] Generated thumbnail for %s", dataset_name)

            # 8. Update task status to COMPLETED
            _mark_task_completed(session, dataset_uuid)
            _logger.info("[page_sync] Successfully processed dataset: %s (%s)", dataset_name, dataset_uuid)

        except Exception as e:
            _logger.error("[page_sync] Error processing task %s: %s", dataset_uuid, e, exc_info=True)
            err_msg = f"Error processing page sync task for dataset_uuid={dataset_uuid}: {e}\n{traceback.format_exc()}"
            _mark_task_failed(session, dataset_uuid, err_msg)

    # 9. Generate consolidated datasets and data index files
    _logger.info("[page_sync] Generating consolidated metadata files...")
    try:
        consolidated_path = info_dir / "consolidated_datasets.json"
        _logger.debug("[page_sync] Generating consolidated datasets at: %s", consolidated_path)
        _gen_consolidation(str(dataset_info_dir), str(consolidated_path))

        data_index_path = info_dir / "data_index.json"
        _logger.debug("[page_sync] Generating data index at: %s", data_index_path)
        _gen_data_index(str(dataset_info_dir), str(data_index_path))

        _logger.debug("[page_sync] Copying robot aliases file into info directory")
        _copy_robot_aliases_and_exclude(str(info_dir))

        _logger.info("[page_sync] Successfully generated consolidated metadata files")
    except Exception as e:
        _logger.error("[page_sync] Error generating consolidated metadata files: %s", e, exc_info=True)

    _logger.info("[page_sync] Target file structure construction completed at: %s", target_dir)


def main(
    db_path: str,
    target_dir: str,
    crf: int = 18,
    update_videos: bool = False,
    force_regenerate: bool = False,
    log_level: str = "INFO",
) -> None:
    """
    Main entry point for page sync operation.

    Args:
        db_path: Path to the SQLite database
        target_dir: Root directory of the page project
        crf: CRF value for video compression (default: 18, range: 0-51, lower = better quality)
        update_videos: If True, always regenerate videos and thumbnails; if False, skip existing ones (default: False)
        force_regenerate: If True, ignore existing COMPLETED status and rebuild assets whenever prerequisites are ready
        log_level: Logging level (default: INFO)
    """
    from datetime import datetime

    from robocoin_dataset.database.database import DatasetDatabase

    # Setup logging to logs/page/ directory
    log_dir = Path("logs/page")
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"page_sync_{timestamp}.log"

    # Configure logging with both file and console handlers
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)
    logger.info("[page_sync] Log file created at: %s", log_file)

    # Initialize database
    db = DatasetDatabase(db_path)
    logger.info("[page_sync] Initialized database at: %s", db_path)

    # Run the sync operation
    with db.with_session() as session:
        construce_target_file(
            db=db,
            session=session,
            target_dir=target_dir,
            crf=crf,
            update_videos=update_videos,
            force_regenerate=force_regenerate,
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
        "--crf",
        type=int,
        default=18,
        help="CRF value for video compression (default: 18, range: 0-51, lower = better quality)",
    )
    parser.add_argument(
        "--update-videos",
        action="store_true",
        help="Force regenerate videos and thumbnails even if they exist (default: False)",
    )
    parser.add_argument(
        "--force-regenerate",
        action="store_true",
        help="Regenerate datasets even if their status already shows as COMPLETED",
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
        crf=args.crf,
        update_videos=args.update_videos,
        force_regenerate=args.force_regenerate,
        log_level=args.log_level,
    )
