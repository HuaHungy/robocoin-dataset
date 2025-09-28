import json
import logging
import os
import pickle
import shutil
import subprocess
import tempfile
import threading
from collections import defaultdict
from pathlib import Path

import av
import imagehash
import requests
from PIL import Image
from sqlalchemy import exists
from sqlalchemy.orm import Session
from tqdm import tqdm

from robocoin_dataset.annotation.subtask_annotion.subtask_annotation_process import (
    validate_annotation_json,
)
from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DatasetAnnotationCorrespondingDB,
    DatasetSubtaskAnnotationContentDB,
    DatasetSubtaskAnnotationContentStatusDB,
    DownloadStatus,
    EpisodeRangeSubtaskAnnotationDB,
    EpisodeSubtaskAnnotationCorrespondingDB,
    FileHashStatus,
    ImageHashStatus,
    LeFormatConvertDB,
    SubtaskAnnotationJsonDB,
    SubtaskAnnotationVideoDownloadDB,
    SubtaskAnnotationVideoFileHashDB,
    SubtaskAnnotationVideoImageHashDB,
    TaskStatus,
)

FRAME_SAMPLE_NUM = 10


def gen_frame_indices_from_framenum(frame_num: int) -> list[int]:
    """
    根据视频总帧数和目标采样帧数，生成准均匀分布的帧索引列表。
    保证：对于相同的 (frame_num, sample_num)，返回结果始终一致。

    采用等距采样（首帧固定为 0，末帧包含），并向下取整索引。

    :param frame_num: 视频总帧数（>= 1）
    :param sample_num: 要采样的帧数量（>= 1）
    :return: 准均匀分布的帧索引列表，长度为 min(sample_num, frame_num)
    """
    if frame_num <= 0:
        raise ValueError("frame_num 必须大于 0")
    if FRAME_SAMPLE_NUM <= 0:
        raise ValueError("sample_num 必须大于 0")

    # 实际采样数不能超过总帧数
    actual_sample_num = min(FRAME_SAMPLE_NUM, frame_num)

    if actual_sample_num == 1:
        return [0]  # 单帧时返回第一帧

    if actual_sample_num == frame_num:
        return list(range(frame_num))  # 全部采样

    # 等间距采样：从 0 到 frame_num-1，均匀取 actual_sample_num 个点
    indices = []
    for i in range(actual_sample_num):
        # 线性映射：i / (sample_num - 1) * (frame_num - 1)
        index = int(round(i * (frame_num - 1) / (actual_sample_num - 1)))
        indices.append(index)

    # 去重并保持顺序（理论上不会重复，但 round 可能导致边界重复）
    seen = set()
    unique_indices = []
    for idx in indices:
        if idx not in seen:
            seen.add(idx)
            unique_indices.append(idx)

    # 如果去重后数量不足，补充缺失的帧（比如中间插值或从中间取）
    while len(unique_indices) < actual_sample_num:
        # 简单策略：从中间开始逐个添加未使用的帧
        mid = frame_num // 2
        for offset in range(0, frame_num // 2 + 1):
            candidates = [mid + offset, mid - offset] if offset > 0 else [mid]
            for cand in candidates:
                if 0 <= cand < frame_num and cand not in seen:
                    unique_indices.append(cand)
                    seen.add(cand)
                    break
            if len(unique_indices) >= actual_sample_num:
                break

    # 排序并截断到目标数量
    unique_indices.sort()
    return unique_indices[:actual_sample_num]


def extract_frame_phashes_ffmpeg(
    video_path: str, frame_indices: list[int], hash_size: int = 16
) -> list[imagehash.ImageHash]:
    """
    使用 ffmpeg 从视频中提取指定帧的 pHash（批量抽取，高效稳定）

    Args:
        filepath (str): 视频文件路径
        frame_indices (list[int]): 要提取的帧索引列表（如 [0, 100, 200]）
        hash_size (int): pHash 的尺寸（默认 16，表示 16x16=256 bit）

    Returns:
        List[imagehash.ImageHash]: pHash 列表，对应每个帧，失败为 None
    """
    video_path = Path(video_path)

    # 检查文件是否存在
    if not video_path.exists():
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    # 如果没有要抽的帧，直接返回
    if not frame_indices:
        return []

    # 创建临时目录保存中间图像
    with tempfile.TemporaryDirectory() as tmpdir:
        output_pattern = os.path.join(tmpdir, "frame_%08d.png")

        # 构建 ffmpeg 的 select 滤镜表达式：eq(n,0)+eq(n,100)+eq(n,200)
        select_expr = "+".join(f"eq(n,{idx})" for idx in frame_indices)
        filter_complex = f"select='{select_expr}'"

        # 构造 ffmpeg 命令
        cmd = [
            "ffmpeg",
            "-i",
            video_path,  # 输入文件
            "-vf",
            filter_complex,  # 只保留指定帧
            "-vsync",  # 最高质量
            "0",  # 覆盖输出
            output_pattern,  # 输出文件命名
        ]

        # 执行命令
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=300,  # 5 分钟超时
        )

        if result.returncode != 0:
            print(f"❌ ffmpeg 抽帧失败 (退出码 {result.returncode}): {video_path}")
            print(f"错误信息:\n{result.stderr}")
            return [None] * len(frame_indices)

        # 按 frame_indices 顺序加载图像并计算 pHash
        phash_list = []
        # 获取生成的图像文件，按序号排序
        generated_files = sorted(
            [f for f in os.listdir(tmpdir) if f.startswith("frame_")],
            key=lambda x: int(x.split("_")[1].split(".")[0]),
        )

        # 映射：文件名 -> 是否存在
        file_map = {f: True for f in generated_files}

        for idx in range(len(frame_indices)):
            # filename = f"frame_{idx:08d}.png"
            filename = f"frame_{idx + 1:08d}.png"
            img_path = os.path.join(tmpdir, filename)
            if filename in file_map and os.path.exists(img_path):
                try:
                    img = Image.open(img_path)
                    phash = imagehash.phash(img, hash_size=hash_size)
                    phash_list.append(phash)
                except Exception as e:
                    print(f"❌ 处理图像 {filename} 失败: {e}")
                    phash_list.append(None)
            else:
                print(f"⚠️ 未找到帧 {idx} 的图像")
                print(f"视频文件路径: {video_path} ")
                phash_list.append(None)

        return phash_list


# def validate_coverage(ranges: list[tuple[int, int]]) -> None:
#     """
#     验证一组 (start, end) 区间是否覆盖从 1 开始的所有连续帧，无空缺。
#     使用 左闭右闭 语义：[start, end] 包含 start 和 end。
#     允许重叠。

#     与原版本不同：本函数会收集所有错误，最后统一抛出。

#     Args:
#         ranges: 区间列表，每个元素为 (start, end)，包含两端
#         item_id: 当前项 ID，用于错误信息

#     Raises:
#         AssertionError: 包含所有错误的汇总信息
#     """
#     errors = []  # 收集所有错误信息

#     if not ranges:
#         errors.append("ranges 不能为空")
#     else:
#         # 排序前先做基本合法性检查
#         for i, (start, end) in enumerate(ranges):
#             if not isinstance(start, int) or not isinstance(end, int):
#                 errors.append(f"区间 #{i + 1} ({start}, {end}): start 和 end 必须是整数")
#                 continue  # 后续检查跳过这个区间
#             if start < 1:
#                 errors.append(f"区间 #{i + 1} ({start}, {end}): start 帧不能小于 1")
#             if end < start:
#                 errors.append(f"区间 #{i + 1} ({start}, {end}): end 帧不能小于 start 帧")

#         if not errors:  # 只有在基础格式都正确时才进行覆盖检查
#             sorted_ranges = sorted(ranges, key=lambda x: x[0])
#             current_end = 0  # 当前已连续覆盖到的最后一个帧

