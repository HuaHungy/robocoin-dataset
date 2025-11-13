import argparse
import asyncio
import logging
from pathlib import Path

from robocoin_dataset.quality_check.qced_repo_generator import QualityCheckedRepoGeneratorServer
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
        "--qc_config_path",
        type=str,
        default="",
        help="Path to the quality check config file",
    )
    parser.add_argument(
        "--state_data_score_threshold",
        type=float,
        default=0.85,
        help="State data score threshold",
    )
    parser.add_argument(
        "--action_data_score_threshold",
        type=float,
        default=0.85,
        help="Action data score threshold",
    )
    parser.add_argument(
        "--video_score_threshold",
        type=float,
        default=0.9,
        help="Video score threshold",
    )

    parser.add_argument("--ds_api_key", type=str, default="sk-a3c8736391cf43809957329f28cac287")

    args = parser.parse_args()
    db_file_path = Path(args.db_file_path).expanduser().absolute()

    if not db_file_path.exists():
        print(f"{db_file_path} does not exist")
        exit(1)

    logger = setup_logger(
        name="quality checked repo generator server",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )

    server = QualityCheckedRepoGeneratorServer(
        db_file_path=db_file_path,
        host=args.host,
        port=args.port,
        logger=logger,
        state_data_score_threshold=args.state_data_score_threshold,
        action_data_score_threshold=args.action_data_score_threshold,
        video_score_threshold=args.video_score_threshold,
        ds_api_key=args.ds_api_key,
    )

    await server.start()


if __name__ == "__main__":
    asyncio.run(main())

"""usage:
python scripts/quality_check/qced_repo_gen_server.py \
    --db_file_path ./db/datasets_new.db \
    --host 0.0.0.0 \
    --port 2110 \
    --log_dir ./logs/quality_checked_repo_generator_server 
"""
