import argparse
import json
import logging
import traceback
from pathlib import Path

from robocoin_dataset.annotation.subtask_annotion.subtask_annotation_process import (
    setup_logger,
    validate_and_get_label_json_data,
    validate_annotation_json,
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
        name="validate_coverage",
        log_dir=Path(args.log_dir),
        level=logging.INFO,
    )

    json_dir = Path(args.json_dir).expanduser().absolute()
    try:
        json_files = [
            file for file in json_dir.iterdir() if file.is_file() and file.suffix == ".json"
        ]
        logger.info(f"Found {len(json_files)} json files.")
        passed_files = []
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
                                errors = validate_annotation_json(data, start_frame_idx=1)
                                if errors:
                                    logger.error(f"Found {len(errors)} errors in {file}")
                                    for error in errors:
                                        if error:
                                            logger.error(f"File {file} 区域覆盖检验失败: {error}")
                                    continue
                                else:
                                    logger.info(f"✅ {file} passed.")

                            except Exception as e:
                                logger.error(f"❌ {file} : {e}")
                                continue

                        except Exception as e:
                            logger.error(f"{file} 检验失败: {e}")
                            print(traceback.format_exc())

                except Exception as e:
                    logger.error(f"处理标注文件 {file} 失败: {e}")
                    print(traceback.format_exc())

            passed_files.append(file)

        logger.info(f"✅ {len(passed_files)} json files passed.")
        impassed_files = [file for file in json_files if file not in passed_files]
        logger.info(f"✅ {len(impassed_files)} json files failed.")
        for file in impassed_files:
            logger.error(f"❌ {file}")

    except Exception:
        print(traceback.format_exc())

    """usage:
    # 功能：检测左闭右闭区间标注文件是否符合规范，包括如下项：
    1. 所有 ranges 覆盖从 1 开始的所有帧，无空缺
    2. 每个 videoLabel 的 ranges 只有一个 {start, end}
    3. 每个 videoLabel 的 timelinelabels 只有一个标签
python scripts/annotation/subtask_annotation_json_file_preprocessing/validate_coverage.py --json_dir ~/Downloads/json_label_files_range_lcrc --log_dir ./outputs/logs 
    """
