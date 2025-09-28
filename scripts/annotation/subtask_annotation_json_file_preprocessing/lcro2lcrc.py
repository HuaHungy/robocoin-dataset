import argparse
import json
import logging
import traceback
from pathlib import Path

from robocoin_dataset.annotation.subtask_annotion.subtask_annotation_process import (
    lcro2lcrc,
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

    argparser.add_argument(
        "--target_json_dir",
        type=str,
        default="",
        help="Path to save json file.",
    )

    args = argparser.parse_args()

    logger = setup_logger(
        name="lcro2lcrc",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )

    target_json_dir = Path(args.target_json_dir).expanduser().absolute()
    target_json_dir.mkdir(parents=True, exist_ok=True)
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
                                for error in errors:
                                    if error:
                                        logger.error(f"File {file} 检验失败: {error}")
                                continue

                            try:
                                new_file_name = file.stem + "_lcrc" + file.suffix
                                new_file_path = target_json_dir / new_file_name
                                new_data = lcro2lcrc(data)
                                with open(new_file_path, "w") as new_f:
                                    json.dump(new_data, new_f, indent=4)

                                logger.info(f"已处理 {file}，保存到 {new_file_path}")

                            except Exception as e:
                                logger.error(f"❌ {file} : {e}")
                                continue

                        except Exception as e:
                            logger.error(f"{file} 检验失败: {e}")
                            print(traceback.format_exc())

                except Exception as e:
                    logger.error(f"处理标注文件 {file} 失败: {e}")
                    print(traceback.format_exc())

    except Exception:
        print(traceback.format_exc())

    """usage:
    # 功能：
    # 1. 将左闭右开（最后一段为左闭右闭）转换为左闭右闭形式 
python scripts/annotation/lcro2lcrc.py --json_dir ~/Downloads/json_label_files_range --target_json_dir ~/Downloads/json_label_files_range_lcrc --log_dir ./outputs/logs 
    """
