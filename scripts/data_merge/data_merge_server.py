import argparse
import asyncio
import logging
from pathlib import Path

from robocoin_dataset.data_merge.data_merger import DataMergerServer
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

    args = parser.parse_args()
    db_file_path = Path(args.db_file_path).expanduser().absolute()

    if not db_file_path.exists():
        print(f"{db_file_path} does not exist")
        exit(1)

    logger = setup_logger(
        name="data merger server",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )

    data_merger = DataMergerServer(
        db_file_path=db_file_path,
        host=args.host,
        port=args.port,
        logger=logger,
    )

    await data_merger.start()


if __name__ == "__main__":
    asyncio.run(main())

"""usage:
python scripts/data_merge/data_merge_server.py \
    --db_file_path ./db/datasets_new.db \
    --host 0.0.0.0 \
    --port 2090 \
    --log_dir ./logs/data_merge_server
"""
