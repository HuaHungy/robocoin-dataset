import argparse
import json
import logging
import re
import shutil
from logging import Logger
from pathlib import Path

import tqdm

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import StAnnotationVideoDB, TaskStatus, UrlVideoStAnnotationDB
from robocoin_dataset.utils.logger import setup_logger


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
            error = validate_annotation_item(item, start_frame_idx=start_frame_idx)
            if error:
                errors.append(error)
        except AssertionError as e:  # noqa: PERF203
            errors.append(f"Invalid item: {e}")
            continue

    return errors


def enter_url_video_st_annotation_json_files(
    db_file_path: str | Path,
    json_src_dir: str | Path,
    passed_json_dst_dir: str | Path,
    impassed_json_dst_dir: str | Path,
    download_dir: str | Path,
    logger: Logger = None,
) -> None:
    db_file_path: Path = Path(db_file_path).expanduser().absolute()
    source_dir = Path(json_src_dir).expanduser().absolute()

    passed_json_dst_dir: Path = Path(passed_json_dst_dir).expanduser().absolute()
    passed_json_dst_dir.mkdir(parents=True, exist_ok=True)

    impassed_json_dst_dir: Path = Path(impassed_json_dst_dir).expanduser().absolute()
    impassed_json_dst_dir.mkdir(parents=True, exist_ok=True)

    download_dir = Path(download_dir).expanduser().absolute()
    download_dir.mkdir(parents=True, exist_ok=True)

    db = DatasetDatabase(db_file_path)
    json_files = [
        file for file in source_dir.iterdir() if file.is_file() and file.suffix == ".json"
    ]
    for file in tqdm.tqdm(json_files, desc="Processing Subtask Annotation JSON files", unit="file"):
        if file.is_file() and file.suffix == ".json":
            try:
                success = True
                with open(file) as f:
                    try:
                        data = json.load(f)
                        # errors = validate_annotation_json(data, start_frame_idx=1)
                        # if errors:
                        #     for error in errors:
                        #         if error:
                        #             logger.error(f"File {file} 检验失败: {error}")
                        #             success = False

                        # else:
                        success = True

                    except Exception as e:
                        logger.error(f"❌ {file} is not a valid annotation json: {e}")
                        success = False

                    if success:
                        with db.with_session() as session:
                            for episode in data:
                                pattern = r"^observation\.images\.(.+)$"
                                video_url = episode.get("video", None)
                                if video_url is None:
                                    for key in episode.keys():
                                        match = re.match(pattern, key)
                                        if match:
                                            video_url = episode.get(key, None)
                                            if video_url is None:
                                                raise ValueError(
                                                    f"{file} 中没有找到视频链接，请检查"
                                                )
                                            break

                                item = (
                                    session.query(StAnnotationVideoDB)
                                    .filter(StAnnotationVideoDB.video_url == video_url)
                                    .first()
                                )
                                if not item:
                                    video_item: StAnnotationVideoDB = StAnnotationVideoDB(
                                        video_url=video_url,
                                        download_status=TaskStatus.PENDING,
                                        video_hash_status=TaskStatus.PENDING,
                                    )
                                    session.add(video_item)
                                    session.flush()
                                    video_item.local_video_path = str(
                                        download_dir / f"{video_item.id}.{video_url.split('.')[-1]}"
                                    )
                                    video_item_id = video_item.id
                                else:
                                    video_item_id = item.id

                                session.query(UrlVideoStAnnotationDB).filter(
                                    UrlVideoStAnnotationDB.video_id == video_item_id
                                ).delete(synchronize_session=False)

                                for range_annotation in episode["videoLabels"]:
                                    # 数据库中的帧索引从0开始, 并且使用左闭右开的区间表达
                                    # 原始标注文件使用了从1开始的帧索引，并且使用左闭右闭的区间表达，因此start帧序号需要减1
                                    st_frame_idx = range_annotation["ranges"][0]["start"] - 1
                                    end_frame_idx = range_annotation["ranges"][0]["end"]
                                    timeline_label = range_annotation["timelinelabels"][0]
                                    item = UrlVideoStAnnotationDB(
                                        video_id=video_item_id,
                                        start_frame_idx=st_frame_idx,
                                        end_frame_idx=end_frame_idx,
                                        annotation=timeline_label,
                                    )
                                    session.add(item)
                            session.commit()

                if success:
                    shutil.move(file, passed_json_dst_dir)
                    logger.info(
                        f"处理标注文件 {file} 成功, the file will be moved to passed_json_dst_dir {passed_json_dst_dir}"
                    )
                else:
                    shutil.move(file, impassed_json_dst_dir)
                    logger.error(
                        f"处理标注文件 {file} 失败, the file will be moved to impassed_json_dst_dir {impassed_json_dst_dir}"
                    )
            except Exception as e:
                logger.error(f"处理标注文件 {file} 失败: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db_file_path",
        type=str,
        required=True,
        help="数据库文件路径",
    )
    parser.add_argument(
        "--json_src_dir",
        type=str,
        required=True,
        help="原始标注文件所在目录",
    )
    parser.add_argument(
        "--passed_json_dst_dir",
        type=str,
        required=True,
        help="处理成功的标注文件保存目录",
    )
    parser.add_argument(
        "--impassed_json_dst_dir",
        type=str,
        required=True,
        help="处理失败的标注文件保存目录",
    )
    parser.add_argument(
        "--download_dir",
        type=str,
        required=True,
        help="下载视频保存目录",
    )
    parser.add_argument(
        "--logger_path",
        type=str,
        default=None,
    )
    args = parser.parse_args()
    logger = setup_logger(name="enter_url_video_st_annotation", log_dir=args.logger_path)
    enter_url_video_st_annotation_json_files(
        db_file_path=args.db_file_path,
        json_src_dir=args.json_src_dir,
        passed_json_dst_dir=args.passed_json_dst_dir,
        impassed_json_dst_dir=args.impassed_json_dst_dir,
        download_dir=args.download_dir,
        logger=logging.getLogger(__name__),
    )
"""Usage:
python scripts/annotation/subtask_annotation/enter_url_video_st_annotation_without_validate.py \
    --db_file_path ./db/datasets_new.db \
    --json_src_dir ./datas/annotation/subtask_annotation/json_files \
    --passed_json_dst_dir ./datas/annotation/subtask_annotation/passed_json_files_passed \
    --impassed_json_dst_dir ./datas/annotation/subtask_annotation/impassed_json_files \
    --download_dir ./datas/annotation/subtask-annotations/download-videos \
    --logger_path ./logs


python scripts/annotation/subtask_annotation/enter_url_video_st_annotation_without_validate.py \
    --db_file_path ./db/datasets_new.db \
    --json_src_dir ./datas/annotation/subtask_annotation/json_files \
    --passed_json_dst_dir ./datas/annotation/subtask_annotation/passed_json_files_passed \
    --impassed_json_dst_dir ./datas/annotation/subtask_annotation/impassed_json_files \
    --download_dir ./datas/annotation/subtask-annotations/download-videos \
    --logger_path ./logs
"""

# db_file_path: Path = Path(db_file_path).expanduser().absolute()
# source_dir = Path(json_src_dir).expanduser().absolute()
# passed_json_dst_dir: Path = Path(passed_json_dst_dir).expanduser().absolute()
# impassed_json_dst_dir: Path = Path(impassed_json_dst_dir).expanduser().absolute()
