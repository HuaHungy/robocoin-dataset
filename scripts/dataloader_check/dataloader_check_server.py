import argparse
import asyncio
import logging
from pathlib import Path

from robocoin_dataset.dataloader_check.dataloader_checker import DataLoaderCheckerServer
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
        "--num_workers",
        type=int,
        default=8,
        help="",
    )

    parser.add_argument(
        "--sample_rate",
        type=float,
        default=0.1,
        help="",
    )

    args = parser.parse_args()
    db_file_path = Path(args.db_file_path).expanduser().absolute()

    if not db_file_path.exists():
        print(f"{db_file_path} does not exist")
        exit(1)

    logger = setup_logger(
        name="dataloader check server",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )

    checker = DataLoaderCheckerServer(
        db_file_path=db_file_path,
        host=args.host,
        port=args.port,
        logger=logger,
        num_workers=args.num_workers,
        sample_rate=args.sample_rate,
    )

    await checker.start()


if __name__ == "__main__":
    asyncio.run(main())

"""usage:
python scripts/dataloader_check/dataloader_check_server.py \
    --db_file_path ./db/datasets_new.db \
    --host 0.0.0.0 \
    --port 2120\
    --log_dir ./logs/dataloader_check_server/ \
    --num_workers 8 \
    --sample_rate 0.1
"""
