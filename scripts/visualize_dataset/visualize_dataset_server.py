import argparse
import asyncio
import logging
from pathlib import Path

from robocoin_dataset.utils.logger import setup_logger
from robocoin_dataset.visualize_dataset.visualize_dataset import DatasetVisualizerServer


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
    parser.add_argument("--device_model", type=str, default="")
    
    # ========== 新增：target_dataset_uuid 参数 ==========
    parser.add_argument(
        "--target_dataset_uuid",
        type=str,
        default="",
        help="Specify a single dataset UUID to process (optional)",
    )

    args = parser.parse_args()
    db_file_path = Path(args.db_file_path).expanduser().absolute()

    if not db_file_path.exists():
        print(f"{db_file_path} does not exist")
        exit(1)

    logger = setup_logger(
        name="dataset visualizer server",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )

    # ========== 传递 target_dataset_uuid 到服务端 ==========
    visualizer_server = DatasetVisualizerServer(
        db_file_path=db_file_path,
        host=args.host,
        port=args.port,
        device_model=args.device_model,
        target_dataset_uuid=args.target_dataset_uuid,  # 新增参数
        logger=logger,
    )

    await visualizer_server.start()


if __name__ == "__main__":
    asyncio.run(main())

"""usage:
python scripts/visualize_dataset/visualize_dataset_server.py \
    --db_file_path /mnt/db/datasets_new.db \
    --host 0.0.0.0 \
    --port 2122 \
    --device_model realman_rmc_aidal \
    --log_dir ./logs/visualize_dataset_server \
    --target_dataset_uuid b667a677-66fb-41a7-b039-06c2f57d4681  # 新增示例
"""
