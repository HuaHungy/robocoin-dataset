import argparse
import asyncio
import logging
from pathlib import Path

from robocoin_dataset.utils.logger import setup_logger
from robocoin_dataset.visualize_dataset.visualize_dataset import DatasetVisualizerClient


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
        default=8766,
        help="server port to connect to.",
    )
    parser.add_argument(
        "--log_dir",
        type=str,
        default="",
        help="path to the log directory",
    )

    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=10.0,
        help="heartbeat interval for each client.",
    )

    args = parser.parse_args()
    logger = setup_logger(
        name="dataset_visualization_client",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )

    server_uri = f"ws://{args.host}:{args.port}"
    dataset_visualization_client = DatasetVisualizerClient(
        server_uri=server_uri, logger=logger, heartbeat_interval=args.heartbeat_interval
    )
    await dataset_visualization_client.run()


if __name__ == "__main__":
    asyncio.run(main())

"""usage:
# realman_rmc_aidal
python scripts/visualize_dataset/visualize_dataset_client.py \
    --host=127.0.0.1 \
    --port=2120\
    --heartbeat-interval=10.0 \
    --log_dir ./logs/dataset_visualization_client
"""
