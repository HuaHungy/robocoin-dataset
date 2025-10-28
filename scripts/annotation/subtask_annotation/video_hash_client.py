import argparse
import asyncio
import logging
from pathlib import Path

from robocoin_dataset.annotation.subtask_annotion.video_hash import VideoHashClient
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
        default=8768,
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
        name="video hash client",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )

    server_uri = f"ws://{args.host}:{args.port}"
    processor_client = VideoHashClient(
        server_uri=server_uri, logger=logger, heartbeat_interval=args.heartbeat_interval
    )
    await processor_client.run()


if __name__ == "__main__":
    asyncio.run(main())

"""usage:
# realman_rmc_aidal
python scripts/annotation/subtask_annotation/video_hash_client.py \
    --host=127.0.0.1 \
    --port=8768 \
    --heartbeat-interval=10.0 \
    --log_dir ./logs/video_hash
"""