#             for start, end in sorted_ranges:
#                 # 检查是否有空缺
#                 if start > current_end + 1:
#                     missing_start = current_end + 1
#                     missing_end = start - 1
#                     if missing_start == missing_end:
#                         gap_msg = f"帧 {missing_start}"
#                     else:
#                         gap_msg = f"帧 [{missing_start}, {missing_end}]"
#                     errors.append(f"存在空缺：{gap_msg} 未被覆盖")

#                 # 更新当前覆盖的最远帧
#                 if end > current_end:
#                     current_end = end

#             # 最终检查：是否覆盖了帧 1？
#             if current_end < 1:
#                 errors.append("至少需要覆盖到帧 1")

#     # === 所有检查完成，统一处理错误 ===
#     if errors:
#         raise AssertionError(errors)


# def validate_annotation_item(item: dict) -> None:
#     video_labels = item.get("videoLabels", [])
#     if not isinstance(video_labels, list):
#         raise AssertionError("videoLabels 必须是数组")

#     if len(video_labels) == 0:
#         raise AssertionError("videoLabels 不能为空")

#     ranges = []
#     for lbl_idx, label in enumerate(video_labels):
#         # 验证 ranges 长度为 1
#         if not isinstance(label.get("ranges"), list) or len(label["ranges"]) != 1:
#             raise AssertionError(f"videoLabel #{lbl_idx + 1}: ranges 必须是一个包含一个元素的数组")

#         r = label["ranges"][0]
#         if not isinstance(r, dict) or "start" not in r or "end" not in r:
#             raise AssertionError(
#                 f"videoLabel #{lbl_idx + 1}: range 必须是 {{'start': ..., 'end': ...}} 格式"
#             )

#         start, end = r["start"], r["end"]
#         if not isinstance(start, int) or not isinstance(end, int):
#             raise AssertionError(f"videoLabel #{lbl_idx + 1}: start 和 end 必须是整数")
#         if start < 1 or end < start:
#             raise AssertionError(f"videoLabel #{lbl_idx + 1}: start >= 1 且 end > start")

#         ranges.append((start, end))

#         # 验证 timelinelabels 长度为 1
#         timeline_labels = label.get("timelinelabels")
#         if not isinstance(timeline_labels, list) or len(timeline_labels) != 1:
#             raise AssertionError(
#                 f"videoLabel #{lbl_idx + 1}: timelinelabels 必须是一个包含一个字符串的数组"
#             )
#         if not isinstance(timeline_labels[0], str):
#             raise AssertionError(f"videoLabel #{lbl_idx + 1}: timelinelabels[0] 必须是字符串")

#     # 验证 range 覆盖连续帧（从 1 开始，无空缺）
#     validate_coverage(ranges)


# def validate_annotation_json(data: str | list) -> list[str]:
#     """
#     验证标注 JSON 数据是否满足以下条件：
#     1. 所有 ranges 覆盖从 1 开始的所有帧，无空缺
#     2. 每个 videoLabel 的 ranges 只有一个 {start, end}
#     3. 每个 videoLabel 的 timelinelabels 只有一个标签

#     Args:
#         data: JSON 字符串 或 已加载的 Python 对象（list of dicts）

#     Returns:
#         err_msg: 错误信息，为空则表示无错误
#     """
#     if isinstance(data, str):
#         data = json.loads(data)

#     if not isinstance(data, list):
#         raise ValueError("JSON 根节点必须是一个数组")

#     err_msg = []
#     for idx, item in enumerate(data):
#         try:
#             validate_annotation_item(item)
#         except AssertionError as e:  # noqa: PERF203
#             err_msg.append(f"第{idx + 1}个条目: {str(e)}")

#     return err_msg


