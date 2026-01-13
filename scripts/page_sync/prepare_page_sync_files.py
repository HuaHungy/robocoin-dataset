#!/usr/bin/env python3
"""
Page Sync Files Preparation Script - CLI Entry Point

本脚本是进行网页同步所需的素材文件生成的CLI入口脚本。

主要功能：
1. 从数据库中读取待同步的数据集信息
2. 生成统一的元数据 YAML 文件（assets/dataset_info/*.yml）
3. 从数据集中采样并压缩视频文件（assets/videos/*.mp4）
4. 生成视频缩略图（assets/thumbnails/*.jpg）
5. 生成汇总的元数据文件（assets/info/consolidated_datasets.json, data_index.json）
6. 可选：将生成的资源上传到 HuggingFace Hub

设计说明：
- 脚本的实际功能都在 page_sync (src/robocoin_dataset/page_sync/) 中实现
- 支持增量同步：只处理状态为 PENDING 的数据集
- 支持强制重新生成：使用 --force-regenerate 可以忽略 COMPLETED 状态
- 对缺失的 YAML 文件保持容错：会记录到 docs/missing_yaml_page.txt，但不中断处理

使用示例：
    # 基本用法
    python scripts/page_sync/prepare_page_sync_files.py \
      --db-path /mnt/db/datasets_new.db \
      --target-dir /home/rogerspyke/projects \
      --log-level INFO \
      --crf 30

    # 强制重新生成视频和缩略图
    python scripts/page_sync/prepare_page_sync_files.py \
      --db-path /mnt/db/datasets_new.db \
      --target-dir /home/rogerspyke/projects \
      --update-videos \
      --crf 30

    # 带 HuggingFace 上传
    python scripts/page_sync/prepare_page_sync_files.py \
      --db-path /mnt/db/datasets_new.db \
      --target-dir /home/rogerspyke/projects \
      --hf-token your_hf_token \
      --hf-repo-id RogersPyke/RoboCOIN_DataManager_assets \
      --crf 30 \
      --force-regenerate

参数说明：
    --update-videos: 强制重新生成视频和缩略图（即使已存在）
    --crf: 视频压缩质量控制参数（范围 0-51，越小质量越好）
           默认 30 可以得到平均约 500KB 的视频文件
    --force-regenerate: 忽略 COMPLETED 状态，强制重新生成所有资源
"""

import argparse
import logging
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Maximum retry times for HuggingFace upload on timeout errors
MAX_RETRY_TIMES = 3


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync dataset information to page project - construct assets (YAML files and videos)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with required arguments
  python scripts/page_sync/prepare_page_sync_files.py \\
    --db-path db/datasets_new.db \\
    --target-dir /path/to/page-project

  # With debug logging
  python scripts/page_sync/prepare_page_sync_files.py \\
    --db-path db/datasets_new.db \\
    --target-dir /path/to/page-project \\
    --log-level DEBUG

  # Force regenerate videos and thumbnails
  python scripts/page_sync/prepare_page_sync_files.py \\
    --db-path db/datasets_new.db \\
    --target-dir /path/to/page-project \\
    --update-videos

  # With custom CRF value for video compression
  python scripts/page_sync/prepare_page_sync_files.py \\
    --db-path db/datasets_new.db \\
    --target-dir /path/to/page-project \\
    --crf 23

  # With HuggingFace upload
  python scripts/page_sync/prepare_page_sync_files.py \\
    --db-path db/datasets_new.db \\
    --target-dir /path/to/page-project \\
    --hf-token your_hf_token \\
    --hf-repo-id RogersPyke/RoboCOIN-DataManager-assets

