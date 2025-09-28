import json
import logging
import sys
from datetime import datetime
from itertools import groupby
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


def validate_and_get_label_json_data(data: str | list) -> tuple[list, list[str]]:
    errors = []
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            errors.append("JSON 格式错误")
            return [], errors

    if not isinstance(data, list):
        errors.append("JSON 根节点必须是一个数组")
        return [], errors

    for ep_idx in range(len(data)):
        item = data[ep_idx]

        if not isinstance(item, dict):
            errors.append(f"Episode item {ep_idx}: JSON 数组中的元素必须是字典")
            continue

        id = item.get("id", None)
        if id is None:
            errors.append(f"Invalid episode item {id}: id is None")
            continue

        ep_labels = item.get("videoLabels", None)
        if ep_labels is None:
            errors.append(f"Episode item {id}: videoLabels is None")
            continue

        if not ep_labels:
            errors.append(f"Episode item {id}: videoLabels is empty")
            continue

        for ranges_label_idx in range(len(ep_labels)):
            ranges_label = ep_labels[ranges_label_idx].get("ranges", None)
            if ranges_label is None:
                errors.append(f"Episode item {id}: videoLabels[{ranges_label_idx}]: ranges is None")
                continue

            if not isinstance(ranges_label, list):
                errors.append(
                    f"Episode item {id}: videoLabels[{ranges_label_idx}]: ranges is not a list"
                )
                continue

            if len(ranges_label) != 1:
                errors.append(
                    f"Episode item {id}: videoLabels[{ranges_label_idx}]: ranges must be a list of one element"
                )
                continue

            range_label = ranges_label[0]
            start = range_label.get("start", None)
            end = range_label.get("end", None)
            if start is None or end is None:
                errors.append(
                    f"Episode item {id}: videoLabels[{ranges_label_idx}]: ranges[{ranges_label_idx}]: start and end must be specified"
                )
                continue

            if end < start:
                errors.append(
                    f"Episode item {id}: videoLabels[{ranges_label_idx}]: ranges[{ranges_label_idx}]: end must be greater than start"
                )
                continue

            if start < 1:
                errors.append(
                    f"Episode item {id}: videoLabels[{ranges_label_idx}]: ranges[{ranges_label_idx}]: start must be greater than 0"
                )
                continue

            timeline_labels = ep_labels[ranges_label_idx].get("timelinelabels", None)
            if timeline_labels is None:
                errors.append(
                    f"Episode item {id}: videoLabels[{ranges_label_idx}]: timelinelabels is not found"
                )
                continue

            if not isinstance(timeline_labels, list):
                errors.append(
                    f"Episode item {id}: videoLabels[{ranges_label_idx}]: timelineLabels is not a list"
                )
                continue

            if len(timeline_labels) != len(ranges_label):
                errors.append(
                    f"Episode item {id}: videoLabels[{ranges_label_idx}]: "
                    f"timelineLabels length is not equal to ranges length"
                )
                continue

        for ep_label in ep_labels:
            ranges_label = ep_label.get("ranges", None)
            if ranges_label is None:
                errors.append(f"Episode item {id}: ranges is None")
                continue

    if errors:
        return [], errors
    return data, []


def is_frame_annotation_json(data: str | list) -> bool:
    data, _ = validate_and_get_label_json_data(data)
    flags = []

    for ep_item in data:
        labels = ep_item.get("videoLabels")
        ep_id = ep_item.get("id")
        max_end_frame_idx = -1
        for label in labels:
            ranges = label.get("ranges")
            end = ranges[0]["end"]
            if end > max_end_frame_idx:
                max_end_frame_idx = end
        for label in labels:
            ranges = label.get("ranges")
            start = ranges[0]["start"]
            end = ranges[0]["end"]
            if start == end:
                if end != max_end_frame_idx:
                    flags.append((True, ep_id))
            else:
                flags.append((False, ep_id))

    flags_set = set(flags)
    bool_set = set([flag[0] for flag in flags_set])
    if bool_set == {True}:
        return True
    if bool_set == {False}:
        return False
    true_ep_ids = [ep_id for flag, ep_id in flags if flag is True]
    false_ep_ids = [ep_id for flag, ep_id in flags if flag is False]

    if len(true_ep_ids) > len(false_ep_ids):
        err_msg = f"These episodes are labeled using start < end: {false_ep_ids}"
    else:
        err_msg = f"These episodes are labeled using start == end: {true_ep_ids}"

    raise ValueError(
        "The video subtask annotation contains inconsistent labels. "
        "Please check the label ranges and make sure they are consistent."
        f"{err_msg}"
    )


