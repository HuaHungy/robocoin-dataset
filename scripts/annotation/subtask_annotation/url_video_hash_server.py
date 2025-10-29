import argparse
import asyncio
import logging
from pathlib import Path

from robocoin_dataset.annotation.subtask_annotion.url_video_hash import UrlVideoHashServer
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
        "--batch_size",
        type=int,
        default=100,
        help="url video hash bash size",
    )

    args = parser.parse_args()
    db_file_path = Path(args.db_file_path).expanduser().absolute()

    if not db_file_path.exists():
        print(f"{db_file_path} does not exist")
        exit(1)

    logger = setup_logger(
        name="url_video_hash_server",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )

    url_video_hash_server = UrlVideoHashServer(
        db_file_path=db_file_path,
        host=args.host,
        port=args.port,
        batch_size=args.batch_size,
        logger=logger,
    )

    await url_video_hash_server.start()


if __name__ == "__main__":
    asyncio.run(main())

"""usage:
# realman_rmc_aidal
python scripts/annotation/subtask_annotation/url_video_hash_server.py \
    --db_file_path ./db/datasets_new.db \
    --host 0.0.0.0 \
    --port 8769 \
    --batch_size 100 \
    --log_dir ./logs/url_video_hash_server
"""
