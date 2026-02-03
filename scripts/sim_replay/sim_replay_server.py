import argparse
import asyncio
import logging
from pathlib import Path

from robocoin_dataset.sim_replay.sim_replay import SimReplayServer
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

    # 新增：指定单个数据集UUID的参数
    parser.add_argument(
        "--target_dataset_uuid",
        type=str,
        default=None,
        help="Specify a single dataset UUID to process (priority over device_model/version)",
    )

    args = parser.parse_args()
    db_file_path = Path(args.db_file_path).expanduser().absolute()
    sim_replay_config_path = Path(args.sim_replay_config_path).expanduser().absolute()
    device_model = args.device_model
    device_model_version = args.device_model_version
    target_dataset_uuid = args.target_dataset_uuid  # 新增

    if not db_file_path.exists():
        print(f"{db_file_path} does not exist")
        exit(1)

    logger = setup_logger(
        name="sim_replay_server",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )

    sim_replay_server = SimReplayServer(
        db_file_path=db_file_path,
        sim_replay_config_path=sim_replay_config_path,
        host=args.host,
        port=args.port,
        heartbeat_interval=30.0,
        device_model=device_model,
        device_model_version=device_model_version,
        target_dataset_uuid=target_dataset_uuid,  # 新增
        timeout=15.0,
        logger=logger,
    )

    await sim_replay_server.start()


if __name__ == "__main__":
    asyncio.run(main())

"""usage:
# realman_rmc_aidal
python scripts/sim_replay/sim_replay_server.py \
    --db_file_path ./db/datasets_new.db \
    --host 0.0.0.0 \
    --port 8766 \
    --sim_replay_config_path ./scripts/sim_replay/configs/sim_replay_config_path.yaml \
    --device_model realman_rmc_aidal \
    --device_model_version default_version \
    --log_dir ./logs/

# 指定单个UUID处理（新增用法）
python scripts/sim_replay/sim_replay_server.py \
    --db_file_path ./db/datasets_new.db \
    --host=0.0.0.0 \
    --port=8767 \
    --sim_replay_config_path ./scripts/sim_replay/configs/sim_replay_config_path.yaml \
    --log_dir ./logs/sim_replay \
    --target_dataset_uuid b667a677-66fb-41a7-b039-06c2f57d4681
"""