def extract_episodes_ranges(data: list) -> list[list[tuple[int, int]]]:
    result = []
    for ep_item in data:
        ep_result = []
        ep_labels = ep_item.get("videoLabels")
        for ranges in ep_labels:
            ranges = ranges.get("ranges")
            range0 = ranges[0]
            start = range0.get("start")
            end = range0.get("end")
            ep_result.append((start, end))
        result.append(ep_result)

    return result


def embed_episodes_ranges(data: list[dict], new_ranges: list[list[tuple[int, int]]]) -> list[dict]:
    """
    将新的区间列表注入到原始数据的每个 episode 的 videoLabels 中。

    Args:
        data: 原始 JSON 数据列表，每个元素是一个 episode 的标注
        new_ranges: 新的区间列表，格式为 [[(s1,e1), (s2,e2), ...], [...], ...]

    Returns:
        修改后的数据列表（深拷贝，不修改原数据）
    """
    import copy

    result = copy.deepcopy(data)  # 避免修改原数据
    if len(result) != len(new_ranges):
        raise AssertionError("数据长度不一致")

    for i, ep_item in enumerate(result):
        ep_new_ranges = new_ranges[i]
        ep_labels = ep_item.get("videoLabels", [])

        for range_item in ep_labels:
            # 获取目标 ranges 列表（通常只有一个 range）
            ranges_list = range_item.get("ranges")
            if not ranges_list or not isinstance(ranges_list, list):
                continue
            if len(ranges_list) == 0:
                continue

            # 更新第一个 range 的 start 和 end
            ranges_list[0]["start"] = ep_new_ranges[0][ranges_list[0]["end"]]

    return result


def process_singleframe_label(data: list) -> list:
    singleframe_ranges = extract_episodes_ranges(data)
    result = []
    for ep_item in singleframe_ranges:
        ep_result = []
        sorted_ranges = sorted(ep_item, key=lambda x: x[0])
        grouped = [list(group) for _, group in groupby(sorted_ranges, key=lambda x: x[0])]
        if not grouped:
            raise AssertionError("没有分组")

        # 处理第一个range
        end_start_ranges_dict = {}
        for idx in range(len(grouped)):
            if idx == 0:
                end_start_ranges_dict[grouped[idx][0][0]] = 1
            else:
                end_start_ranges_dict[grouped[idx][0][0]] = grouped[idx - 1][0][0]

            ep_result.append(end_start_ranges_dict)

        result.append(ep_result)

    return result


def validate_coverage(ranges: list[tuple[int, int]], start_frame_idx: int = 0) -> list[str]:
    """
    验证区间覆盖情况，返回 errors 和 warnings。

    规则：
    - 左闭右闭 [start, end]
    - 必须从帧 1 开始连续覆盖
    - 所有“端点相接”（r1.end == r2.start）视为“区域重叠”，产生 warning
    - 但如果相接涉及“最后一帧”，则不 warning
    """
    errors = []

    if not ranges:
        errors.append("ranges 不能为空")
        return errors
    valid_ranges = []
    for i, (start, end) in enumerate(ranges):
        if not isinstance(start, int) or not isinstance(end, int):
            errors.append(f"区间 #{i + 1} ({start}, {end}): start 和 end 必须是整数")
            continue
        if start < 1:
            errors.append(f"区间 #{i + 1} ({start}, {end}): start 帧不能小于 1")
        if end < start:
            errors.append(f"区间 #{i + 1} ({start}, {end}): end 不能小于 start")
            continue
        valid_ranges.append((start, end))

    if not valid_ranges:
        if not errors:
            errors.append("所有区间均无效")
            return errors

    # Step 2: 计算最大帧号（最后一帧）
    total_max_frame = max(end for _, end in valid_ranges)

    # Step 3: 检查覆盖连续性（左闭右闭）
    sorted_ranges = sorted(valid_ranges, key=lambda x: x[0])
    current_end = start_frame_idx - 1  # 当前连续覆盖到的最后一个帧

    for start, end in sorted_ranges:
        if start > current_end + 1:
            missing_start = current_end + 1
            missing_end = start - 1
            if missing_start == missing_end:
                gap_msg = f"帧 {missing_start}"
            else:
                gap_msg = f"帧 [{missing_start}, {missing_end}]"
            errors.append(f"存在空缺：{gap_msg} 未被覆盖")
        if end > current_end:
            current_end = end

    if current_end < 1:
        errors.append("至少需要覆盖到帧 1")

    # Step 4: 检查所有“端点相接”对（区域重叠）
    # 使用 set 避免重复添加 warning
    range_abut_pairs = set()

    for i, (s1, e1) in enumerate(valid_ranges):
        for j, (s2, e2) in enumerate(valid_ranges):
            if i >= j:  # 避免重复和自比
                continue
            # 判断是否“端点相接”
            if e1 == s2 or e2 == s1:
                # 检查是否涉及最后一帧
                if e1 == total_max_frame or e2 == total_max_frame:
                    continue  # 豁免
                # 添加 warning（避免重复）
                pair_key = tuple(sorted([(s1, e1), (s2, e2)]))  # 无序对
                if pair_key not in range_abut_pairs:
                    range_abut_pairs.add(pair_key)
                    errors.append(f"区间 ({s1},{e1}) 与 ({s2},{e2}) 存在端点相接（区域重叠）")

    return errors


