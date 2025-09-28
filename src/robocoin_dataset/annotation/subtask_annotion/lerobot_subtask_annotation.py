import json
import logging
from collections import defaultdict
from pathlib import Path

from sqlalchemy.orm import Session

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DatasetSubtaskAnnotationContentStatusDB,
    EpisodeRangeSubtaskAnnotationDB,
    LeFormatConvertDB,
    LerobotSubtaskAnnotationStatusDB,
    TaskStatus,
)


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
    验证标注 JSON 数据是否满足以下条件：
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
            errors.append(validate_annotation_item(item), start_frame_idx=start_frame_idx)
        except AssertionError as e:  # noqa: PERF203
            errors.append(f"Invalid item: {e}")
            continue

    return errors


class LerobotSubtaskAnnotation:
    def __init__(
        self,
        db_file_path: str | Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.db = DatasetDatabase(db_file_path)
        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger(__name__)

    def _upsert_lerobot_subtask_annotation_status(
        self,
        session: Session,
        dataset_uuid: str,
        status: TaskStatus,
        err_msg: str | None = None,
    ) -> None:
        # 确定 session 来源

        try:
            # 直接查询并更新，或创建
            item = (
                session.query(LerobotSubtaskAnnotationStatusDB)
                .filter(LerobotSubtaskAnnotationStatusDB.dataset_uuid == dataset_uuid)
                .one_or_none()
            )

            if item:
                item.status = status
                item.err_msg = err_msg  # 确保字段名正确
            else:
                session.add(
                    LerobotSubtaskAnnotationStatusDB(
                        dataset_uuid=dataset_uuid,
                        status=status,
                        err_msg=err_msg,
                    )
                )
            session.commit()
        except Exception:
            session.rollback()
            raise

    def _upsert_lerobot_subtask_annotation_status(
        self,
        dataset_uuid: str,
        status: TaskStatus,
        err_msg: str | None = None,
        extern_sesson: Session | None = None,
    ) -> None:
        if extern_sesson:
            session = extern_sesson
        else:
            session = self.db.with_session()

        with session as session:
            item: LerobotSubtaskAnnotationStatusDB = (
                session.query(LerobotSubtaskAnnotationStatusDB)
                .filter(LerobotSubtaskAnnotationStatusDB.dataset_uuid == dataset_uuid)
                .first()
            )
            if item:
                item.dataset_uuid = dataset_uuid
                item.status = status
                item.err_msg = err_msg
            else:
                item = LerobotSubtaskAnnotationStatusDB(
                    dataset_uuid=dataset_uuid, status=status, error_message=err_msg
                )
                session.add(item)
            session.commit()

    def sync_lerobot_subtask_annotation_task(self) -> None:
        with self.db.with_session() as session:
            query = session.query(DatasetSubtaskAnnotationContentStatusDB.dataset_uuid).filter(
                ~session.query(LerobotSubtaskAnnotationStatusDB)
                .filter(
                    LerobotSubtaskAnnotationStatusDB.dataset_uuid
                    == DatasetSubtaskAnnotationContentStatusDB.dataset_uuid
                )
                .exists()
            )
            items = query.all()
            for item in items:
                self._upsert_lerobot_subtask_annotation_status(
                    session, dataset_uuid=item.dataset_uuid, status=TaskStatus.PENDING
                )
            self.logger.info(f"Sync {len(items)} lerobot subtask annotation tasks")

    def _gen_one_lerobot_subtask_annotation_task(self) -> tuple[str, str | Path]:
        with self.db.with_session() as session:
            query = (
                session.query(LeFormatConvertDB.dataset_uuid, LeFormatConvertDB.convert_path)
                .filter(
                    LeFormatConvertDB.dataset_uuid == LerobotSubtaskAnnotationStatusDB.dataset_uuid
                )
                .filter(LerobotSubtaskAnnotationStatusDB.status == TaskStatus.PENDING)
            )

            item: LeFormatConvertDB = query.first()
            return item.dataset_uuid, item.convert_path

    def _validate_range_coverage(self, frame_num: int, ranges: list[tuple[int, int, str]]) -> bool:
        ranges_frame_num = max(end for _, end, _ in ranges) + 1
        if frame_num != ranges_frame_num:
            raise ValueError(
                f"标注数据有误：帧数不一致，标注数据帧数：{ranges_frame_num}，视频帧数：{frame_num}"
            )
        temp_ranges = [(start, end) for start, end, _ in ranges]
        errors = validate_coverage(temp_ranges)
        if errors:
            raise ValueError(f"标注数据有误：{errors}")

    def _get_episodes_frame_num(self, convert_path: str | Path) -> dict[int, int]:
        convert_path = Path(convert_path).expanduser().absolute()
        if not convert_path.exists():
            raise FileNotFoundError(f"{convert_path} does not exist.")
        if not convert_path.is_dir():
            raise NotADirectoryError(f"{convert_path} is not a directory.")

        episode_jsonl_path = convert_path / "meta/episode.jsonl"

        result = {}
        if not episode_jsonl_path.exists():
            raise FileNotFoundError(f"{episode_jsonl_path} does not exist.")
        try:
            with open(episode_jsonl_path, encoding="utf-8") as f:
                episode_jsonl_data = [json.loads(line) for line in f]
                for item in episode_jsonl_data:
                    ep_idx = item["episode_index"]
                    frame_num = item["length"]
                    result[ep_idx] = {frame_num}

            return result
        except Exception as e:
            raise Exception(f"❌ 读取 {episode_jsonl_path} 失败: {e}")

    def _get_episode_range_subtask_annotation(
        self, dataset_uuid: str
    ) -> dict[int, list[tuple[int, int, str]]]:
        with self.db.with_session() as session:
            query = session.query(EpisodeRangeSubtaskAnnotationDB).filter(
                EpisodeRangeSubtaskAnnotationDB.dataset_uuid == dataset_uuid
            )
            items = query.all()
            result = defaultdict(list)
            for item in items:
                result[item.episode_id].append(
                    item.range_from_frame_idx,
                    item.range_to_frame_idx,
                    item.subtask_annotation,
                )

            query = session.query(LeFormatConvertDB).filter(
                LeFormatConvertDB.dataset_uuid == dataset_uuid
            )
            item = query.first()
            if item:
                episodes_frame_num_dict = self._get_episodes_frame_num(
                    convert_path=item.convert_path
                )
            else:
                raise Exception(f"dataset: {dataset_uuid} NOT found convert path")

            for ep_idx, range_annotation in result.items():
                self._validate_range_coverage(
                    frame_num=episodes_frame_num_dict[ep_idx],
                    ranges=range_annotation,
                )

            return result

    def _get_ep_data_file(self, ds_dir: str | Path, ep_idx: int) -> Path | None:
        ds_dir = Path(ds_dir).expanduser().absolute()
        if not ds_dir.exists():
            raise ValueError(f"{ds_dir} not exists")
        if not ds_dir.is_dir():
            raise ValueError(f"{ds_dir} is not a dir")
        ep_file_name = f"episode_{ep_idx:06d}.parquet"

        return next(ds_dir.rglob(ep_file_name), None)