Output Structure:
  target-dir/
    assets/
      dataset_info/
        {dataset_name}.yml
        ...
      videos/
        {dataset_name}.mp4
        ...
        """,
    )

    parser.add_argument(
        "--db-path",
        type=str,
        required=True,
        help="Path to the SQLite database file (e.g., db/datasets_new.db)",
    )

    parser.add_argument(
        "--target-dir",
        type=str,
        required=True,
        help="Root directory of the page project where assets will be created",
    )

    parser.add_argument(
        "--crf",
        type=int,
        default=23,
        help="CRF value for video compression (default: 18, range: 0-51, lower = better quality)",
    )

    parser.add_argument(
        "--update-videos",
        action="store_true",
        help="Force regenerate videos and thumbnails even if they exist (default: False)",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )

    parser.add_argument(
        "--force-regenerate",
        action="store_true",
        help="Regenerate page sync files even if the dataset already shows as COMPLETED",
    )

    parser.add_argument(
        "--hf-token",
        type=str,
        default=None,
        help="HuggingFace token for uploading assets (optional). If not provided, upload will be skipped.",
    )

    parser.add_argument(
        "--hf-repo-id",
        type=str,
        default=None,
        help="HuggingFace repository ID for uploading assets (optional). If not provided, upload will be skipped.",
    )

    args = parser.parse_args()

    # 配置基本 logging，这样在进入 page_sync_main 之前就能看到日志
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    # Validate paths
    db_path = Path(args.db_path)
    if not db_path.exists():
        logger.error("[prepare_page_sync_files] Database file not found: %s", args.db_path)
        sys.exit(1)

    target_dir = Path(args.target_dir)
    if not target_dir.exists():
        logger.error("[prepare_page_sync_files] Target directory not found: %s", args.target_dir)
        logger.error("[prepare_page_sync_files] Please create the directory first or check the path.")
        sys.exit(1)

    # Import and run the main function
    from robocoin_dataset.page_sync.page_sync import main as page_sync_main

    logger.info("[prepare_page_sync_files] Starting page sync operation...")
    logger.info("[prepare_page_sync_files]   Database: %s", args.db_path)
    logger.info("[prepare_page_sync_files]   Target: %s", args.target_dir)
    logger.info("[prepare_page_sync_files]   CRF: %s", args.crf)
    logger.info("[prepare_page_sync_files]   Update videos: %s", args.update_videos)
    logger.info("[prepare_page_sync_files]   Log level: %s", args.log_level)

    try:
        page_sync_main(
            db_path=str(db_path.absolute()),
            target_dir=str(target_dir.absolute()),
            crf=args.crf,
            update_videos=args.update_videos,
            log_level=args.log_level,
        force_regenerate=args.force_regenerate,
        )
        logger.info("[prepare_page_sync_files] ✓ Page sync completed successfully!")

        # Optional HuggingFace upload
        if args.hf_token and args.hf_repo_id:
            logger.info("[prepare_page_sync_files] Starting HuggingFace upload...")
            from robocoin_dataset.page_sync.upload_assets_utils import sync_assets_to_hf

            assets_dir = target_dir / "assets"

            # Retry logic for timeout and network errors
            last_exception = None
            upload_success = False
            for attempt in range(1, MAX_RETRY_TIMES + 1):
                try:
                    commit_sha = sync_assets_to_hf(
                        assets_dir=str(assets_dir),
                        repo_id=args.hf_repo_id,
                        token=args.hf_token,
                    )
                    logger.info("[prepare_page_sync_files] ✓ HuggingFace upload completed successfully! Commit SHA: %s", commit_sha)
                    upload_success = True
                    break  # Success, exit retry loop
                except Exception as e:
                    last_exception = e
                    # Check if it's a timeout or network-related error
                    is_timeout_or_network_error = False
                    error_str = str(e).lower()

                    # Check for timeout-related keywords
                    if any(keyword in error_str for keyword in ['timeout', 'timed out', 'connection', 'network', 'socket']):
                        is_timeout_or_network_error = True

                    # Check for specific exception types
                    exception_type = type(e).__name__
                    if any(keyword in exception_type.lower() for keyword in ['timeout', 'connection', 'network']):
                        is_timeout_or_network_error = True

                    # Check for HTTP errors that might indicate timeout (504, 408, etc.)
                    if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
                        if e.response.status_code in [408, 504, 503]:
                            is_timeout_or_network_error = True

                    if is_timeout_or_network_error and attempt < MAX_RETRY_TIMES:
                        wait_time = attempt * 2  # Exponential backoff: 2s, 4s, 6s
                        logger.warning(
                            "[prepare_page_sync_files] ⚠ Upload attempt %d/%d failed due to timeout/network error: %s. Retrying in %d seconds...",
                            attempt, MAX_RETRY_TIMES, e, wait_time
                        )
                        time.sleep(wait_time)
                    else:
                        # Not a timeout/network error, or max retries reached
                        if attempt >= MAX_RETRY_TIMES:
                            logger.error(
                                "[prepare_page_sync_files] ✗ HuggingFace upload failed after %d attempts. Last error: %s",
                                MAX_RETRY_TIMES, e
                            )
                        else:
                            logger.error("[prepare_page_sync_files] ✗ Error during HuggingFace upload: %s", e)
                        raise

            # If upload failed after all retries, raise the last exception
            if not upload_success and last_exception is not None:
                raise last_exception
        elif args.hf_token or args.hf_repo_id:
            logger.warning("[prepare_page_sync_files] ⚠ WARNING: Both --hf-token and --hf-repo-id must be provided for HuggingFace upload. Skipping upload.")
        else:
            logger.info("[prepare_page_sync_files] ℹ HuggingFace upload skipped (no token/repo-id provided)")

    except KeyboardInterrupt:
        logger.error("[prepare_page_sync_files] ✗ Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.error("[prepare_page_sync_files] ✗ Error during page sync: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