def validate_annotation_item(item: dict, start_frame_idx: int = 0) -> str:
    video_labels = item.get("videoLabels", [])
    item_id = item.get("id")
    if not video_labels:
        return f"#{item_id} videoLabels 不能为空"

    if not video_labels:
        return f"#{item_id} videoLabels 不能为空"
    if not isinstance(video_labels, list):
        return f"#{item_id} videoLabels 必须是数组"

    if len(video_labels) == 0:
        return f"#{item_id} videoLabels 不能为空"

    ranges = []
    for lbl_idx, label in enumerate(video_labels):
        # 验证 ranges 长度为 1
        if not isinstance(label.get("ranges"), list) or len(label["ranges"]) != 1:
            return f"videoLabel #{item_id}-{lbl_idx + 1}: ranges 必须是一个包含一个元素的数组"

        r = label["ranges"][0]
        if not isinstance(r, dict) or "start" not in r or "end" not in r:
            return f"videoLabel #{item_id}-{lbl_idx + 1}: range 必须是 {{'start': ..., 'end': ...}} 格式"

        start, end = r["start"], r["end"]
        if not isinstance(start, int) or not isinstance(end, int):
            return f"videoLabel #{item_id}-{lbl_idx + 1}: start 和 end 必须是整数"
        if start < start_frame_idx or end < start:
            return f"videoLabel #{item_id}-{lbl_idx + 1}: start >= {start_frame_idx} 且 end > start"

        ranges.append((start, end))

        # 验证 timelinelabels 长度为 1
        timeline_labels = label.get("timelinelabels")
        if not isinstance(timeline_labels, list) or len(timeline_labels) != 1:
            return f"videoLabel #{item_id}-{lbl_idx + 1}: timelinelabels 必须是一个包含一个字符串的数组"
        if not isinstance(timeline_labels[0], str):
            return f"videoLabel #{item_id}-{lbl_idx + 1}: timelinelabels[0] 必须是字符串"

    # 验证 range 覆盖连续帧（从 start_frame 开始，无空缺）
    range_coverage_errors = validate_coverage(ranges, start_frame_idx=start_frame_idx)
    if range_coverage_errors:
        return f"videoLabel #{item_id}: {range_coverage_errors}"

    return ""


def validate_annotation_json(data: str | list, start_frame_idx: int = 0) -> list[str]:
    """
    验证标注 JSON 数据(左闭右闭)是否满足以下条件：
    1. 所有 ranges 覆盖从 1 开始的所有帧，无空缺
    2. 每个 videoLabel 的 ranges 只有一个 {start, end}
    3. 每个 videoLabel 的 timelinelabels 只有一个标签

    Args:
        data: JSON 字符串 或 已加载的 Python 对象（list of dicts）

    Returns:
        True if valid, raises AssertionError otherwise
    """
    errors = []
    if isinstance(data, str):
        data = json.loads(data)

    if not isinstance(data, list):
        errors.append("JSON 根节点必须是一个数组")
        return errors

    for item in data:
        try:
            errors.append(validate_annotation_item(item, start_frame_idx=start_frame_idx))
        except AssertionError as e:  # noqa: PERF203
            errors.append(f"Invalid item: {e}")
            continue

    return errors


def lcro2lcrc(data: list[dict]) -> list[dict]:
    import copy

    new_data = copy.deepcopy(data)  # 避免修改原数据
    for ep_item in new_data:
        labels = ep_item.get("videoLabels")
        max_end_frame_idx = -1
        for label in labels:
            ranges = label.get("ranges")
            end = ranges[0]["end"]
            if end > max_end_frame_idx:
                max_end_frame_idx = end
        for label in labels:
            ranges = label.get("ranges")
            end = ranges[0]["end"]
            if end != max_end_frame_idx:
                ranges[0]["end"] -= 1

    return new_data
