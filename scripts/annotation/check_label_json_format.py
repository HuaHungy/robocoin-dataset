import argparse
import json
import logging
import traceback
from pathlib import Path

from ...src.robocoin_dataset.annotation.subtask_annotion.subtask_annotation_process import (
    setup_logger,
    validate_and_get_label_json_data,
)

if __name__ == "__main__":
    argparser = argparse.ArgumentParser()

    argparser.add_argument(
        "--json_dir",
        type=str,
        default="",
        help="json dir",
    )

    argparser.add_argument(
        "--log_dir",
        type=str,
        default="outputs/logs/",
        help="Path to log file.",
    )

    args = argparser.parse_args()

    logger = setup_logger(
        name="check_label_json_format",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )

    json_dir = Path(args.json_dir).expanduser().absolute()
    try:
        json_files = [
            file for file in json_dir.iterdir() if file.is_file() and file.suffix == ".json"
        ]
        logger.info(f"Found {len(json_files)} json files.")
        for file in json_files:
            if file.is_file() and file.suffix == ".json":
                try:
                    with open(file) as f:
                        try:
                            data = json.load(f)
                            data, errors = validate_and_get_label_json_data(data)
                            if errors:
                                logger.error(f"❌ {file} 格式检验失败: {errors}")
                            else:
                                logger.info(f"✅ {file} 格式检验成功")
                        except Exception as e:
                            logger.error(f"{file} 格式检验失败: {e}")
                            print(traceback.format_exc())

                except Exception as e:
                    logger.error(f"{file} 格式检验失败: {e}")
                    print(traceback.format_exc())

    except Exception:
        print(traceback.format_exc())

    """usage:

    python scripts/annotation/check_label_json_format.py --json_dir ~/Downloads/json_annotation_test --log_dir ./outputs/logs 
    """
