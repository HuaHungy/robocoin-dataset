import argparse
import asyncio
import logging
from pathlib import Path

from robocoin_dataset.dataloader.dataloader import DataloaderDbClient
from robocoin_dataset.utils.logger import setup_logger


async def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="server host to connect to.",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8771,
        help="server port to connect to.",
    )
    parser.add_argument(
        "--log_dir",
        type=str,
        default="",
        help="Path to the log directory",
    )

    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=10.0,
        help="Heartbeat interval for each client.",
    )

    args = parser.parse_args()
    logger = setup_logger(
        name="dataloader client",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )

    server_uri = f"ws://{args.host}:{args.port}"
    dataloader_client = DataloaderDbClient(
        server_uri=server_uri, logger=logger, heartbeat_interval=args.heartbeat_interval
    )
    await dataloader_client.run()


if __name__ == "__main__":
    asyncio.run(main())

"""usage:
python scripts/dataloader/dataloader_client.py \
    --host=127.0.0.1 \
    --port=8771 \
    --heartbeat-interval=10.0 \
    --log_dir ./logs/dataloader
"""
