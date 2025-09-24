import argparse
import json
import logging
import sys
import traceback
from datetime import datetime
from logging.handlers import RotatingFileHandler  # 可选：轮转
from pathlib import Path


def setup_logger(
    name: str,
    log_dir: Path,
    level=logging.INFO,  # noqa: ANN001
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    fmt: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt: str = "%Y-%m-%d %H:%M:%S",
) -> logging.Logger:
    """
    创建一个同时输出到文件（带时间戳）和控制台的日志记录器
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        # 已配置，避免重复
        return logger

    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(fmt=fmt, datefmt=datefmt)

    # 创建日志文件路径
    log_dir = Path(log_dir)
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"Unable to mkdir log dir {log_dir}: {e}", file=sys.stderr)
        # 降级：只输出到控制台
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        return logger

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_filepath = log_dir / f"{name}_{timestamp}.log"

    # 文件处理器（带轮转）
    file_handler = RotatingFileHandler(
        log_filepath, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    # 添加处理器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger.info(f"The log system has been started, log file: {log_filepath.resolve()}")

    return logger


def validate_annotation_json(data: str | list) -> None:
    """
    验证标注 JSON 数据是否满足以下条件：
    1. 所有 ranges 覆盖从 1 开始的所有帧，无空缺
    2. 每个 videoLabel 的 ranges 只有一个 {start, end}
    3. 每个 videoLabel 的 timelinelabels 只有一个标签

    Args:
        data: JSON 字符串 或 已加载的 Python 对象（list of dicts）

    Returns:
        True if valid, raises AssertionError otherwise
    """
    if isinstance(data, str):
        data = json.loads(data)

    if not isinstance(data, list):
        raise ValueError("JSON 根节点必须是一个数组")

    for idx, item in enumerate(data):
        video_labels = item.get("videoLabels", [])
        if not isinstance(video_labels, list):
            raise AssertionError(f"第 {idx + 1} 个条目的 videoLabels 必须是数组")

        if len(video_labels) == 0:
            raise AssertionError(f"第 {idx + 1} 个条目的 videoLabels 不能为空")

        ranges = []
        for lbl_idx, label in enumerate(video_labels):
            # 验证 ranges 长度为 1
            if not isinstance(label.get("ranges"), list) or len(label["ranges"]) != 1:
                raise AssertionError(
                    f"第 {idx + 1} 个条目, videoLabel #{lbl_idx + 1}: "
                    f"ranges 必须是一个包含一个元素的数组"
                )

            r = label["ranges"][0]
            if not isinstance(r, dict) or "start" not in r or "end" not in r:
                raise AssertionError(
                    f"第 {idx + 1} 个条目, videoLabel #{lbl_idx + 1}: "
                    f"range 必须是 {{'start': ..., 'end': ...}} 格式"
                )

            start, end = r["start"], r["end"]
            if not isinstance(start, int) or not isinstance(end, int):
                raise AssertionError(
                    f"第 {idx + 1} 个条目, videoLabel #{lbl_idx + 1}: start 和 end 必须是整数"
                )
            if start < 1 or end < start:
                raise AssertionError(
                    f"第 {idx + 1} 个条目, videoLabel #{lbl_idx + 1}: start >= 1 且 end > start"
                )

            ranges.append((start, end))

            # 验证 timelinelabels 长度为 1
            timeline_labels = label.get("timelinelabels")
            if not isinstance(timeline_labels, list) or len(timeline_labels) != 1:
                raise AssertionError(
                    f"第 {idx + 1} 个条目, videoLabel #{lbl_idx + 1}: "
                    f"timelinelabels 必须是一个包含一个字符串的数组"
                )
            if not isinstance(timeline_labels[0], str):
                raise AssertionError(
                    f"第 {idx + 1} 个条目, videoLabel #{lbl_idx + 1}: "
                    f"timelinelabels[0] 必须是字符串"
                )

        # 验证 range 覆盖连续帧（从 1 开始，无空缺）
        validate_coverage(ranges, item_id=item.get("id"), entry_idx=idx + 1)


def validate_coverage(
    ranges: list[tuple[int, int]], item_id: int = None, entry_idx: int = 1
) -> None:
    """
    验证一组 (start, end) 区间是否覆盖从 1 开始的所有帧，无空缺。
    允许重叠。
    """
    if not ranges:
        raise AssertionError("ranges 不能为空")

    # 按 start 排序
    sorted_ranges = sorted(ranges, key=lambda x: x[0])

    current_end = 1  # 当前覆盖到的帧（开区间）

    for start, end in sorted_ranges:
        if start < 1:
            raise AssertionError(f"第 {entry_idx} 个条目 (id={item_id}): start 帧不能小于 1")

        if start > current_end:
            raise AssertionError(
                f"第 {entry_idx} 个条目 (id={item_id}): "
                f"帧 [{current_end}, {start}) 未被覆盖，存在空缺"
            )

        current_end = max(current_end, end)  # 合并区间

    if current_end <= 1:
        raise AssertionError(f"第 {entry_idx} 个条目 (id={item_id}): 至少需要覆盖到帧 1")


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

    log = setup_logger(
        name="validate_label_json_files",
        log_dir=Path(args.log_dir),
        level=logging.ERROR,
    )

    json_dir = Path(args.json_dir)
    try:
        json_files = [
            file for file in json_dir.iterdir() if file.is_file() and file.suffix == ".json"
        ]
        for file in json_files:
            if file.is_file() and file.suffix == ".json":
                try:
                    with open(file) as f:
                        try:
                            data = json.load(f)
                            validate_annotation_json(data)
                        except Exception as e:
                            log.error(f"❌ {file} is not a valid annotation json: {e}")
                            continue

                        for episode in data:
                            video_url = episode["video"]
                            try:
                                ep_annotation = json.dumps(episode["videoLabels"])
                            except Exception as e:
                                raise Exception(f"Failed to dumpi videoLabels of {episode}") from e

                except Exception as e:
                    log.error(f"处理标注文件 {file} 失败: {e}")

    except Exception:
        print(traceback.format_exc())

    """usage:
    python scripts/annotation/validate_label_json_files.py \
        --json_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/files-to-process \
        --log_dir ./output/logs 
    """
