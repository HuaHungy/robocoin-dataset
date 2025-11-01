import argparse
import asyncio
import logging
from pathlib import Path

from robocoin_dataset.dataloader.dataloader import DataloaderDbServer
from robocoin_dataset.utils.logger import setup_logger


async def main() -> None:
    parser = argparse.ArgumentParser()

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
        default=8771,
        help="Port to run the server",
    )

    parser.add_argument(
        "--db",
        type=str,
        default="",
        help="Path to SQLite DB file (defaults to built-in example if empty)",
    )

    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=30.0,
        help="Heartbeat interval (seconds)",
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Heartbeat timeout (seconds)",
    )

    args = parser.parse_args()

    logger = setup_logger(
        name="dataloader server",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )

    dataloader_server = DataloaderDbServer(
        db_file_path=Path(args.db) if args.db else None,
        host=args.host,
        port=args.port,
        heartbeat_interval=args.heartbeat_interval,
        timeout=args.timeout,
        logger=logger,
    )

    await dataloader_server.start()


if __name__ == "__main__":
    asyncio.run(main())

"""usage:
python scripts/dataloader/dataloader_server.py \
    --host 0.0.0.0 \
    --port 8771 \
    --db examples/dataloader_test/datasets_new.db \
    --heartbeat-interval 30.0 \
    --timeout 15.0 \
    --log_dir ./logs/dataloader
"""
