import argparse
import asyncio
import logging
from pathlib import Path

from robocoin_dataset.quality_check.dataset_quality_check import (
    DatasetQualityCheckServer,
)
from robocoin_dataset.utils.logger import setup_logger


async def main() -> None:
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
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to run the server",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8768,
        help="Port to run the server",
    )
    parser.add_argument(
        "--qc_config_path",
        type=str,
        default="",
        help="Path to the quality check config file",
    )

    parser.add_argument(
        "--target_dataset_uuid",
        type=str,
        default=None,
        help="Specify the target dataset UUID for testing (optional)"
    )

    args = parser.parse_args()
    db_file_path = Path(args.db_file_path).expanduser().absolute()

    if not db_file_path.exists():
        print(f"{db_file_path} does not exist")
        exit(1)

    logger = setup_logger(
        name="quality check server",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )

    checker = DatasetQualityCheckServer(
        db_file_path=db_file_path,
        host=args.host,
        port=args.port,
        logger=logger,
        qc_config_path=args.qc_config_path,
        target_dataset_uuid=args.target_dataset_uuid
    )

    await checker.start()


if __name__ == "__main__":
    asyncio.run(main())

"""usage:
python scripts/quality_check/quality_check_server.py \
    --db_file_path ./db/datasets_new.db \
    --host 0.0.0.0 \
    --port 2100\
    --log_dir ./logs/quality_check_server/ \
    --qc_config_path scripts/quality_check/configs/device_version_checker_config.yaml
"""
