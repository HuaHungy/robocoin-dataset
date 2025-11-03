import argparse
import asyncio
import logging
from pathlib import Path

from robocoin_dataset.annotation.motion_annotation.motion_annotation_data_post_process import (
    MotionAnnotationDataPostProcessServer,
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
        "--sim_replay_config_path",
        type=str,
        default="",
        help="Path to the factory config file",
    )

    parser.add_argument(
        "--device_model",
        type=str,
        default=None,
        help="Device model to sim replay",
    )

    parser.add_argument(
        "--device_model_version",
        type=str,
        default=None,
        help="Device model version to sim replay",
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
        default=8767,
        help="Port to run the server",
    )

    args = parser.parse_args()
    db_file_path = Path(args.db_file_path).expanduser().absolute()

    if not db_file_path.exists():
        print(f"{db_file_path} does not exist")
        exit(1)

    logger = setup_logger(
        name="video hash server",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )

    motion_annotation_server = MotionAnnotationDataPostProcessServer(
        db_file_path=db_file_path,
        sim_replay_config_path=args.sim_replay_config_path,
        host=args.host,
        port=args.port,
        heartbeat_interval=30.0,
        device_model=args.device_model,
        device_model_version=args.device_model_version,
        timeout=15.0,
        logger=logger,
    )

    await motion_annotation_server.start()


if __name__ == "__main__":
    asyncio.run(main())


"""Usage:

python scripts/annotation/motion_annotation/motion_annotation_server.py \
    --db_file_path ./db/datasets_new.db \
    --host 0.0.0.0 \
    --port 8766 \
    --sim_replay_config_path ./scripts/sim_replay/configs/sim_replay_config_path.yaml \
    --device_model realman_rmc_aidal \
    --device_model_version default_version \
    --log_dir ./logs/
"""