class VideoSubtaskAnnotation:
    def __init__(
        self,
        db_file_path: str | Path,
        json_src_dir: str | Path,
        passed_json_dst_dir: str | Path,
        impassed_json_dst_dir: str | Path,
        video_dl_dir: str | Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.json_src_dir = Path(json_src_dir).expanduser().absolute()
        self.passed_json_dst_dir = Path(passed_json_dst_dir).expanduser().absolute()
        self.impassed_json_dst_dir = Path(impassed_json_dst_dir).expanduser().absolute()
        self.video_dl_dir = Path(video_dl_dir).expanduser().absolute()
        self.logger = logger or logging.getLogger(__name__)

        if self.json_src_dir.is_file():
            raise NotADirectoryError(f"Json source directory {self.json_src_dir} is a file")
        if self.passed_json_dst_dir.is_file():
            raise NotADirectoryError(
                f"Json destination directory {self.passed_json_dst_dir} is a file"
            )
        self.passed_json_dst_dir.mkdir(parents=True, exist_ok=True)
        self.impassed_json_dst_dir.mkdir(parents=True, exist_ok=True)
        if self.video_dl_dir.is_file():
            raise NotADirectoryError(f"Download directory {self.video_dl_dir} is a file")
        self.video_dl_dir.mkdir(parents=True, exist_ok=True)
        pass

    def process_video_subtask_annotation_json_files(self) -> None:
        source_dir = self.json_src_dir
        json_files = [
            file for file in source_dir.iterdir() if file.is_file() and file.suffix == ".json"
        ]
        for file in tqdm(json_files, desc="Processing Subtask Annotation JSON files", unit="file"):
            if file.is_file() and file.suffix == ".json":
                try:
                    success = True
                    with open(file) as f:
                        try:
                            data = json.load(f)
                            errors = validate_annotation_json(data, start_frame_idx=1)
                            if errors:
                                for error in errors:
                                    if error:
                                        self.logger.error(f"File {file} 检验失败: {error}")
                                        success = False
                        except Exception as e:
                            self.logger.error(f"❌ {file} is not a valid annotation json: {e}")
                            success = False

                        if success:
                            for episode in data:
                                video_url = episode["video"]
                                ep_annotation = json.dumps(episode["videoLabels"])

                                with self.db.with_session() as session:
                                    item = (
                                        session.query(SubtaskAnnotationJsonDB)
                                        .filter(SubtaskAnnotationJsonDB.video_url == video_url)
                                        .first()
                                    )

                                    if item:
                                        item.json_content = ep_annotation
                                        self.logger.info(
                                            f"⚠️ Video {video_url} already exists in database, this one will covert the old one."
                                        )
                                    else:
                                        new_entry = SubtaskAnnotationJsonDB(
                                            video_url=video_url, json_content=ep_annotation
                                        )
                                        session.add(new_entry)

                                    session.commit()

                    if success:
                        shutil.move(file, self.passed_json_dst_dir)
                        self.logger.info(
                            f"处理标注文件 {file} 成功, the file will be moved to passed_json_dst_dir {self.passed_json_dst_dir}"
                        )
                    else:
                        shutil.move(file, self.impassed_json_dst_dir)
                        self.logger.error(
                            f"处理标注文件 {file} 失败, the file will be moved to impassed_json_dst_dir {self.impassed_json_dst_dir}"
                        )
                except Exception as e:
                    self.logger.error(f"处理标注文件 {file} 失败: {e}")

    def sync_download_tasks(self) -> None:
        with self.db.with_session() as session:
            # 子查询：哪些 annotation_id 已经存在于 download 表中
            subquery = session.query(SubtaskAnnotationVideoDownloadDB.annotation_id).subquery()

            # 查询 json 表中不存在于 download 表的记录
            missing_annotations = (
                session.query(SubtaskAnnotationJsonDB.id, SubtaskAnnotationJsonDB.video_url)
                .filter(~exists().where(subquery.c.annotation_id == SubtaskAnnotationJsonDB.id))
                .all()
            )

            # 构建要插入的 download 记录
            new_downloads = []
            for ann in missing_annotations:
                download_path = f"{self.video_dl_dir}/{ann.id}.mp4"  # 可按需调整命名规则

                new_download = SubtaskAnnotationVideoDownloadDB(
                    annotation_id=ann.id,
                    video_download_path=download_path,
                    download_status=DownloadStatus.PENDING,
                    frame_num=None,
                    video_matched_status=False,
                    # file_hash 和 image_hash 会由 cascade 自动处理（如果后面添加）
                )
                new_downloads.append(new_download)

            # 批量插入
            if new_downloads:
                session.bulk_save_objects(new_downloads)
                session.commit()
                self.logger.info(f"成功插入 {len(new_downloads)} 条新的下载记录。")
            else:
                self.logger.info("没有缺失的下载记录需要创建。")

    def _gen_download_task(self) -> tuple[str, str, int]:
        with self.db.with_session() as session:
            query = (
                session.query(
                    SubtaskAnnotationVideoDownloadDB.id,
                    SubtaskAnnotationVideoDownloadDB.annotation_id,
                    SubtaskAnnotationJsonDB.video_url,
                )
                .join(
                    SubtaskAnnotationJsonDB,
                    SubtaskAnnotationJsonDB.id == SubtaskAnnotationVideoDownloadDB.annotation_id,
                )
                .filter(SubtaskAnnotationVideoDownloadDB.download_status == DownloadStatus.PENDING)
                .first()
            )

            if not query:
                self.logger.info(
                    "未找到状态为 PENDING 的下载任务，或所有任务对应的 JSON 记录已不存在。"
                )
                return None, None, None
            download_id, annotation_id, video_url = query

            # 第二步：获取 download 对象并更新状态
            download_obj: SubtaskAnnotationVideoDownloadDB = session.query(
                SubtaskAnnotationVideoDownloadDB
            ).get(download_id)
            if download_obj:
                download_obj.download_status = DownloadStatus.DOWNLOADING
                session.commit()

                return video_url, download_obj.video_download_path, download_id
            session.rollback()
            self.logger.error("更新状态时发生错误：无法重新加载对象。")
            return video_url, None, None

    def _submit_download_result(self, task_id: int, success: bool, frame_num: int) -> None:
        with self.db.with_session() as session:
            task = (
                session.query(SubtaskAnnotationVideoDownloadDB)
                .filter(SubtaskAnnotationVideoDownloadDB.id == task_id)
                .with_for_update(skip_locked=True)
                .first()
            )
            if task and task.download_status == DownloadStatus.DOWNLOADING:
                if success:
                    task.download_status = DownloadStatus.SUCCESS
                else:
                    task.download_status = DownloadStatus.FAILED

                task.frame_num = frame_num
                session.commit()

    def _download_video(self, url: str, file_path: Path) -> bool:
        file_path = Path(file_path).expanduser().absolute()
        if file_path.exists():
            self.logger.info(f"{file_path} 已存在, passing")
            return True
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_file_path = file_path.parent / f"{file_path.name}.tmp"
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            with open(tmp_file_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:  # 过滤掉保持连接的空 chunk
                        file.write(chunk)
                shutil.move(tmp_file_path, file_path)
                return True

        except Exception as e:
            self.logger.error(f"下载失败: {url}, 错误: {e}")
            return False

    def _get_frame_num(self, video_path: str) -> int:
        try:
            with av.open(video_path) as container:
                # 查找视频流
                video_stream = next((s for s in container.streams if s.type == "video"), None)
                if not video_stream:
                    return -1
                return video_stream.frames if video_stream.frames > 0 else -1
        except Exception as e:
            raise Exception("Failed to get frame num") from e

    def download_videos_single_thread(self) -> None:
        with self.db.with_session() as session:
            task_num = (
                session.query(SubtaskAnnotationVideoDownloadDB)
                .filter(SubtaskAnnotationVideoDownloadDB.download_status == DownloadStatus.PENDING)
                .count()
            )

        pbar = tqdm(total=task_num, desc="📥 下载进度", unit="file", dynamic_ncols=True)

        while True:
            # 获取任务
            url, save_path, task_id = self._gen_download_task()
            if task_id is None:
                break  # 无任务了

            success = self._download_video(url, save_path)
            try:
                frame_num = self._get_frame_num(save_path)
            except Exception:
                frame_num = -1
                success = False
                self.logger.info(f"video decoding failed: {save_path}")
            self._submit_download_result(task_id, success, frame_num=frame_num)

            # ✅ 更新进度条（线程安全）
            pbar.set_postfix_str(f"Task {task_id}: {'✅' if success else '❌'}")
            pbar.update(1)  # 增加1

            if not success:
                self.logger.warning(f"任务 {task_id} 下载失败")

    def download_videos_multi_threads(self, num_workers: int = 8) -> None:
        """
        启动多个工作线程，并发下载所有待处理任务
        """

        with self.db.with_session() as session:
            task_num = (
                session.query(SubtaskAnnotationVideoDownloadDB)
                .filter(SubtaskAnnotationVideoDownloadDB.download_status == DownloadStatus.PENDING)
                .count()
            )
        self.logger.info(f"🚀 启动 {num_workers} 个下载线程...")

        pbar = tqdm(total=task_num, desc="📥 下载进度", unit="file", dynamic_ncols=True)

        pbar_lock = threading.Lock()

        def _worker_download(worker_id: int) -> None:
            while True:
                # 获取任务
                url, save_path, task_id = self._gen_download_task()
                if task_id is None:
                    break  # 无任务了

                success = self._download_video(url, save_path)
                try:
                    frame_num = self._get_frame_num(save_path)
                except Exception:
                    frame_num = -1
                    success = False
                    self.logger.info(f"video decoding failed: {save_path}")

                self._submit_download_result(task_id, success, frame_num=frame_num)

                # ✅ 更新进度条（线程安全）
                with pbar_lock:
                    pbar.set_postfix_str(f"Task {task_id}: {'✅' if success else '❌'}")
                    pbar.update(1)  # 增加1

                if not success:
                    self.logger.warning(f"Worker-{worker_id}: 任务 {task_id} 下载失败")

        threads: list[threading.Thread] = []
        for i in range(num_workers):
            t = threading.Thread(target=_worker_download, args=(i,), name=f"Downloader-{i}")
            t.start()
            threads.append(t)

        # 等待所有线程完成
        for t in threads:
            t.join()

        self.logger.info("🎉 所有下载任务已完成！")

    def sync_filehash_tasks(self) -> None:
        with self.db.with_session() as session:
            existing_download_ids = session.query(
                SubtaskAnnotationVideoFileHashDB.download_id
            ).subquery()

            # 查询满足条件的 download 记录：
            #   - 下载成功
            #   - 不存在于 file_hash 表中
            downloads_needing_hash = (
                session.query(SubtaskAnnotationVideoDownloadDB.id)
                .filter(
                    SubtaskAnnotationVideoDownloadDB.download_status == DownloadStatus.SUCCESS,
                    ~exists().where(
                        existing_download_ids.c.download_id == SubtaskAnnotationVideoDownloadDB.id
                    ),
                )
                .all()
            )

            # 构建新的 file_hash 记录
            new_file_hashes = []
            for download in downloads_needing_hash:
                file_hash = SubtaskAnnotationVideoFileHashDB(
                    download_id=download.id,
                    sha256=None,  # 等待计算
                    hash_status=FileHashStatus.PENDING,
                )
                new_file_hashes.append(file_hash)

            # 批量插入
            if new_file_hashes:
                session.bulk_save_objects(new_file_hashes)
                session.commit()
                self.logger.info(f"已为 {len(new_file_hashes)} 个下载任务创建文件哈希记录。")
                return
            self.logger.info("没有需要创建文件哈希的任务。")
            return

    def _gen_file_hash_task(self) -> tuple[Path, int]:
        with self.db.with_session() as session:
            # 使用 join 联查 file_hash 和 download 表，确保能拿到 video_download_path
            result = (
                session.query(
                    SubtaskAnnotationVideoFileHashDB.id,
                    SubtaskAnnotationVideoFileHashDB.download_id,
                    SubtaskAnnotationVideoDownloadDB.video_download_path,
                )
                .join(
                    SubtaskAnnotationVideoDownloadDB,
                    SubtaskAnnotationVideoDownloadDB.id
                    == SubtaskAnnotationVideoFileHashDB.download_id,
                )
                .filter(SubtaskAnnotationVideoFileHashDB.hash_status == FileHashStatus.PENDING)
                .first()
            )

            if not result:
                self.logger.info("未找到状态为 PENDING 的文件哈希任务。")
                return None, None

            file_hash_id, download_id, video_download_path = result

            if not video_download_path:
                self.logger.warning(
                    f"警告：file_hash_id={file_hash_id} 对应的 video_download_path 为空。"
                )
                return None, None

            # 获取 file_hash 实例并更新状态（为了触发 ORM 更新）
            file_hash_record = session.query(SubtaskAnnotationVideoFileHashDB).get(file_hash_id)
            if file_hash_record:
                file_hash_record.hash_status = FileHashStatus.PROCESSING
                session.commit()
            else:
                session.rollback()
                self.logger.info("更新状态失败：无法加载 file_hash 记录。")
                return None, None

            return video_download_path, file_hash_id

    def _submit_filehash_result(self, task_id: int, filehash: str) -> None:
        with self.db.with_session() as session:
            # 查询 file_hash 记录，加锁防止并发冲突
            file_hash_task = (
                session.query(SubtaskAnnotationVideoFileHashDB)
                .filter(SubtaskAnnotationVideoFileHashDB.id == task_id)
                .with_for_update(skip_locked=True)
                .first()
            )

            if not file_hash_task:
                self.logger.error(f"FileHash 任务不存在，ID: {task_id}")
                return

            if file_hash_task.hash_status != FileHashStatus.PROCESSING:
                self.logger.error(
                    f"FileHash 任务状态异常，ID: {task_id}，当前状态: {file_hash_task.hash_status}"
                )
                return

            # 根据 filehash 是否有效决定状态
            if filehash and isinstance(filehash, str) and len(filehash.strip()) == 64:
                filehash = filehash.strip()
                file_hash_task.sha256 = filehash
                file_hash_task.hash_status = FileHashStatus.SUCCESS
            else:
                file_hash_task.hash_status = FileHashStatus.FAILED

            try:
                session.commit()
            except Exception as e:
                session.rollback()
                self.logger.error(f"Failed to commit file hash for {id}: {e}")
                raise e

    def _compute_sha256(self, filepath: str) -> str:
        """计算文件的 SHA-256 哈希值"""
        import hashlib

        hasher = hashlib.sha256()
        try:
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            self.logger.error(f"无法读取文件 {filepath}: {e}")

    def compute_file_hashes_single_thread(self) -> None:
        with self.db.with_session() as session:
            total_tasks = (
                session.query(SubtaskAnnotationVideoFileHashDB)
                .join(
                    SubtaskAnnotationVideoDownloadDB,
                    SubtaskAnnotationVideoDownloadDB.id
                    == SubtaskAnnotationVideoFileHashDB.download_id,
                )
                .filter(SubtaskAnnotationVideoFileHashDB.hash_status == FileHashStatus.PENDING)
                .count()
            )

        if total_tasks == 0:
            self.logger.info("没有待处理的文件哈希任务。")
            return

        # 创建进度条
        pbar = tqdm(total=total_tasks, desc="🔐 计算文件哈希", unit="file", dynamic_ncols=True)

        while True:
            # 获取一个待处理的任务
            file_path, task_id = self._gen_file_hash_task()
            if task_id is None:
                break  # 无任务了

            # 计算 SHA256
            sha256_hex = None
            try:
                if not Path(file_path).exists():
                    raise FileNotFoundError(f"视频文件不存在: {file_path}")

                sha256_hex = self._compute_sha256(file_path)
                self.logger.debug(f"成功计算哈希: {file_path} -> {sha256_hex}")

            except Exception as e:
                self.logger.error(
                    f"计算文件哈希失败 (file_hash_id={task_id}, path={file_path}): {e}"
                )
                self._submit_filehash_result(task_id=task_id, filehash=None)  # 标记失败
                pbar.set_postfix_str(f"Task {task_id}: ❌")
                pbar.update(1)
                continue

            # 提交成功结果
            self._submit_filehash_result(task_id=task_id, filehash=sha256_hex)
            pbar.set_postfix_str(f"Task {task_id}: ✅")
            pbar.update(1)

        pbar.close()
        self.logger.info("文件哈希计算完成。")

    def compute_file_hashes_multi_threads(self, num_workers: int = 8) -> None:
        """
        启动多个工作线程，并发计算所有待处理视频文件的 SHA256 哈希值。

        :param num_workers: 工作线程数量
        """
        # 先统计总任务数
        with self.db.with_session() as session:
            total_tasks = (
                session.query(SubtaskAnnotationVideoFileHashDB)
                .join(
                    SubtaskAnnotationVideoDownloadDB,
                    SubtaskAnnotationVideoDownloadDB.id
                    == SubtaskAnnotationVideoFileHashDB.download_id,
                )
                .filter(SubtaskAnnotationVideoFileHashDB.hash_status == FileHashStatus.PENDING)
                .count()
            )

        if total_tasks == 0:
            self.logger.info("没有待处理的文件哈希任务。")
            return

        self.logger.info(f"🚀 启动 {num_workers} 个哈希计算线程...")

        # 创建进度条
        pbar = tqdm(total=total_tasks, desc="🔐 计算文件哈希", unit="file", dynamic_ncols=True)
        pbar_lock = threading.Lock()

        def _worker_hash(worker_id: int) -> None:
            while True:
                # 获取一个待处理的任务（线程安全）
                video_path, task_id = (
                    self._gen_file_hash_task()
                )  # 返回 {"file_hash_id": int, "video_download_path": str}
                if task_id is None:
                    break  # 所有任务已完成

                # 计算 SHA256
                try:
                    if not Path(video_path).exists():
                        raise FileNotFoundError(f"视频文件不存在: {video_path}")

                    sha256_hex = self._compute_sha256(video_path)
                    self.logger.debug(
                        f"Worker-{worker_id}: 成功计算哈希 → {sha256_hex[:8]}... ({video_path})"
                    )

                    # 提交成功结果
                    self._submit_filehash_result(task_id=task_id, filehash=sha256_hex)

                except Exception as e:
                    self.logger.error(
                        f"Worker-{worker_id}: 计算哈希失败 (file_hash_id={task_id}): {e}"
                    )
                    self._submit_filehash_result(task_id=task_id, filehash=None)  # 标记失败

                # ✅ 线程安全更新进度条
                with pbar_lock:
                    status = "✅" if "sha256_hex" in locals() else "❌"
                    pbar.set_postfix_str(f"Task {task_id}: {status}")
                    pbar.update(1)

        # 创建并启动线程
        threads: list[threading.Thread] = []
        for i in range(num_workers):
            t = threading.Thread(target=_worker_hash, args=(i,), name=f"HashWorker-{i}")
            t.start()
            threads.append(t)

        # 等待所有线程完成
        for t in threads:
            t.join()

        pbar.close()
        self.logger.info("🎉 所有文件哈希计算任务已完成！")

    def sync_imagehash_tasks(self) -> None:
        """
        为所有下载成功（SUCCESS）且尚未创建 image_hash 的任务，创建 image_hash 记录。
        """
        with self.db.with_session() as session:
            # 查询已存在的 image_hash 的 download_id
            existing_download_ids = session.query(
                SubtaskAnnotationVideoImageHashDB.download_id
            ).subquery()

            # 查询满足条件的 download 记录：
            #   - 下载成功
            #   - 不存在于 image_hash 表中
            downloads_needing_imagehash = (
                session.query(SubtaskAnnotationVideoDownloadDB.id)
                .filter(
                    SubtaskAnnotationVideoDownloadDB.download_status == DownloadStatus.SUCCESS,
                    ~exists().where(
                        existing_download_ids.c.download_id == SubtaskAnnotationVideoDownloadDB.id
                    ),
                )
                .all()
            )

            # 构建新的 image_hash 记录
            new_image_hashes = []
            for download in downloads_needing_imagehash:
                image_hash = SubtaskAnnotationVideoImageHashDB(
                    download_id=download.id,
                    image_hashes=None,
                    image_hash_status=ImageHashStatus.PENDING,
                )
                new_image_hashes.append(image_hash)

            # 批量插入
            if new_image_hashes:
                session.bulk_save_objects(new_image_hashes)
                session.commit()
                self.logger.info(f"已为 {len(new_image_hashes)} 个下载任务创建图像哈希记录。")
                return

            self.logger.info("没有需要创建图像哈希的任务。")

    def _gen_image_hash_task(self) -> tuple[str, list[int], int] | tuple[None, None, None]:
        """
        获取一个待处理的 image_hash 任务。
        返回: (video_download_path, image_frame_indices, image_hash_id)
        """
        with self.db.with_session() as session:
            result = (
                session.query(
                    SubtaskAnnotationVideoImageHashDB.id,
                    SubtaskAnnotationVideoDownloadDB.video_download_path,
                    SubtaskAnnotationVideoDownloadDB.frame_num,
                )
                .join(
                    SubtaskAnnotationVideoDownloadDB,
                    SubtaskAnnotationVideoDownloadDB.id
                    == SubtaskAnnotationVideoImageHashDB.download_id,
                )
                .filter(
                    SubtaskAnnotationVideoImageHashDB.image_hash_status == ImageHashStatus.PENDING
                )
                .first()
            )

            if not result:
                self.logger.info("未找到状态为 PENDING 的图像哈希任务。")
                return None, None, None

            image_hash_id, video_path, frame_num = result

            if not video_path:
                self.logger.warning(f"警告：image_hash_id={image_hash_id} 的 video_path 为空。")
                return None, None, None

            # 获取记录并更新状态为 PROCESSING
            image_hash_record = session.query(SubtaskAnnotationVideoImageHashDB).get(image_hash_id)
            if image_hash_record:
                image_hash_record.image_hash_status = ImageHashStatus.PROCESSING
                session.commit()
            else:
                session.rollback()
                self.logger.error("更新状态失败：无法加载 image_hash 记录。")
                return None, None, None

            image_frame_indices = gen_frame_indices_from_framenum(frame_num=frame_num)

            return video_path, image_frame_indices, image_hash_id

    def _submit_imagehashes_result(
        self,
        task_id: int,
        serialized_imagehashes: bytes,
    ) -> None:
        with self.db.with_session() as session:
            # 查询 image_hash 记录，加锁防止并发冲突
            image_hash_task = (
                session.query(SubtaskAnnotationVideoImageHashDB)
                .filter(SubtaskAnnotationVideoImageHashDB.id == task_id)
                .with_for_update(skip_locked=True)
                .first()
            )

            if not image_hash_task:
                self.logger.error(f"ImageHash 任务不存在，ID: {task_id}")
                return

            if image_hash_task.image_hash_status != ImageHashStatus.PROCESSING:
                self.logger.error(
                    f"ImageHash 任务状态异常，ID: {task_id}，当前状态: {image_hash_task.image_hash_status}"
                )
                return

            # 根据 filehash 是否有效决定状态
            if serialized_imagehashes:
                image_hash_task.image_hashes = serialized_imagehashes
                image_hash_task.image_hash_status = ImageHashStatus.SUCCESS
            else:
                image_hash_task.image_hash_status = ImageHashStatus.FAILED

            session.commit()

    def compute_image_hashes_multi_threads(self, num_workers: int = 8) -> None:
        """
        启动多个工作线程，并发计算所有待处理视频文件的 SHA256 哈希值。

        :param num_workers: 工作线程数量
        """
        # 先统计总任务数
        with self.db.with_session() as session:
            total_tasks = (
                session.query(SubtaskAnnotationVideoImageHashDB)
                .join(
                    SubtaskAnnotationVideoDownloadDB,
                    SubtaskAnnotationVideoDownloadDB.id
                    == SubtaskAnnotationVideoImageHashDB.download_id,
                )
                .filter(
                    SubtaskAnnotationVideoImageHashDB.image_hash_status == ImageHashStatus.PENDING
                )
                .count()
            )

        if total_tasks == 0:
            self.logger.info("没有待处理的视频指纹任务。")
            return

        self.logger.info(f"🚀 启动 {num_workers} 个指纹计算线程...")

        # 创建进度条
        pbar = tqdm(total=total_tasks, desc="🔐 计算视频指纹哈希", unit="video", dynamic_ncols=True)
        pbar_lock = threading.Lock()

        def _worker_hash(worker_id: int) -> None:
            while True:
                # 获取一个待处理的任务（线程安全）
                video_path, image_frame_indices, task_id = self._gen_image_hash_task()
                if task_id is None:
                    break  # 所有任务已完成

                # 计算 SHA256
                try:
                    phashes: list[imagehash.ImageHash] = extract_frame_phashes_ffmpeg(
                        video_path=video_path, frame_indices=image_frame_indices
                    )
                    serialized_hashes = pickle.dumps(phashes)
                    self.logger.debug(f"Worker-{worker_id}: 成功计算视频指纹  ({video_path})")

                    # 提交成功结果
                    self._submit_imagehashes_result(
                        task_id=task_id, serialized_imagehashes=serialized_hashes
                    )

                except Exception as e:
                    self.logger.error(
                        f"Worker-{worker_id}: 计算视频指纹失败 (image_hash_id={task_id}): {e}"
                    )
                    self._submit_imagehashes_result(
                        task_id=task_id, serialized_imagehashes=None
                    )  # 标记失败

                # ✅ 线程安全更新进度条
                with pbar_lock:
                    status = "✅" if "phashes" in locals() else "❌"
                    pbar.set_postfix_str(f"Task {task_id}: {status}")
                    pbar.update(1)

        # 创建并启动线程
        threads: list[threading.Thread] = []
        for i in range(num_workers):
            t = threading.Thread(target=_worker_hash, args=(i,), name=f"ImageHashesWorker-{i}")
            t.start()
            threads.append(t)

        # 等待所有线程完成
        for t in threads:
            t.join()

        pbar.close()
        self.logger.info("🎉 所有视频指纹计算任务已完成！")

    def compute_image_hashes_single_threads(self) -> None:
        """
        启动多个工作线程，并发计算所有待处理视频文件的 SHA256 哈希值。

        :param num_workers: 工作线程数量
        """
        # 先统计总任务数
        with self.db.with_session() as session:
            total_tasks = (
                session.query(SubtaskAnnotationVideoImageHashDB)
                .join(
                    SubtaskAnnotationVideoDownloadDB,
                    SubtaskAnnotationVideoDownloadDB.id
                    == SubtaskAnnotationVideoImageHashDB.download_id,
                )
                .filter(
                    SubtaskAnnotationVideoImageHashDB.image_hash_status == ImageHashStatus.PENDING
                )
                .count()
            )

        if total_tasks == 0:
            self.logger.info("没有待处理的视频指纹任务。")
            return

        # 创建进度条
        pbar = tqdm(total=total_tasks, desc="🔐 计算视频指纹哈希", unit="video", dynamic_ncols=True)

        while True:
            # 获取一个待处理的任务（线程安全）
            video_path, image_frame_indices, task_id = self._gen_image_hash_task()
            if task_id is None:
                break  # 所有任务已完成

            # 计算 SHA256
            try:
                phashes: list[imagehash.ImageHash] = extract_frame_phashes_ffmpeg(
                    video_path=video_path, frame_indices=image_frame_indices
                )
                serialized_hashes = pickle.dumps(phashes)
                self.logger.debug(f"成功计算视频指纹  ({video_path})")

                # 提交成功结果
                self._submit_imagehashes_result(
                    task_id=task_id, serialized_imagehashes=serialized_hashes
                )

            except Exception as e:
                self.logger.error(f"计算视频指纹失败 (image_hash_id={task_id}): {e}")
                self._submit_imagehashes_result(
                    task_id=task_id, serialized_imagehashes=None
                )  # 标记失败

            # ✅ 线程安全更新进度条
            status = "✅" if "phashes" in locals() else "❌"
            pbar.set_postfix_str(f"Task {task_id}: {status}")
            pbar.update(1)

        pbar.close()
        self.logger.info("🎉 所有视频指纹计算任务已完成！")

    def prepare_video_filehash_lib(self) -> None:
        with self.db.with_session() as session:
            results = (
                session.query(
                    SubtaskAnnotationVideoFileHashDB.sha256,
                    SubtaskAnnotationVideoFileHashDB.download_id,
                )
                .filter(SubtaskAnnotationVideoFileHashDB.hash_status == FileHashStatus.SUCCESS)
                .filter(
                    SubtaskAnnotationVideoFileHashDB.sha256.isnot(None)
                )  # 可选：确保 sha256 存在
                .all()
            )
        sha256_list = [row.sha256 for row in results]
        download_id_list = [row.download_id for row in results]

        self.video_filehash_lib = {
            sha256_list[i]: download_id_list[i] for i in range(len(download_id_list))
        }

    def prepare_video_imagehashes_lib(self) -> None:
        with self.db.with_session() as session:
            image_hashes_results = (
                session.query(
                    SubtaskAnnotationVideoImageHashDB.download_id,
                    SubtaskAnnotationVideoImageHashDB.image_hashes,
                )
                .filter(
                    SubtaskAnnotationVideoImageHashDB.image_hash_status == ImageHashStatus.SUCCESS
                )  # 可选：确保 sha256 存在
                .all()
            )

            frame_num_results = session.query(
                SubtaskAnnotationVideoDownloadDB.id,
                SubtaskAnnotationVideoDownloadDB.frame_num,
            ).all()

        image_hashes_list = [pickle.loads(row.image_hashes) for row in image_hashes_results]
        download_id_list = [row.download_id for row in image_hashes_results]

        video_imagehashes = {
            download_id_list[i]: image_hashes_list[i] for i in range(len(download_id_list))
        }
        frame_num_list = [row.frame_num for row in frame_num_results]
        download_id_list = [row.id for row in frame_num_results]

        frame_num_dict = {
            download_id_list[i]: frame_num_list[i] for i in range(len(download_id_list))
        }

        self.video_imagehashes_lib = self._sort_video_imagehashes_from_frame_num(
            video_imagehashes, frame_num_dict=frame_num_dict
        )

    def _get_video_lengths(self) -> dict[int, int]:
        with self.db.with_session() as session:
            results = (
                session.query(
                    SubtaskAnnotationVideoDownloadDB.id,
                    SubtaskAnnotationVideoDownloadDB.frame_num,
                )
                .filter(SubtaskAnnotationVideoDownloadDB.download_status == DownloadStatus.SUCCESS)
                .all()
            )

        download_id_list = [row.download_id for row in results]
        frame_num_list = [row.frame_num for row in results]

        return {download_id_list[i]: frame_num_list[i] for i in range(len(download_id_list))}

    def _sort_video_imagehashes_from_frame_num(
        self,
        video_imagehashes: dict[int, list[imagehash.ImageHash]],
        frame_num_dict: dict[int, int],
    ) -> dict[int, list[tuple[int, list[imagehash.ImageHash]]]]:
        result = defaultdict(list)
        for idx, frame_num in frame_num_dict.items():
            if idx in video_imagehashes:
                result[frame_num].append((idx, video_imagehashes[idx]))

        return dict(result)

    def _match_video_file_hash(self, hash: str, file_hash_lib: dict[str, int]) -> int | None:
        if hash in file_hash_lib:
            return file_hash_lib[hash]
        return None

    def _match_video_image_hashes(
        self,
        frame_num: int,
        image_phashes: list[imagehash.ImageHash],
        video_image_phashes_lib: dict[int, list[tuple[int, list[imagehash.ImageHash]]]],
        threashold: float = 0.95,
    ) -> int | None:
        if frame_num not in video_image_phashes_lib:
            return None

        min_avg_dist = 1
        matched_id = None

        for item in video_image_phashes_lib[frame_num]:
            id = item[0]
            phashes = item[1]
            if len(image_phashes) != len(phashes):
                continue

            dist = 0
            hash_num = 0
            for s_phash, t_phash in zip(image_phashes, phashes):
                if s_phash is None or t_phash is None:
                    continue
                dist += (s_phash - t_phash) / len(t_phash)
                hash_num += 1

            if hash_num == 0:
                continue
            avg_dist = dist / hash_num
            if avg_dist < min_avg_dist:
                min_avg_dist = avg_dist
                matched_id = id

        if matched_id is None:
            return None
        if 1 - min_avg_dist < threashold:
            return None

        return matched_id

    def _match_video(
        self,
        video_path: str | Path,
    ) -> int | None:
        video_path = Path(video_path).expanduser().absolute()
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}.")

        if video_path.is_dir():
            raise ValueError(f"{video_path} is a directory.")

        sha256_hex = self._compute_sha256(video_path)

        if sha256_hex in self.video_filehash_lib:
            return self.video_filehash_lib[sha256_hex]

        frame_num = self._get_frame_num(video_path=video_path)
        frame_indices = gen_frame_indices_from_framenum(frame_num=frame_num)

        image_hashes = extract_frame_phashes_ffmpeg(
            video_path=video_path, frame_indices=frame_indices
        )

        return self._match_video_image_hashes(
            frame_num,
            image_phashes=image_hashes,
            video_image_phashes_lib=self.video_imagehashes_lib,
        )

    def sync_dataset_annotation_corresponding_task(self) -> None:
        with self.db.with_session() as session:
            query = (
                session.query(LeFormatConvertDB.dataset_uuid, LeFormatConvertDB.convert_path)
                .filter(LeFormatConvertDB.convert_status == TaskStatus.COMPLETED)
                .filter(
                    ~session.query(DatasetAnnotationCorrespondingDB)
                    .filter(
                        DatasetAnnotationCorrespondingDB.dataset_uuid
                        == LeFormatConvertDB.dataset_uuid
                    )
                    .exists()
                )
            )
            tasks = query.all()
            for task in tasks:
                self._upsert_dataset_annotation_corresponding_status(
                    session, task.dataset_uuid, TaskStatus.PENDING
                )

            self.logger.info(f"Sync {len(tasks)} subtask annotation corresponding tasks to process")

    def _gen_one_dataset_subtask_annotation_corresponding_task(
        self, ds_uuid: str | None = None
    ) -> tuple[str, str | Path]:
        with self.db.with_session() as session:
            if ds_uuid is None:
                query = session.query(DatasetAnnotationCorrespondingDB).filter(
                    DatasetAnnotationCorrespondingDB.corresponding_status == TaskStatus.PENDING
                )
            else:
                query = session.query(DatasetAnnotationCorrespondingDB).filter(
                    DatasetAnnotationCorrespondingDB.corresponding_status == TaskStatus.PENDING,
                    DatasetAnnotationCorrespondingDB.dataset_uuid == ds_uuid,
                )
            item = query.first()
            if not item:
                self.logger.warning(f"No subtask annotation task found for dataset {ds_uuid}")
                return None, None
            ds_uuid = item.dataset_uuid
            self._upsert_dataset_annotation_corresponding_status(
                session, ds_uuid, TaskStatus.PROCESSING
            )
            query = session.query(LeFormatConvertDB).filter(
                LeFormatConvertDB.dataset_uuid == ds_uuid
            )
            item = query.first()

            return ds_uuid, item.convert_path

    def _get_annotationid_from_downloadid(self, download_id: int) -> int | None:
        with self.db.with_session() as session:
            return (
                session.query(SubtaskAnnotationJsonDB.id)
                .join(SubtaskAnnotationVideoDownloadDB.annotation)  # 通过关系 join
                .filter(SubtaskAnnotationVideoDownloadDB.id == download_id)
                .scalar()  # 返回单个值
            )

    def _get_epidx_annoidx_corresponding(self, session: Session, ds_uuid: str, ep_idx: int) -> int:
        return (
            session.query(EpisodeSubtaskAnnotationCorrespondingDB.annotation_json_id)
            .filter(
                EpisodeSubtaskAnnotationCorrespondingDB.dataset_uuid == ds_uuid,
                EpisodeSubtaskAnnotationCorrespondingDB.episode_idx == ep_idx,
            )
            .first()
        )

    def _upsert_epidx_annoidx_corresponding(
        self, session: Session, ds_uuid: str, ep_idx: int, annotation_idx: int
    ) -> None:
        record = (
            session.query(EpisodeSubtaskAnnotationCorrespondingDB)
            .filter(
                EpisodeSubtaskAnnotationCorrespondingDB.dataset_uuid == ds_uuid,
                EpisodeSubtaskAnnotationCorrespondingDB.episode_idx == ep_idx,
            )
            .first()
        )

        if record:
            record.annotation_json_id = annotation_idx
        else:
            record = EpisodeSubtaskAnnotationCorrespondingDB(
                dataset_uuid=ds_uuid, episode_idx=ep_idx, annotation_json_id=annotation_idx
            )
        session.add(record)

        session.commit()

    def _upsert_dataset_annotation_corresponding_status(
        self,
        session: Session,
        ds_uuid: str,
        status: TaskStatus = TaskStatus.PENDING,
        error_epindices: list[int] = [],
    ) -> None:
        if error_epindices:
            status = TaskStatus.FAILED
            err_msg = f"Unmatched episode indices: {error_epindices}"
        else:
            err_msg = ""

        item = (
            session.query(DatasetAnnotationCorrespondingDB)
            .filter(DatasetAnnotationCorrespondingDB.dataset_uuid == ds_uuid)
            .first()
        )

        if item:
            item.corresponding_status = status
            item.error_msg = err_msg
        else:
            item = DatasetAnnotationCorrespondingDB(
                dataset_uuid=ds_uuid, corresponding_status=status, error_msg=err_msg
            )

        session.add(item)
        session.commit()

    def _correspond_dataset_subtask_annotation(self, ds_uuid: str, ds_path: str | Path) -> None:
        ds_path: Path = Path(ds_path).expanduser().absolute()
        if not ds_path.exists():
            raise ValueError(f"{ds_path} not exists")
        if ds_path.is_file():
            raise ValueError(f"{ds_path} is a file")

        video_dir = ds_path / "videos"
        if not video_dir.exists():
            raise ValueError(f"{video_dir} not exists")

        chunks = [dir for dir in list(video_dir.iterdir()) if dir.is_dir()]

        chunk_subdirs = [dir for dir in list(chunks[0].iterdir()) if dir.is_dir()]

        camera_videos = {
            dir.name: sorted(list(dir.glob("*.mp4"))) for dir in chunk_subdirs if dir.is_dir()
        }

        temp_camera_name = next(iter(camera_videos))

        camera_labels = {camera_name: False for camera_name in camera_videos.keys()}

        annotation_id_dict = {}
        success_ep_set = set()
        failed_ep_set = set()
        pbar = tqdm(
            range(len(camera_videos[temp_camera_name])), desc="对齐Episode标注文件", unit="episode"
        )
        for ep_idx in pbar:
            with self.db.with_session() as session:
                if self._get_epidx_annoidx_corresponding(
                    session=session, ds_uuid=ds_uuid, ep_idx=ep_idx
                ):
                    continue
            video_download_id = None
            for camera_name in camera_videos.keys():
                if not camera_labels[camera_name]:
                    continue
                video_download_id = self._match_video(camera_videos[camera_name][ep_idx])
                if video_download_id:
                    # Found matched video
                    break
                camera_labels[camera_name] = False

            if not video_download_id:
                for camera_name in camera_videos.keys():
                    video_download_id = self._match_video(camera_videos[camera_name][ep_idx])
                    if video_download_id:
                        # Found matched video
                        camera_labels[camera_name] = True
                        break

            if video_download_id:
                annotation_id = self._get_annotationid_from_downloadid(video_download_id)
                annotation_id_dict[ep_idx] = annotation_id
                with self.db.with_session() as session:
                    self._upsert_epidx_annoidx_corresponding(
                        session=session,
                        ds_uuid=ds_uuid,
                        ep_idx=ep_idx,
                        annotation_idx=annotation_id,
                    )
                success_ep_set.add(ep_idx)
            if not video_download_id:
                failed_ep_set.add(ep_idx)
                pbar.set_postfix(
                    {
                        "失败数": len(failed_ep_set),
                    }
                )

        error_epindices = [
            ep_idx
            for ep_idx in range(len(camera_videos[temp_camera_name]))
            if ep_idx not in success_ep_set
        ]
        if error_epindices:
            status = TaskStatus.FAILED
        else:
            status = TaskStatus.COMPLETED
        with self.db.with_session() as session:
            self._upsert_dataset_annotation_corresponding_status(
                session=session,
                ds_uuid=ds_uuid,
                status=status,
                error_epindices=error_epindices,
            )

    def correspond_dataset_subtask_annotations(self, ds_uuids: list[str] | None = None) -> None:
        self.logger.info("Loading video file hashes lib ...")
        self.prepare_video_filehash_lib()
        self.logger.info("Loading video image hashes lib ...")
        self.prepare_video_imagehashes_lib()
        if ds_uuids is None:
            while True:
                task = self._gen_one_dataset_subtask_annotation_corresponding_task()
                if not task:
                    self.logger.info("All task completed, no task to process")
                    break

                uuid = task[0]
                convert_path = task[1]

                self.logger.info(f"Corresponding subtask annotation for dataset: {convert_path}")
                if convert_path is None:
                    raise ValueError("Please specify the convert path")
                self._correspond_dataset_subtask_annotation(ds_uuid=uuid, ds_path=convert_path)

            return

        for ds_uuid in ds_uuids:
            uuid, convert_path = self._gen_one_dataset_subtask_annotation_corresponding_task(
                ds_uuid=ds_uuid
            )
            if uuid is None:
                self.logger.warning("Failed to generate corresponding task for dataset: {ds_uuid}")
                continue
            self._correspond_dataset_subtask_annotation(ds_uuid=uuid, ds_path=convert_path)

    def _upsert_dataset_annotation_content_status(
        self, session: Session, ds_uuid: str, status: TaskStatus, err_msg: str = None
    ) -> None:
        item: DatasetSubtaskAnnotationContentStatusDB = (
            session.query(DatasetSubtaskAnnotationContentStatusDB)
            .filter(DatasetSubtaskAnnotationContentStatusDB.dataset_uuid == ds_uuid)
            .first()
        )
        if item:
            item.dataset_uuid = ds_uuid
            item.status = status
            item.err_message = err_msg
        else:
            item = DatasetSubtaskAnnotationContentStatusDB(
                dataset_uuid=ds_uuid, status=status, err_message=err_msg
            )
        session.add(item)
        session.commit()

    def sync_dataset_subtask_annotation_content(self) -> None:
        with self.db.with_session() as session:
            query = (
                session.query(DatasetAnnotationCorrespondingDB)
                .filter(
                    DatasetAnnotationCorrespondingDB.corresponding_status == TaskStatus.COMPLETED
                )
                .filter(
                    ~session.query(DatasetSubtaskAnnotationContentStatusDB)
                    .filter(
                        DatasetSubtaskAnnotationContentStatusDB.dataset_uuid
                        == DatasetAnnotationCorrespondingDB.dataset_uuid
                    )
                    .exists()
                )
            )
            items = query.all()
            for item in items:
                self._upsert_dataset_annotation_content_status(
                    session, ds_uuid=item.dataset_uuid, status=TaskStatus.PENDING
                )

            self.logger.info(f"Sync {len(items)} dataset subtask annotation content tasks")

    def _gen_one_dataset_subtask_annotation_content_task(
        self,
    ) -> str | None:
        with self.db.with_session() as session:
            task = (
                session.query(DatasetSubtaskAnnotationContentStatusDB)
                .filter(DatasetSubtaskAnnotationContentStatusDB.status == TaskStatus.PENDING)
                .first()
            )
            if not task:
                self.logger.info("No pending dataset subtask annotation content task")
                return None

            self._upsert_dataset_annotation_content_status(
                session=session, ds_uuid=task.dataset_uuid, status=TaskStatus.PROCESSING
            )
            return task.dataset_uuid

    def _upsert_dataset_subtask_annotation_content(
        self,
        session: Session,
        ds_uuid: str,
        ori_content: str,
        new_content: str | None = None,
    ) -> None:
        item = (
            session.query(DatasetSubtaskAnnotationContentDB)
            .filter(DatasetSubtaskAnnotationContentDB.dataset_uuid == ds_uuid)
            .filter(DatasetSubtaskAnnotationContentDB.ori_content == ori_content)
            .first()
        )
        if item is None:
            item = DatasetSubtaskAnnotationContentDB(
                dataset_uuid=ds_uuid,
                ori_content=ori_content,
                new_content=new_content,
            )
            session.add(item)
            session.commit()
        else:
            item.new_content = new_content
            session.commit()

    def _get_dataset_subtask_annotation_json_dict(
        self,
        ds_uuid: str,
    ) -> dict[int, str]:
        with self.db.with_session() as session:
            results = (
                session.query(
                    EpisodeSubtaskAnnotationCorrespondingDB.episode_idx,
                    SubtaskAnnotationJsonDB.json_content,
                )
                .join(
                    SubtaskAnnotationJsonDB,
                    SubtaskAnnotationJsonDB.id
                    == EpisodeSubtaskAnnotationCorrespondingDB.annotation_json_id,
                )
                .filter(EpisodeSubtaskAnnotationCorrespondingDB.dataset_uuid == ds_uuid)
                .order_by(
                    EpisodeSubtaskAnnotationCorrespondingDB.episode_idx
                )  # 按 episode_idx 排序
                .all()
            )
            return {item.episode_idx: item.json_content for item in results}

    # 提取为字符串列表

    # def _get_dataset_subtask_annotation_set(
    #     self,
    #     ds_uuid: str,
    # ) -> set[str]:
    #     annotation_set = set()
    #     json_list = self._get_dataset_subtask_annotation_json_dict(ds_uuid=ds_uuid)
    #     for json_item in json_list:
    #         video_labels = json_item["videoLabels"]
    #         print(video_labels)
    #         for video_label in video_labels:
    #             annotations = video_label.get("timelinelabels", [])
    #             for annotation in annotations:
    #                 annotation_set.add(annotation)

    #     return annotation_set

    # def optimize_dataset_subtask_annotation_content(
    #     self,
    #     ds_uuid: str,
    #     api_key: str,
    # ) -> dict[str, str]:
    #     """
    #     Generate dataset subtask annotation content.
    #     """
    #     annotation_set = self._get_dataset_subtask_annotation_set(ds_uuid=ds_uuid)
    #     from .subtask_annotation_optimization import optimize_annotation

    #     return optimize_annotation(annotation_set=annotation_set, ds_api_key=api_key)

    def _upsert_episode_range_subtask_annotation(
        self,
        ds_uuid: str,
        episode_idx: int,
        range_from_frame_idx: int,
        range_to_frame_idx: int,
        annotation: str,
    ) -> None:
        with self.db.with_session() as session:
            item = (
                session.query(EpisodeRangeSubtaskAnnotationDB)
                .filter(
                    EpisodeRangeSubtaskAnnotationDB.dataset_uuid == ds_uuid,
                    EpisodeRangeSubtaskAnnotationDB.episode_id == episode_idx,
                    EpisodeRangeSubtaskAnnotationDB.range_from_frame_idx == range_from_frame_idx,
                    EpisodeRangeSubtaskAnnotationDB.range_to_frame_idx == range_to_frame_idx,
                )
                .first()
            )
            if item is None:
                item = EpisodeRangeSubtaskAnnotationDB(
                    dataset_uuid=ds_uuid,
                    episode_id=episode_idx,
                    range_from_frame_idx=range_from_frame_idx,
                    range_to_frame_idx=range_to_frame_idx,
                    subtask_annotation=annotation,
                )
            else:
                item.dataset_uuid = ds_uuid
                item.episode_id = episode_idx
                item.range_from_frame_idx = range_from_frame_idx
                item.range_to_frame_idx = range_to_frame_idx
                item.subtask_annotation = annotation

            session.add(item)
            session.commit()

    def gen_dataset_optimized_subtask_annotation_content(
        self,
        ds_uuid: str,
        api_key: str,
    ) -> dict[str, str]:
        """
        Generate dataset subtask annotation content.
        """
        episode_annotation_json_dict = self._get_dataset_subtask_annotation_json_dict(
            ds_uuid=ds_uuid
        )
        annotation_set = set()
        for json_str in episode_annotation_json_dict.values():
            for range_label in json.loads(json_str):
                annotations = range_label.get("timelinelabels", [])
                for annotation in annotations:
                    annotation_set.add(annotation)

        from .subtask_annotation_optimization import optimize_annotation

        optimized_annotation_dict = optimize_annotation(
            annotation_set=annotation_set, ds_api_key=api_key
        )

        for ep_idx, json_str in episode_annotation_json_dict.items():
            for range_label in json.loads(json_str):
                annotations = range_label.get("timelinelabels", [])
                ranges = range_label.get("ranges", [])
                try:
                    range = ranges[0]
                    annotation = annotations[0]
                except IndexError:
                    raise ValueError(
                        f"dataset {ds_uuid} has invalid annotation json, ranges or timelinelabels are empty"
                    )
                start_frame_idx = range["start"] - 1
                end_frame_idx = range["end"] - 1
                optimized_annotation = optimized_annotation_dict[annotation]
                self._upsert_episode_range_subtask_annotation(
                    ds_uuid,
                    ep_idx,
                    start_frame_idx,
                    end_frame_idx,
                    optimized_annotation,
                )

    def process_dataset_subtask_annotation(self, api_key: str) -> None:
        while True:
            ds_uuid = self._gen_one_dataset_subtask_annotation_content_task()
            if ds_uuid is None:
                break
            err_msg = ""
            try:
                self.gen_dataset_optimized_subtask_annotation_content(ds_uuid, api_key=api_key)
                status = TaskStatus.COMPLETED
            except Exception as e:
                err_msg = f"{ds_uuid} gen_dataset_optimized_subtask_annotation_content error: {e}"
                status = TaskStatus.FAILED

            with self.db.with_session() as session:
                self._upsert_dataset_annotation_content_status(
                    session=session,
                    ds_uuid=ds_uuid,
                    status=status,
                    err_msg=err_msg,
                )
