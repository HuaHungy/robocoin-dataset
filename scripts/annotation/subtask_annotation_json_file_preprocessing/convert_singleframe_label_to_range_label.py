import argparse
import json
import logging
import traceback
from pathlib import Path

from robocoin_dataset.annotation.subtask_annotion.subtask_annotation_process import (
    embed_episodes_ranges,
    is_frame_annotation_json,
    process_singleframe_label,
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
        name="convert_singleframe_label_to_range_label",
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
                                new_file_name = file.stem + "_range_labelled" + file.suffix
                                new_file_path = target_json_dir / new_file_name
                                if is_frame_annotation_json(data):
                                    new_ranges = process_singleframe_label(data)
                                    new_data = embed_episodes_ranges(data, new_ranges)
                                else:
                                    new_data = data
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
    # 1. 格式检查
python scripts/annotation/convert_singleframe_label_to_range_label.py --json_dir ~/Downloads/json_label_files --target_json_dir ~/Downloads/json_label_files_range --log_dir ./outputs/logs 
    """
