import concurrent.futures
import json
import logging
import os
import pickle
import re
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
from sqlalchemy import not_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from tqdm import tqdm

from robocoin_dataset.annotation.subtask_annotion.subtask_annotation_process import (
    validate_annotation_json,
)
from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DlVideoDB,
    LeFormatConvertDB,
    LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationDB,
    LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationStatusDB,
    LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationDB,
    LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationStatusDB,
    LeformatDatasetEpisodeSubtaskRangeAnnotationEmbeddingStatusDB,
    LeformatEpisodeUrlVideoMatchDB,
    LeformatEpisodeUrlVideoMatchStatusDB,
    LeformatEpisodeVideoHashDB,
    LeformatEpisodeVideoHashStatusDB,
    TaskStatus,
    UrlVideoStAnnotationDB,
)

FRAME_SAMPLE_NUM = 10


def compute_sha256(filepath: str | Path) -> str:
    """计算文件的 SHA-256 哈希值"""
    import hashlib

    hasher = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        raise e


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

    def _get_convert_path(self, dataset_uuid: str) -> str:
        with self.db.with_session() as session:
            item = (
                session.query(LeFormatConvertDB)
                .filter(LeFormatConvertDB.dataset_uuid == dataset_uuid)
                .first()
            )
            if item:
                return item.convert_path
            return None

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
        using_file_hash: bool = True,
        using_image_hashes: bool = True,
    ) -> int | None:
        video_path = Path(video_path).expanduser().absolute()
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}.")

        if video_path.is_dir():
            raise ValueError(f"{video_path} is a directory.")

        if using_file_hash:
            try:
                sha256_hex = compute_sha256(video_path)

                if sha256_hex in self.video_filehash_lib:
                    return self.video_filehash_lib[sha256_hex]
            except Exception as e:
                self.logger.warning(f"Failed to compute sha256 for {video_path}: {e}")

        if using_image_hashes:
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
        return None

    def _match_video_with_hash(
        self, file_hash: str, frame_num: int, image_hashes: list[imagehash.ImageHash]
    ) -> int | None:
        if file_hash in self.video_filehash_lib:
            return self.video_filehash_lib[file_hash]
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
        self, convert_path: str | None = None
    ) -> tuple[str, str | Path]:
        with self.db.with_session() as session:
            if convert_path is None:
                query = session.query(DatasetAnnotationCorrespondingDB).filter(
                    DatasetAnnotationCorrespondingDB.corresponding_status == TaskStatus.PENDING
                )
            else:
                query = session.query(DatasetAnnotationCorrespondingDB).filter(
                    DatasetAnnotationCorrespondingDB.corresponding_status == TaskStatus.PENDING,
                    DatasetAnnotationCorrespondingDB.convert_path == convert_path,
                )
            item = query.first()
            if not item:
                self.logger.warning(f"No subtask annotation task found for dataset {convert_path}")
                return None, None
            convert_path = item.dataset_uuid
            self._upsert_dataset_annotation_corresponding_status(
                session, convert_path, TaskStatus.PROCESSING
            )
            query = session.query(LeFormatConvertDB).filter(
                LeFormatConvertDB.dataset_uuid == convert_path
            )
            item = query.first()

            return convert_path, item.convert_path

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
            query = session.query(LeFormatConvertDB.convert_path).filter(
                LeFormatConvertDB.dataset_uuid == ds_uuid
            )
            item = DatasetAnnotationCorrespondingDB(
                convert_path=query.first().convert_path,
                dataset_uuid=ds_uuid,
                corresponding_status=status,
                error_msg=err_msg,
            )

        session.add(item)
        session.commit()

    # def _correspond_dataset_subtask_annotation(
    #     self,
    #     ds_uuid: str,
    #     ds_path: str | Path,
    #     using_file_hash: bool = True,
    #     using_image_hash: bool = True,
    # ) -> None:
    #     ds_path: Path = Path(ds_path).expanduser().absolute()
    #     if not ds_path.exists():
    #         raise ValueError(f"{ds_path} not exists")
    #     if ds_path.is_file():
    #         raise ValueError(f"{ds_path} is a file")

    #     video_dir = ds_path / "videos"
    #     if not video_dir.exists():
    #         raise ValueError(f"{video_dir} not exists")

    #     chunks = [dir for dir in list(video_dir.iterdir()) if dir.is_dir()]

    #     chunk_subdirs = [dir for dir in list(chunks[0].iterdir()) if dir.is_dir()]

    #     camera_videos = {
    #         dir.name: sorted(list(dir.glob("*.mp4"))) for dir in chunk_subdirs if dir.is_dir()
    #     }

    #     temp_camera_name = next(iter(camera_videos))

    #     camera_labels = {camera_name: False for camera_name in camera_videos.keys()}

    #     annotation_id_dict = {}
    #     success_ep_set = set()
    #     failed_ep_set = set()
    #     pbar = tqdm(
    #         range(len(camera_videos[temp_camera_name])), desc="对齐Episode标注文件", unit="episode"
    #     )
    #     for ep_idx in pbar:
    #         with self.db.with_session() as session:
    #             if self._get_epidx_annoidx_corresponding(
    #                 session=session, ds_uuid=ds_uuid, ep_idx=ep_idx
    #             ):
    #                 continue
    #         video_download_id = None
    #         for camera_name in camera_videos.keys():
    #             if not camera_labels[camera_name]:
    #                 continue
    #             video_download_id = self._match_video(
    #                 camera_videos[camera_name][ep_idx],
    #                 using_file_hash=using_file_hash,
    #                 using_image_hashes=using_image_hash,
    #             )
    #             if video_download_id:
    #                 # Found matched video
    #                 break
    #             camera_labels[camera_name] = False

    #         if not video_download_id:
    #             for camera_name in camera_videos.keys():
    #                 video_download_id = self._match_video(
    #                     camera_videos[camera_name][ep_idx],
    #                     using_file_hash=using_file_hash,
    #                     using_image_hashes=using_image_hash,
    #                 )
    #                 if video_download_id:
    #                     # Found matched video
    #                     camera_labels[camera_name] = True
    #                     break

    #         if video_download_id:
    #             annotation_id = self._get_annotationid_from_downloadid(video_download_id)
    #             annotation_id_dict[ep_idx] = annotation_id
    #             with self.db.with_session() as session:
    #                 self._upsert_epidx_annoidx_corresponding(
    #                     session=session,
    #                     ds_uuid=ds_uuid,
    #                     ep_idx=ep_idx,
    #                     annotation_idx=annotation_id,
    #                 )
    #             success_ep_set.add(ep_idx)
    #         if not video_download_id:
    #             failed_ep_set.add(ep_idx)
    #             pbar.set_postfix(
    #                 {
    #                     "失败数": len(failed_ep_set),
    #                 }
    #             )

    #     error_epindices = [
    #         ep_idx
    #         for ep_idx in range(len(camera_videos[temp_camera_name]))
    #         if ep_idx not in success_ep_set
    #     ]
    #     if error_epindices:
    #         status = TaskStatus.FAILED
    #     else:
    #         status = TaskStatus.COMPLETED
    #     with self.db.with_session() as session:
    #         self._upsert_dataset_annotation_corresponding_status(
    #             session=session,
    #             ds_uuid=ds_uuid,
    #             status=status,
    #             error_epindices=error_epindices,
    #         )

    # def correspond_dataset_subtask_annotations(
    #     self,
    #     ds_convert_paths: list[str] | None = None,
    #     using_file_hash: bool = True,
    #     using_image_hash: bool = True,
    # ) -> None:
    #     self.logger.info("Loading video file hashes lib ...")
    #     self.prepare_video_filehash_lib()
    #     self.logger.info("Loading video image hashes lib ...")
    #     self.prepare_video_imagehashes_lib()
    #     if ds_convert_paths is None:
    #         while True:
    #             task = self._gen_one_dataset_subtask_annotation_corresponding_task()
    #             if not task:
    #                 self.logger.info("All task completed, no task to process")
    #                 break

    #             uuid = task[0]
    #             convert_path = task[1]

    #             self.logger.info(f"Corresponding subtask annotation for dataset: {convert_path}")
    #             if convert_path is None:
    #                 raise ValueError("Please specify the convert path")
    #             self._correspond_dataset_subtask_annotation(
    #                 ds_uuid=uuid,
    #                 ds_path=convert_path,
    #                 using_file_hash=using_file_hash,
    #                 using_image_hash=using_image_hash,
    #             )

    #         return

    #     for convert_path in ds_convert_paths:
    #         uuid, convert_path = self._gen_one_dataset_subtask_annotation_corresponding_task(
    #             convert_path=convert_path
    #         )
    #         if uuid is None:
    #             self.logger.warning("Failed to generate corresponding task for dataset: {ds_uuid}")
    #             continue
    #         self._correspond_dataset_subtask_annotation(
    #             ds_uuid=uuid,
    #             ds_path=convert_path,
    #             using_file_hash=using_file_hash,
    #             using_image_hash=using_image_hash,
    #         )

    def sync_leformat_episode_video_hash_status(self) -> None:
        with self.db.with_session() as session:
            query = (
                session.query(LeFormatConvertDB.dataset_uuid, LeFormatConvertDB.convert_path)
                .filter(LeFormatConvertDB.convert_status == TaskStatus.COMPLETED)
                .filter(
                    ~session.query(LeFormatConvertDB)
                    .filter(
                        LeformatEpisodeVideoHashStatusDB.dataset_uuid
                        == LeFormatConvertDB.dataset_uuid
                    )
                    .exists()
                )
            )

            tasks = list(query.all())
            for ds_uuid, convert_path in tasks:
                self._upsert_leformat_episode_video_hash_status(
                    session=session,
                    ds_uuid=ds_uuid,
                    convert_path=convert_path,
                    status=TaskStatus.PENDING,
                )

    def _upsert_leformat_episode_video_hash(
        self,
        session: Session,
        ds_uuid: str,
        ep_idx: int,
        video_path: str,
        file_hash: str,
        frame_num: int,
        image_hashes: bytes,
    ) -> None:
        item = (
            session.query(LeformatEpisodeVideoHashDB)
            .filter(LeformatEpisodeVideoHashDB.dataset_uuid == ds_uuid)
            .filter(LeformatEpisodeVideoHashDB.video_path == video_path)
            .first()
        )
        if item is None:
            item = LeformatEpisodeVideoHashDB(
                dataset_uuid=ds_uuid,
                episode_idx=ep_idx,
                video_path=video_path,
                file_hash=file_hash,
                frame_num=frame_num,
                image_hashes=image_hashes,
            )
            session.add(item)
        else:
            item.file_hash = file_hash
            item.image_hashes = image_hashes

        session.commit()

    def _upsert_leformat_episode_video_hash_status(
        self,
        session: Session,
        ds_uuid: str,
        convert_path: str,
        status: TaskStatus,
    ) -> None:
        item = (
            session.query(LeformatEpisodeVideoHashStatusDB)
            .filter(LeformatEpisodeVideoHashStatusDB.dataset_uuid == ds_uuid)
            .filter(LeformatEpisodeVideoHashStatusDB.convert_path == convert_path)
        ).first()
        if item:
            item.status = status
        else:
            item = LeformatEpisodeVideoHashStatusDB(
                dataset_uuid=ds_uuid,
                convert_path=convert_path,
                status=status,
            )
            session.add(item)
        session.commit()

    def _gen_one_leformat_episode_video_hash_task(self) -> tuple[str, str]:
        """
        生成一个处理视频文件的任务。

        :return: (ds_uuid, convert_path, ep_idx, video_path)
        """
        with self.db.with_session() as session:
            item = (
                session.query(
                    LeformatEpisodeVideoHashStatusDB,
                )
                .filter(LeformatEpisodeVideoHashStatusDB.status == TaskStatus.PENDING)
                .first()
            )
            if item is None:
                return None
            self._upsert_leformat_episode_video_hash_status(
                session=session,
                ds_uuid=item.dataset_uuid,
                convert_path=item.convert_path,
                status=TaskStatus.PROCESSING,
            )
            return item.dataset_uuid, item.convert_path

    def generate_leformat_episode_video_hashes_threas_pool(self, num_workers: int = 8) -> None:
        """
        启动多个工作线程，并发计算所有待处理视频文件的 SHA256 哈希值。

        :param num_workers: 工作线程数量
        """
        self.sync_leformat_episode_video_hash_status()
        # 先统计总任务数
        # tuple = (ds_uuid, convert_path, ep_idx, video_path)
        tasks: list[tuple[str, int, str]] = []
        with self.db.with_session() as session:
            datasets_tasks = (
                session.query(
                    LeformatEpisodeVideoHashStatusDB.dataset_uuid,
                    LeformatEpisodeVideoHashStatusDB.convert_path,
                )
                .filter(LeformatEpisodeVideoHashStatusDB.status == TaskStatus.PENDING)
                .all()
            )

        self.logger.info(f"🚀 启动 {num_workers} 个Episode Video Hash及指纹计算线程...")
        # 创建进度条

        def process_item(item: tuple[str, int, str]) -> None:
            ds_uuid, ep_idx, video_path = item
            if video_path is None:
                return
            if not video_path.exists():
                return

            file_hash = compute_sha256(video_path)

            frame_num = self._get_frame_num(video_path=video_path)

            image_frame_indices = gen_frame_indices_from_framenum(frame_num=frame_num)
            phashes: list[imagehash.ImageHash] = extract_frame_phashes_ffmpeg(
                video_path=video_path, frame_indices=image_frame_indices
            )
            serialized_hashes = pickle.dumps(phashes)

            with self.db.with_session() as session:
                self._upsert_leformat_episode_video_hash(
                    session=session,
                    ds_uuid=ds_uuid,
                    video_path=str(video_path),
                    ep_idx=ep_idx,
                    file_hash=file_hash,
                    frame_num=frame_num,
                    image_hashes=serialized_hashes,
                )

        num_datasets = len(list(datasets_tasks))
        ds_pbar = tqdm(
            total=num_datasets, desc="🔐 计算数据集视频指纹哈希", unit="dataset", dynamic_ncols=True
        )
        while True:
            item = self._gen_one_leformat_episode_video_hash_task()
            if item is None:
                break
            ds_uuid, convert_path = item
            tasks = []

            pattern = re.compile(r"^episode_\d{6}\.mp4$")
            for video_path in Path(convert_path).expanduser().absolute().rglob("*.mp4"):
                if not pattern.match(video_path.name):
                    continue
                try:
                    ep_idx = int(video_path.with_suffix("").name.split("_")[-1])
                    tasks.append((ds_uuid, ep_idx, video_path))
                except Exception:  # noqa: PERF203
                    continue
            ep_pbar = tqdm(
                total=len(tasks),
                desc=f"🔐 启动数据集{convert_path}视频文件处理线程",
                unit="video",
                dynamic_ncols=True,
            )

            with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
                results = executor.map(process_item, tasks)
                for _ in results:
                    ep_pbar.update(1)

            with self.db.with_session() as session:
                self._upsert_leformat_episode_video_hash_status(
                    session=session,
                    ds_uuid=ds_uuid,
                    convert_path=convert_path,
                    status=TaskStatus.COMPLETED,
                )
            ds_pbar.update(1)

        self.logger.info("🎉 所有Episode Videos 文件Hash及视频指纹计算任务已完成！")

    def upsert_dl_video(
        self,
        session: Session,
        video_url: str,
        download_path: str = None,
        frame_num: int = None,
        file_hash: str = None,
        image_hashes: bytes = None,
        download_status: TaskStatus | None = None,
        file_hash_status: TaskStatus | None = None,
        image_hash_status: TaskStatus | None = None,
    ) -> DlVideoDB:
        # 如果状态未传入，默认保持 PENDING

        obj = session.query(DlVideoDB).filter_by(video_url=video_url).first()

        if obj is not None:
            # 存在：只更新传入的非 None 字段

            if download_path is not None:
                obj.download_path = download_path
            if frame_num is not None:
                obj.frame_num = frame_num
            if file_hash is not None:
                obj.file_hash = file_hash
            if image_hashes is not None:
                obj.image_hashes = image_hashes
            if download_status is not None:
                obj.download_status = download_status
            if file_hash_status is not None:
                obj.file_hash_status = file_hash_status
            if image_hash_status is not None:
                obj.image_hash_status = image_hash_status

        # 可选：更新时间戳字段（如果有）
        # obj.updated_at = datetime.utcnow()

        else:
            # 不存在：创建新对象
            obj = DlVideoDB(
                video_url=video_url,
                download_path=download_path,
                frame_num=frame_num,
                file_hash=file_hash,
                image_hashes=image_hashes,
                download_status=download_status,
                file_hash_status=file_hash_status,
                image_hash_status=image_hash_status,
            )
            session.add(obj)

        session.commit()
        return obj

    def _gen_url_video_download_path(self, video_url: str) -> Path:
        with self.db.with_session() as session:
            res = self.upsert_dl_video(session, video_url)
            dl_path = self.video_dl_dir / f"{res.id}.mp4"
            self.upsert_dl_video(
                session,
                video_url=res.video_url,
                download_path=str(dl_path),
                download_status=res.download_status,
                frame_num=res.frame_num,
                file_hash_status=res.file_hash_status,
                image_hash_status=res.image_hash_status,
                file_hash=res.file_hash,
                image_hashes=res.image_hashes,
            )
            return dl_path

    def upsert_url_video_st_annotation_if_not_exists(
        self,
        session: Session,
        video_url: str,
        start_frame_idx: int,
        end_frame_idx: int,
        annotation: str,
    ) -> tuple[UrlVideoStAnnotationDB, bool]:
        try:
            # 构造新记录
            new_record = UrlVideoStAnnotationDB(
                video_url=video_url,
                start_frame_idx=start_frame_idx,
                end_frame_idx=end_frame_idx,
                annotation=annotation,
            )
            session.add(new_record)
            session.flush()  # 触发数据库约束检查
            session.commit()
            return new_record, True  # 插入成功

        except IntegrityError:
            # 唯一约束冲突：记录已存在
            session.rollback()  # 回滚当前事务中的插入操作
            session.expunge_all()  # 清理未完成的对象

            # 查询已存在的记录
            existing = (
                session.query(UrlVideoStAnnotationDB)
                .filter_by(
                    video_url=video_url,
                    start_frame_idx=start_frame_idx,
                    end_frame_idx=end_frame_idx,
                    annotation=annotation,
                )
                .first()
            )
            return existing, False  # 已存在，未插入

    def enter_url_video_st_annotation_json_files(self) -> None:
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

                            else:
                                success = True

                        except Exception as e:
                            self.logger.error(f"❌ {file} is not a valid annotation json: {e}")
                            success = False

                        if success:
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
                                for range_annotation in episode["videoLabels"]:
                                    # 数据库中的帧索引从0开始, 并且使用左闭右开的区间表达
                                    # 原始标注文件使用了从1开始的帧索引，并且使用左闭右闭的区间表达，因此start帧序号需要减1
                                    st_frame_idx = range_annotation["ranges"][0]["start"] - 1
                                    end_frame_idx = range_annotation["ranges"][0]["end"]
                                    timeline_label = range_annotation["timelinelabels"][0]

                                    with self.db.with_session() as session:
                                        self.upsert_url_video_st_annotation_if_not_exists(
                                            session=session,
                                            video_url=video_url,
                                            start_frame_idx=st_frame_idx,
                                            end_frame_idx=end_frame_idx,
                                            annotation=timeline_label,
                                        )
                                self._gen_url_video_download_path(video_url=video_url)

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

    def _gen_download_task(self) -> tuple[str, str]:
        with self.db.with_session() as session:
            item: DlVideoDB = (
                session.query(DlVideoDB)
                .filter(DlVideoDB.download_status == TaskStatus.PENDING)
                .filter(DlVideoDB.download_path.isnot(None))
                .first()
            )

            if not item:
                self.logger.info(
                    "未找到状态为 PENDING 的下载任务，或所有任务对应的 JSON 记录已不存在。"
                )
                return None, None

            video_url = item.video_url
            download_path = item.download_path
            item.download_status = TaskStatus.PROCESSING
            session.commit()

            # 第二步：获取 download 对象并更新状态
            return video_url, download_path

    def _get_undownloaded_videos_num(self) -> int:
        with self.db.with_session() as session:
            return (
                session.query(DlVideoDB)
                .filter(DlVideoDB.download_status == TaskStatus.PENDING)
                .filter(DlVideoDB.download_path.isnot(None))
                .count()
            )

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

    def _submit_video_download_result(
        self, video_url: str, download_path: str, success: bool, frame_num: int = None
    ) -> None:
        with self.db.with_session() as session:
            item = (
                session.query(DlVideoDB)
                .filter(DlVideoDB.video_url == video_url)
                .with_for_update(skip_locked=True)
                .first()
            )
            if item:
                item.download_status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
                item.download_path = download_path
                item.frame_num = frame_num
                session.commit()

    def download_videos_multi_threads(self, num_workers: int = 8) -> None:
        """
        启动多个工作线程，并发下载所有待处理任务
        """

        undownloaded_videos_num = self._get_undownloaded_videos_num()
        if undownloaded_videos_num <= 0:
            self.logger.info("没有待处理的任务")
            return
        self.logger.info(f"🚀 启动 {num_workers} 个下载线程，下载{undownloaded_videos_num}个视频")

        pbar = tqdm(
            total=undownloaded_videos_num, desc="📥 下载进度", unit="file", dynamic_ncols=True
        )

        pbar_lock = threading.Lock()

        def _worker_download(worker_id: int) -> None:
            while True:
                # 获取任务
                video_url, download_path = self._gen_download_task()
                if video_url is None:
                    break  # 无任务了

                success = self._download_video(video_url, download_path)
                if success:
                    try:
                        frame_num = self._get_frame_num(download_path)
                    except Exception:
                        frame_num = None
                        success = False
                        self.logger.info(f"video decoding failed: {download_path}")

                self._submit_video_download_result(
                    video_url=video_url,
                    download_path=download_path,
                    success=success,
                    frame_num=frame_num,
                )

                # ✅ 更新进度条（线程安全）
                with pbar_lock:
                    pbar.set_postfix_str(f"Download {video_url}: {'✅' if success else '❌'}")
                    pbar.update(1)  # 增加1

                if not success:
                    self.logger.warning(f"Worker-{worker_id}: {video_url} 下载失败")

        threads: list[threading.Thread] = []
        for i in range(num_workers):
            t = threading.Thread(target=_worker_download, args=(i,), name=f"Downloader-{i}")
            t.start()
            threads.append(t)

        # 等待所有线程完成
        for t in threads:
            t.join()

        self.logger.info("🎉 所有下载任务已完成！")

    def _gen_downlod_video_file_hash_task(self) -> str:
        with self.db.with_session() as session:
            item: DlVideoDB = (
                session.query(DlVideoDB)
                .filter(DlVideoDB.download_status == TaskStatus.COMPLETED)
                .filter(DlVideoDB.download_path.isnot(None))
                .filter(DlVideoDB.file_hash_status == TaskStatus.PENDING)
                .first()
            )

            if not item:
                self.logger.info(
                    "未找到状态为 PENDING 的下载任务，或所有任务对应的 JSON 记录已不存在。"
                )
                return None

            download_path = item.download_path
            item.file_hash_status = TaskStatus.PROCESSING
            session.commit()

            # 第二步：获取 download 对象并更新状态
            return download_path

    def _get_file_unhashed_videos_num(self) -> int:
        with self.db.with_session() as session:
            return (
                session.query(DlVideoDB)
                .filter(DlVideoDB.download_status == TaskStatus.COMPLETED)
                .filter(DlVideoDB.download_path.isnot(None))
                .filter(DlVideoDB.file_hash_status == TaskStatus.PENDING)
                .count()
            )

    def _submit_video_file_hash_result(
        self, download_path: str, filehash: str | None = None
    ) -> None:
        with self.db.with_session() as session:
            item = (
                session.query(DlVideoDB)
                .filter(DlVideoDB.download_path == download_path)
                .with_for_update(skip_locked=True)
                .first()
            )

            if not item:
                self.logger.error(f"FileHash 任务不存在，download_path is: {download_path}")
                return

            if item.file_hash_status != TaskStatus.PROCESSING:
                self.logger.error(
                    f"FileHash 任务状态异常，download_path: {download_path}，当前状态: {item.file_hash_status}"
                )
                return

            # 根据 filehash 是否有效决定状态
            if filehash and isinstance(filehash, str) and len(filehash.strip()) == 64:
                filehash = filehash.strip()
                item.file_hash = filehash
                item.file_hash_status = TaskStatus.COMPLETED
            else:
                item.file_hash_status = TaskStatus.FAILED

            try:
                session.commit()
            except Exception as e:
                session.rollback()
                self.logger.error(f"Failed to commit file hash for {item.id}: {e}")
                raise e

    def generate_url_video_file_hashes_multi_threads(self, num_workers: int = 8) -> None:
        """
        启动多个工作线程，并发计算所有待处理视频文件的 SHA256 哈希值。

        :param num_workers: 工作线程数量
        """
        # 先统计总任务数
        unhashed_videos_num = self._get_file_unhashed_videos_num()
        if unhashed_videos_num == 0:
            self.logger.info("没有待处理的文件哈希任务。")
            return

        self.logger.info(
            f"🚀 启动 {num_workers} 个计算线程，完成{unhashed_videos_num}个视频的文件Hash计算..."
        )

        # 创建进度条
        pbar = tqdm(
            total=unhashed_videos_num, desc="🔐 计算文件哈希", unit="file", dynamic_ncols=True
        )
        pbar_lock = threading.Lock()

        def _worker_hash(worker_id: int) -> None:
            while True:
                # 获取一个待处理的任务（线程安全）
                download_path = self._gen_downlod_video_file_hash_task()
                if download_path is None:
                    break  # 所有任务已完成
                download_path = Path(download_path).expanduser().absolute()

                # 计算 SHA256
                try:
                    if not download_path.exists():
                        raise FileNotFoundError(f"视频文件不存在: {download_path}")

                    sha256_hex = compute_sha256(download_path)
                    self.logger.debug(
                        f"Worker-{worker_id}: 成功计算哈希 → {sha256_hex[:8]}... ({download_path})"
                    )

                    # 提交成功结果
                    self._submit_video_file_hash_result(
                        download_path=str(download_path), filehash=sha256_hex
                    )

                except Exception as e:
                    self.logger.error(
                        f"Worker-{worker_id}: 计算哈希失败, File is {download_path}: {e}"
                    )
                    self._submit_video_file_hash_result(
                        download_path=str(download_path), filehash=None
                    )  # 标记失败

                # ✅ 线程安全更新进度条
                with pbar_lock:
                    status = "✅" if "sha256_hex" in locals() else "❌"
                    pbar.set_postfix_str(f"{download_path}: {status}")
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

    def _gen_downlod_video_image_hash_task(self) -> tuple[str, int]:
        with self.db.with_session() as session:
            item: DlVideoDB = (
                session.query(DlVideoDB)
                .filter(DlVideoDB.download_status == TaskStatus.COMPLETED)
                .filter(DlVideoDB.download_path.isnot(None))
                .filter(DlVideoDB.image_hash_status == TaskStatus.PENDING)
                .first()
            )

            if not item:
                self.logger.info(
                    "未找到状态为 PENDING 的下载任务，或所有任务对应的 JSON 记录已不存在。"
                )
                return None, None

            download_path = item.download_path
            frame_num = item.frame_num
            item.image_hash_status = TaskStatus.PROCESSING
            session.commit()

            # 第二步：获取 download 对象并更新状态
            return download_path, frame_num

    def _get_image_unhashed_videos_num(self) -> int:
        with self.db.with_session() as session:
            return (
                session.query(DlVideoDB)
                .filter(DlVideoDB.download_status == TaskStatus.COMPLETED)
                .filter(DlVideoDB.download_path.isnot(None))
                .filter(DlVideoDB.image_hash_status == TaskStatus.PENDING)
                .count()
            )

    def _submit_video_image_hash_result(
        self, download_path: str, imagehashes: str | None = None
    ) -> None:
        with self.db.with_session() as session:
            item = (
                session.query(DlVideoDB)
                .filter(DlVideoDB.download_path == download_path)
                .with_for_update(skip_locked=True)
                .first()
            )

            if not item:
                self.logger.error(f"FileHash 任务不存在，download_path is: {download_path}")
                return

            if item.image_hash_status != TaskStatus.PROCESSING:
                self.logger.error(
                    f"FileHash 任务状态异常，download_path: {download_path}，当前状态: {item.image_hash_status}"
                )
                return

            # 根据 filehash 是否有效决定状态
            if imagehashes:
                item.image_hashes = imagehashes
                item.image_hash_status = TaskStatus.COMPLETED
            else:
                item.image_hash_status = TaskStatus.FAILED

            try:
                session.commit()
            except Exception as e:
                session.rollback()
                self.logger.error(f"Failed to commit file hash for {id}: {e}")
                raise e

    def generate_url_video_image_hashes_multi_threads(self, num_workers: int = 8) -> None:
        # 先统计总任务数
        unhashed_videos_num = self._get_image_unhashed_videos_num()
        if unhashed_videos_num == 0:
            self.logger.info("没有待处理的视频指纹任务。")
            return

        self.logger.info(
            f"🚀 启动 {num_workers} 个计算线程，完成{unhashed_videos_num}个视频的指纹计算..."
        )

        # 创建进度条
        pbar = tqdm(
            total=unhashed_videos_num, desc="🔐 计算视频指纹", unit="video", dynamic_ncols=True
        )
        pbar_lock = threading.Lock()

        def _worker_hash(worker_id: int) -> None:
            while True:
                # 获取一个待处理的任务（线程安全）
                download_path, frame_num = self._gen_downlod_video_image_hash_task()
                if download_path is None or frame_num is None:
                    break  # 所有任务已完成
                frame_indices = gen_frame_indices_from_framenum(frame_num)
                download_path = Path(download_path).expanduser().absolute()

                # 计算 SHA256
                try:
                    phashes: list[imagehash.ImageHash] = extract_frame_phashes_ffmpeg(
                        video_path=download_path, frame_indices=frame_indices
                    )
                    serialized_hashes = pickle.dumps(phashes)
                    self.logger.debug(f"成功计算视频指纹  ({download_path})")

                    #     # 提交成功结果
                    self._submit_video_image_hash_result(
                        download_path=str(download_path), imagehashes=serialized_hashes
                    )

                except Exception as e:
                    self.logger.error(f"计算视频指纹失败 (download_path={download_path}): {e}")
                    self._submit_video_image_hash_result(
                        download_path=str(download_path), imagehashes=None
                    )  # 标记失败

                # ✅ 线程安全更新进度条
                with pbar_lock:
                    status = "✅" if "serialized_hashes" in locals() else "❌"
                    pbar.set_postfix_str(f"{download_path}: {status}")
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
        self.logger.info("🎉 所有视频指纹计算任务已完成！")

    def _upsert_leformat_episode_url_video_match_status(
        self,
        session: Session,
        dataset_uuid: str,
        convert_path: str,
        status: TaskStatus,
        unmatched_episode_indices: str | None = None,
    ) -> None:
        item = (
            session.query(LeformatEpisodeUrlVideoMatchStatusDB)
            .filter(LeformatEpisodeUrlVideoMatchStatusDB.dataset_uuid == dataset_uuid)
            .first()
        )
        if item:
            item.convert_path = convert_path
            if unmatched_episode_indices:
                item.unmatched_episode_indices = f"{unmatched_episode_indices}"
                item.status = TaskStatus.FAILED
            else:
                item.status = status

        else:
            if unmatched_episode_indices:
                item = LeformatEpisodeUrlVideoMatchStatusDB(
                    dataset_uuid=dataset_uuid,
                    convert_path=convert_path,
                    status=TaskStatus.FAILED,
                    unmatched_episode_indices=f"{unmatched_episode_indices}",
                )
            else:
                item = LeformatEpisodeUrlVideoMatchStatusDB(
                    dataset_uuid=dataset_uuid, convert_path=convert_path, status=status
                )
            session.add(item)
        session.commit()

    def _sync_leformat_episode_url_video_match_tasks(self) -> None:
        with self.db.with_session() as session:
            items = list(
                session.query(LeFormatConvertDB)
                .join(
                    LeformatEpisodeVideoHashStatusDB,
                    LeFormatConvertDB.dataset_uuid == LeformatEpisodeVideoHashStatusDB.dataset_uuid,
                )
                .filter(LeFormatConvertDB.convert_status == TaskStatus.COMPLETED)
                .filter(LeformatEpisodeVideoHashStatusDB.status == TaskStatus.COMPLETED)
                .filter(
                    # 不存在于 LeformatEpisodeUrlVideoMatchStatusDB 中
                    ~session.query(LeformatEpisodeUrlVideoMatchStatusDB)
                    .filter(
                        LeformatEpisodeUrlVideoMatchStatusDB.dataset_uuid
                        == LeFormatConvertDB.dataset_uuid
                    )
                    .exists()
                )
                .all()
            )
            for item in items:
                self._upsert_leformat_episode_url_video_match_status(
                    session,
                    dataset_uuid=item.dataset_uuid,
                    convert_path=item.convert_path,
                    status=TaskStatus.PENDING,
                )
            self.logger.info(f"同步 {len(items)} 个 leformat_episode_url_video_match 任务...")

    def _gen_one_leformat_episode_url_video_match_task(self) -> str:
        with self.db.with_session() as session:
            item = (
                session.query(LeformatEpisodeUrlVideoMatchStatusDB).filter(
                    LeformatEpisodeUrlVideoMatchStatusDB.status == TaskStatus.PENDING
                )
            ).first()

            if item:
                self._upsert_leformat_episode_url_video_match_status(
                    session,
                    dataset_uuid=item.dataset_uuid,
                    convert_path=item.convert_path,
                    status=TaskStatus.PROCESSING,
                )
                return item.dataset_uuid
            return None

    def prepare_video_filehash_lib(self) -> dict[str, str]:
        with self.db.with_session() as session:
            results = (
                session.query(
                    DlVideoDB,
                )
                .filter(DlVideoDB.file_hash_status == TaskStatus.COMPLETED)
                .filter(DlVideoDB.file_hash.isnot(None))  # 可选：确保 sha256 存在
                .all()
            )
        sha256_list = [row.file_hash for row in results]
        download_id_list = [row.id for row in results]

        return {sha256_list[i]: download_id_list[i] for i in range(len(download_id_list))}

    def prepare_video_imagehashes_lib(self) -> dict[str, list[str]]:
        with self.db.with_session() as session:
            items = (
                session.query(DlVideoDB)
                .filter(
                    DlVideoDB.image_hash_status == TaskStatus.COMPLETED
                )  # 可选：确保 sha256 存在
                .all()
            )

        image_hashes_list = [pickle.loads(row.image_hashes) for row in items]
        id_list = [row.id for row in items]

        video_imagehashes = {id_list[i]: image_hashes_list[i] for i in range(len(id_list))}
        frame_num_list = [row.frame_num for row in items]

        frame_num_dict = {id_list[i]: frame_num_list[i] for i in range(len(id_list))}

        return self._sort_video_imagehashes_from_frame_num(
            video_imagehashes, frame_num_dict=frame_num_dict
        )

    def _upsert_leformat_episode_url_video_match(
        self,
        session: Session,
        dataset_uuid: str,
        episode_idx: int,
        url_video_id: int,
    ) -> None:
        item = (
            session.query(LeformatEpisodeUrlVideoMatchDB)
            .filter(LeformatEpisodeUrlVideoMatchDB.dataset_uuid == dataset_uuid)
            .filter(LeformatEpisodeUrlVideoMatchDB.episode_idx == episode_idx)
            .first()
        )
        if item:
            item.url_video_id = url_video_id
        else:
            item = LeformatEpisodeUrlVideoMatchDB(
                dataset_uuid=dataset_uuid, episode_idx=episode_idx, url_video_id=url_video_id
            )
            session.add(item)
        session.commit()

    def _match_single_leformat_episode_with_url_video(
        self,
        dataset_uuid: str,
        file_hash_lib: dict[str, str],
        image_hashes_lib: dict[int, list[tuple[int, list[imagehash.ImageHash]]]],
    ) -> None:
        def list_to_range_string(nums: list[int]) -> str:
            if not nums:
                return "[]"

            nums = sorted(nums)
            result = []
            start = end = nums[0]

            for num in nums[1:]:
                if num == end + 1:
                    end = num  # 连续，扩展区间
                else:
                    result.append(f"{start}-{end}" if start != end else f"{start}")
                    start = end = num

            result.append(f"{start}-{end}" if start != end else f"{start}")
            return "[" + ",".join(result) + "]"

        with self.db.with_session() as session:
            query = session.query(LeformatEpisodeVideoHashDB).filter(
                LeformatEpisodeVideoHashDB.dataset_uuid == dataset_uuid
            )
            items = list(query.all())

        episode_file_hashes: dict[int, list[str]] = defaultdict(list)
        episode_image_hashes: dict[int, list[list[imagehash.ImageHash]]] = defaultdict(list)
        episode_frame_nums: dict[int, int] = defaultdict(int)
        for item in items:
            ep_idx = item.episode_idx
            file_hash = item.file_hash
            frame_num = item.frame_num
            video_image_hashes: list[imagehash.ImageHash] = pickle.loads(item.image_hashes)
            episode_file_hashes[ep_idx].append(file_hash)
            episode_image_hashes[ep_idx].append(video_image_hashes)
            episode_frame_nums[ep_idx] = frame_num

        for ep_idx in episode_file_hashes.keys():
            file_hashes = episode_file_hashes[ep_idx]
            ep_image_hashes = episode_image_hashes[ep_idx]

        unmatched_ep_idxs = []

        for ep_idx in episode_file_hashes.keys():
            file_hashes = episode_file_hashes[ep_idx]
            ep_image_hashes = episode_image_hashes[ep_idx]
            frame_num = episode_frame_nums[ep_idx]
            matched: bool = False
            for file_hash in file_hashes:
                file_hash_matched = self._match_video_file_hash(file_hash, file_hash_lib)
                if file_hash_matched:
                    with self.db.with_session() as session:
                        self._upsert_leformat_episode_url_video_match(
                            session, dataset_uuid, ep_idx, file_hash_matched
                        )
                    matched = True
                    break
            if not matched:
                for video_image_hashes in ep_image_hashes:
                    image_hash_matched = self._match_video_image_hashes(
                        frame_num=frame_num,
                        image_phashes=video_image_hashes,
                        video_image_phashes_lib=image_hashes_lib,
                    )
                    if image_hash_matched:
                        with self.db.with_session() as session:
                            self._upsert_leformat_episode_url_video_match(
                                session, dataset_uuid, ep_idx, image_hash_matched
                            )
                        matched = True
                        break
                if not matched:
                    unmatched_ep_idxs.append(ep_idx)
        compressed_unmatched_ep_idxs_str = list_to_range_string(unmatched_ep_idxs)

        if unmatched_ep_idxs:
            self._upsert_leformat_episode_url_video_match_status(
                session,
                dataset_uuid=dataset_uuid,
                convert_path=self._get_convert_path(dataset_uuid),
                status=TaskStatus.FAILED,
                unmatched_episode_indices=compressed_unmatched_ep_idxs_str,
            )
        else:
            self._upsert_leformat_episode_url_video_match_status(
                session,
                dataset_uuid=dataset_uuid,
                convert_path=self._get_convert_path(dataset_uuid),
                status=TaskStatus.COMPLETED,
            )

    def match_leformat_episode_with_url_video(self) -> None:
        self._sync_leformat_episode_url_video_match_tasks()
        file_hash_lib = self.prepare_video_filehash_lib()
        image_hashes_lib = self.prepare_video_imagehashes_lib()
        with self.db.with_session() as session:
            task_num = (
                session.query(LeformatEpisodeUrlVideoMatchStatusDB)
                .filter(LeformatEpisodeUrlVideoMatchStatusDB.status == TaskStatus.PENDING)
                .count()
            )
        pbar = tqdm(total=task_num, desc="Match leformat episode with url video", unit="task")

        try:
            processed_count = 0
            while True:
                dataset_uuid = self._gen_one_leformat_episode_url_video_match_task()
                if dataset_uuid is None:
                    break

                self._match_single_leformat_episode_with_url_video(
                    dataset_uuid, file_hash_lib=file_hash_lib, image_hashes_lib=image_hashes_lib
                )

                pbar.update(1)
                processed_count += 1

            pbar.close()

        except Exception as e:
            pbar.close()
            raise e

    def _upsert_leformat_dataset_episode_original_subtask_range_annotation_status(
        self,
        session: Session,
        dataset_uuid: str,
        convert_path: str | None = None,
        status: TaskStatus | None = None,
        err_msg: str | None = None,
    ) -> None:
        item = (
            session.query(LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationStatusDB)
            .filter(
                LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationStatusDB.dataset_uuid
                == dataset_uuid
            )
            .first()
        )

        if item:
            # 更新已有记录
            if convert_path is not None:
                item.convert_path = convert_path
            if status is not None:
                item.status = status
            if err_msg is not None:
                item.err_msg = err_msg
        else:
            # 插入新记录
            record = LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationStatusDB(
                dataset_uuid=dataset_uuid,
                convert_path=convert_path,
                status=status or TaskStatus.PENDING,
            )
            session.add(record)

        session.commit()

    def sync_leformat_dataset_episode_original_subtask_range_annotation_task_baai(self) -> None:
        with self.db.with_session() as session:
            items = (
                session.query(LeformatEpisodeUrlVideoMatchStatusDB)
                .filter(LeformatEpisodeUrlVideoMatchStatusDB.status == TaskStatus.COMPLETED)
                .filter(
                    not_(
                        session.query(LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationStatusDB)
                        .filter(
                            LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationStatusDB.dataset_uuid
                            == LeformatEpisodeUrlVideoMatchStatusDB.dataset_uuid
                        )
                        .exists()
                    )
                )
                .all()
            )

        for item in items:
            with self.db.with_session() as session:
                self._upsert_leformat_dataset_episode_original_subtask_range_annotation_status(
                    session,
                    dataset_uuid=item.dataset_uuid,
                    convert_path=item.convert_path,
                    status=TaskStatus.PENDING,
                )

        self.logger.info(
            f"sync {len(list(items))} leformat_dataset_episode_original_subtask_range_annotation_task_baai: {len(list(items))}"
        )

    def _gen_one_leformat_dataset_episode_original_subtask_range_annotation_task_baai(
        self,
    ) -> str | None:
        with self.db.with_session() as session:
            item: LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationStatusDB = (
                session.query(LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationStatusDB)
                .filter(
                    LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationStatusDB.status
                    == TaskStatus.PENDING
                )
                .first()
            )

            if item is None:
                return None

            self._upsert_leformat_dataset_episode_original_subtask_range_annotation_status(
                session,
                dataset_uuid=item.dataset_uuid,
                convert_path=item.convert_path,
                status=TaskStatus.PROCESSING,
            )
            return item.dataset_uuid

    def _upsert_leformat_dataset_episode_original_subtask_range_annotation_no_commit(
        self,
        session: Session,
        dataset_uuid: str,
        episode_idx: int,
        start_frame_idx: int,
        end_frame_idx: int,
        annotation: str,
    ) -> None:
        item = (
            session.query(LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationDB)
            .filter(
                LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationDB.dataset_uuid == dataset_uuid,
                LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationDB.episode_idx == episode_idx,
                LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationDB.start_frame_idx
                == start_frame_idx,
                LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationDB.end_frame_idx
                == end_frame_idx,
                LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationDB.annotation == annotation,
            )
            .first()
        )

        if not item:
            new_item = LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationDB(
                dataset_uuid=dataset_uuid,
                episode_idx=episode_idx,
                start_frame_idx=start_frame_idx,
                end_frame_idx=end_frame_idx,
                annotation=annotation,
            )
            session.add(new_item)
        else:
            item.annotation = annotation

    def _genearte_leformat_dataset_episode_original_subtask_range_annotation_baai(
        self, dataset_uuid: str
    ) -> None:
        with self.db.with_session() as session:
            ep_items = (
                session.query(LeformatEpisodeUrlVideoMatchDB)
                .filter(LeformatEpisodeUrlVideoMatchDB.dataset_uuid == dataset_uuid)
                .all()
            )

            if not ep_items:
                self.logger.error(f"No episode url video match for {dataset_uuid}")
                self._upsert_leformat_dataset_episode_original_subtask_range_annotation_status(
                    session,
                    dataset_uuid=dataset_uuid,
                    status=TaskStatus.FAILED,
                    err_msg="No episode url video match for this dataset",
                )
                return

        range_num = 0
        with self.db.with_session() as session:
            for ep_item in ep_items:
                ep_idx = ep_item.episode_idx
                url_video_id = ep_item.url_video_id
                url = session.query(DlVideoDB).filter(DlVideoDB.id == url_video_id).first()
                if url is None:
                    self.logger.warning(f"No url video for {url_video_id}")
                    continue

                url_range_annotation_items = list(
                    session.query(UrlVideoStAnnotationDB)
                    .filter(UrlVideoStAnnotationDB.video_url == url.video_url)
                    .all()
                )

                for url_range_annotation_item in url_range_annotation_items:
                    start_frame_idx = url_range_annotation_item.start_frame_idx
                    end_frame_idx = url_range_annotation_item.end_frame_idx
                    annotation = url_range_annotation_item.annotation
                    self._upsert_leformat_dataset_episode_original_subtask_range_annotation_no_commit(
                        session,
                        dataset_uuid=dataset_uuid,
                        episode_idx=ep_idx,
                        start_frame_idx=start_frame_idx,
                        end_frame_idx=end_frame_idx,
                        annotation=annotation,
                    )
                range_num += 1
            session.commit()

            self.logger.info(
                f"Generate {range_num} original subtask range annotation for dataset {dataset_uuid}"
            )
        with self.db.with_session() as session:
            self._upsert_leformat_dataset_episode_original_subtask_range_annotation_status(
                session,
                dataset_uuid=dataset_uuid,
                status=TaskStatus.COMPLETED,
            )

    def generate_leformat_datasets_original_range_subtask_annotation_baai(self) -> None:
        self.sync_leformat_dataset_episode_original_subtask_range_annotation_task_baai()
        with self.db.with_session() as session:
            task_num = (
                session.query(LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationStatusDB)
                .filter(
                    LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationStatusDB.status
                    == TaskStatus.PENDING
                )
                .count()
            )

        pbar = tqdm(total=task_num, desc="Match leformat episode with url video", unit="task")

        try:
            processed_count = 0
            while True:
                dataset_uuid = self._gen_one_leformat_dataset_episode_original_subtask_range_annotation_task_baai()
                if dataset_uuid is None:
                    break
                self._genearte_leformat_dataset_episode_original_subtask_range_annotation_baai(
                    dataset_uuid
                )
                pbar.update(1)
                processed_count += 1

            pbar.close()

        except Exception as e:
            pbar.close()
            raise e

    def _upsert_leformat_dataset_episode_optimized_subtask_range_annotation_status(
        self,
        session: Session,
        dataset_uuid: str,
        convert_path: str | None = None,
        status: TaskStatus | None = None,
        err_msg: str | None = None,
    ) -> None:
        item = (
            session.query(LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationStatusDB)
            .filter(
                LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationStatusDB.dataset_uuid
                == dataset_uuid
            )
            .first()
        )

        if item:
            # 更新已有记录
            if convert_path is not None:
                item.convert_path = convert_path
            if status is not None:
                item.status = status
            if err_msg is not None:
                item.err_msg = err_msg
        else:
            # 插入新记录
            record = LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationStatusDB(
                dataset_uuid=dataset_uuid,
                convert_path=convert_path,
                status=status or TaskStatus.PENDING,
                err_msg=err_msg,
            )
            session.add(record)

        session.commit()

    def sync_leformat_dataset_episode_optimized_subtask_range_annotation_task_baai(self) -> None:
        with self.db.with_session() as session:
            items = (
                session.query(LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationStatusDB)
                .filter(
                    LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationStatusDB.status
                    == TaskStatus.COMPLETED
                )
                .filter(
                    not_(
                        session.query(LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationStatusDB)
                        .filter(
                            LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationStatusDB.dataset_uuid
                            == LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationStatusDB.dataset_uuid
                        )
                        .exists()
                    )
                )
                .all()
            )

        for item in items:
            with self.db.with_session() as session:
                self._upsert_leformat_dataset_episode_optimized_subtask_range_annotation_status(
                    session,
                    dataset_uuid=item.dataset_uuid,
                    convert_path=item.convert_path,
                    status=TaskStatus.PENDING,
                )

        self.logger.info(
            f"sync {len(list(items))} leformat_dataset_episode_optimized_subtask_range_annotation_task_baai: {len(list(items))}"
        )

    def _gen_one_leformat_dataset_episode_optimized_subtask_range_annotation_task_baai(
        self,
    ) -> str | None:
        with self.db.with_session() as session:
            item: LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationStatusDB = (
                session.query(LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationStatusDB)
                .filter(
                    LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationStatusDB.status
                    == TaskStatus.PENDING
                )
                .first()
            )

            if item is None:
                return None

            self._upsert_leformat_dataset_episode_optimized_subtask_range_annotation_status(
                session,
                dataset_uuid=item.dataset_uuid,
                convert_path=item.convert_path,
                status=TaskStatus.PROCESSING,
            )
            return item.dataset_uuid

    def _upsert_leformat_dataset_episode_optimized_subtask_range_annotation_no_commit(
        self,
        session: Session,
        dataset_uuid: str,
        episode_idx: int,
        start_frame_idx: int,
        end_frame_idx: int,
        annotation: str,
    ) -> None:
        item = (
            session.query(LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationDB)
            .filter(
                LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationDB.dataset_uuid
                == dataset_uuid,
                LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationDB.episode_idx == episode_idx,
                LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationDB.start_frame_idx
                == start_frame_idx,
                LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationDB.end_frame_idx
                == end_frame_idx,
                LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationDB.annotation == annotation,
            )
            .first()
        )

        if not item:
            new_item = LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationDB(
                dataset_uuid=dataset_uuid,
                episode_idx=episode_idx,
                start_frame_idx=start_frame_idx,
                end_frame_idx=end_frame_idx,
                annotation=annotation,
            )
            session.add(new_item)
        else:
            item.annotation = annotation

    def _genearte_leformat_dataset_episode_optimized_subtask_range_annotation_baai(
        self, dataset_uuid: str, dp_api_key: str
    ) -> None:
        with self.db.with_session() as session:
            range_items = list(
                session.query(LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationDB)
                .filter(
                    LeformatDatasetEpisodeOriginalSubtaskRangeAnnotationDB.dataset_uuid
                    == dataset_uuid
                )
                .all()
            )

            if not range_items:
                self.logger.error(
                    f"No episode original subtask range annotation for {dataset_uuid}"
                )
                self._upsert_leformat_dataset_episode_optimized_subtask_range_annotation_status(
                    session,
                    dataset_uuid=dataset_uuid,
                    status=TaskStatus.FAILED,
                    err_msg="No episode original subtask range annotation found for this dataset",
                )
                return

        original_subtask_annotations = set([item.annotation for item in range_items])
        from .subtask_annotation_optimization import optimize_annotation

        try:
            optimized_annotation_dict = optimize_annotation(
                annotation_set=original_subtask_annotations, ds_api_key=dp_api_key
            )
        except Exception as e:
            self.logger.error(f"Failed to optimize annotation for {dataset_uuid}: {e}")
            self._upsert_leformat_dataset_episode_optimized_subtask_range_annotation_status(
                session,
                dataset_uuid=dataset_uuid,
                status=TaskStatus.FAILED,
                err_msg=str(e),
            )
            return

        with self.db.with_session() as session:
            for range_item in range_items:
                ep_idx = range_item.episode_idx
                start_frame_idx = range_item.start_frame_idx
                end_frame_idx = range_item.end_frame_idx
                annotation = optimized_annotation_dict[range_item.annotation]
                self._upsert_leformat_dataset_episode_optimized_subtask_range_annotation_no_commit(
                    session,
                    dataset_uuid=dataset_uuid,
                    episode_idx=ep_idx,
                    start_frame_idx=start_frame_idx,
                    end_frame_idx=end_frame_idx,
                    annotation=annotation,
                )
            self._upsert_leformat_dataset_episode_optimized_subtask_range_annotation_status(
                session,
                dataset_uuid=dataset_uuid,
                status=TaskStatus.COMPLETED,
            )
            session.commit()

            self._upsert_leformat_dataset_episode_optimized_subtask_range_annotation_status(
                session,
                dataset_uuid=dataset_uuid,
                status=TaskStatus.COMPLETED,
            )

    def generate_leformat_datasets_optimized_range_subtask_annotation_baai(
        self, dp_api_key: str
    ) -> None:
        self.sync_leformat_dataset_episode_optimized_subtask_range_annotation_task_baai()
        with self.db.with_session() as session:
            task_num = (
                session.query(LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationStatusDB)
                .filter(
                    LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationStatusDB.status
                    == TaskStatus.PENDING
                )
                .count()
            )

        pbar = tqdm(
            total=task_num,
            desc="Generate Episode Optimized Range Subtask Annotations for Datasets",
            unit="dataset",
        )

        try:
            processed_count = 0
            while True:
                dataset_uuid = self._gen_one_leformat_dataset_episode_optimized_subtask_range_annotation_task_baai()
                if dataset_uuid is None:
                    break
                self._genearte_leformat_dataset_episode_optimized_subtask_range_annotation_baai(
                    dataset_uuid, dp_api_key=dp_api_key
                )
                pbar.update(1)
                processed_count += 1

            pbar.close()

        except Exception as e:
            pbar.close()
            raise e

    def _upsert_leformat_dataset_episode_subtask_range_annotation_embedding_status(
        self,
        session: Session,
        dataset_uuid: str,
        convert_path: str | None = None,
        status: TaskStatus | None = None,
        err_msg: str | None = None,
    ) -> None:
        item = (
            session.query(LeformatDatasetEpisodeSubtaskRangeAnnotationEmbeddingStatusDB)
            .filter(
                LeformatDatasetEpisodeSubtaskRangeAnnotationEmbeddingStatusDB.dataset_uuid
                == dataset_uuid
            )
            .first()
        )

        if item:
            # 更新已有记录
            if convert_path is not None:
                item.convert_path = convert_path
            if status is not None:
                item.status = status
            if err_msg is not None:
                item.err_msg = err_msg
        else:
            # 插入新记录
            record = LeformatDatasetEpisodeSubtaskRangeAnnotationEmbeddingStatusDB(
                dataset_uuid=dataset_uuid,
                convert_path=convert_path,
                status=status or TaskStatus.PENDING,
                err_msg=err_msg,
            )
            session.add(record)

        session.commit()

    def sync_leformat_dataset_episode_subtask_range_annotation_embedding_task_baai(self) -> None:
        with self.db.with_session() as session:
            items = (
                session.query(LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationStatusDB)
                .filter(
                    LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationStatusDB.status
                    == TaskStatus.COMPLETED
                )
                .filter(
                    not_(
                        session.query(LeformatDatasetEpisodeSubtaskRangeAnnotationEmbeddingStatusDB)
                        .filter(
                            LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationStatusDB.dataset_uuid
                            == LeformatDatasetEpisodeSubtaskRangeAnnotationEmbeddingStatusDB.dataset_uuid
                        )
                        .exists()
                    )
                )
                .all()
            )

        for item in items:
            with self.db.with_session() as session:
                self._upsert_leformat_dataset_episode_subtask_range_annotation_embedding_status(
                    session,
                    dataset_uuid=item.dataset_uuid,
                    convert_path=item.convert_path,
                    status=TaskStatus.PENDING,
                )

        self.logger.info(
            f"sync {len(list(items))} leformat_dataset_episode_subtask_range_annotation_embedding_task_baai: {len(list(items))}"
        )

    def _gen_one_leformat_dataset_episode_optimized_subtask_range_annotation_embedding_task(
        self,
    ) -> str | None:
        with self.db.with_session() as session:
            item: LeformatDatasetEpisodeSubtaskRangeAnnotationEmbeddingStatusDB = (
                session.query(LeformatDatasetEpisodeSubtaskRangeAnnotationEmbeddingStatusDB)
                .filter(
                    LeformatDatasetEpisodeSubtaskRangeAnnotationEmbeddingStatusDB.status
                    == TaskStatus.PENDING
                )
                .first()
            )

            if item is None:
                return None

            self._upsert_leformat_dataset_episode_subtask_range_annotation_embedding_status(
                session,
                dataset_uuid=item.dataset_uuid,
                convert_path=item.convert_path,
                status=TaskStatus.PROCESSING,
            )
            return item.dataset_uuid

    def _embed_leformat_dataset_episode_optimized_subtask_range_annotation_baai(
        self, dataset_uuid: str
    ) -> None:
        with self.db.with_session() as session:
            range_items = list(
                session.query(LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationDB)
                .filter(
                    LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationDB.dataset_uuid
                    == dataset_uuid
                )
                .all()
            )
            if not range_items:
                self.logger.error(
                    f"No episode optimized subtask range annotation for {dataset_uuid}"
                )
                self._upsert_leformat_dataset_episode_subtask_range_annotation_embedding_status(
                    session,
                    dataset_uuid=dataset_uuid,
                    status=TaskStatus.FAILED,
                    err_msg="No episode optimzed subtask range annotation found for this dataset",
                )
                return

        # 获取 leformat_path
        leformat_path = Path(self._get_convert_path(dataset_uuid)).expanduser().absolute()
        if not leformat_path.exists():
            self.logger.error(f"{leformat_path} does not exist")
            self._upsert_leformat_dataset_episode_subtask_range_annotation_embedding_status(
                session,
                dataset_uuid=dataset_uuid,
                status=TaskStatus.FAILED,
                err_msg=f"{leformat_path} does not exist",
            )

        # 获取 subtasks.jsonl文件路径
        subtask_annotations_path = leformat_path / "annotations"
        subtask_annotations_path.mkdir(parents=True, exist_ok=True)
        jsonl_file_path = subtask_annotations_path / "subtasks.jsonl"

        optimized_subtask_annotations = list(set([item.annotation for item in range_items]))

        # dict{subtask_annotation : idx}
        optimized_subtask_annotations_dict = {
            item: idx for idx, item in enumerate(optimized_subtask_annotations)
        }
        optimized_subtask_annotations_dict["null"] = len(optimized_subtask_annotations_dict)

        jsonl_dicts: list[dict] = []
        for annotation, idx in optimized_subtask_annotations_dict.items():
            jsonl_dicts.append(
                {
                    "subtask_index": idx,
                    "subtask": annotation,
                }
            )
        with jsonl_file_path.open("w") as f:
            for item in jsonl_dicts:
                f.write(json.dumps(item) + "\n")

        self.logger.info(f"subtasks.jsonl written to {jsonl_file_path}")

        parquet_files_dir = leformat_path / "data"
        episodes_jsonl_file_path = leformat_path / "meta/episodes.jsonl"
        if not episodes_jsonl_file_path.exists():
            self.logger.error(f"{episodes_jsonl_file_path} does not exist")
            self._upsert_leformat_dataset_episode_subtask_range_annotation_embedding_status(
                session,
                dataset_uuid=dataset_uuid,
                status=TaskStatus.FAILED,
                err_msg=f"{episodes_jsonl_file_path} does not exist",
            )

        with episodes_jsonl_file_path.open("r") as f:
            episodes_jsonl = [json.loads(line) for line in f]

        episodes_frame_nums = [item["length"] for item in episodes_jsonl]
        parquet_files = list(parquet_files_dir.rglob("*.parquet"))

        for parquet_file_path in tqdm(parquet_files, desc="Embed subtask annotations", unit="file"):
            filename = parquet_file_path.name  # 获取文件名

            match = re.search(r"episode_(\d+)", filename)
            if match:
                ep_idx = int(match.group(1))
            else:
                self.logger.error(f"Cannot find episode index in {filename}")
                continue

            episode_subtask_annotations = [
                item for item in range_items if item.episode_idx == ep_idx
            ]

            if ep_idx >= len(episodes_jsonl):
                self.logger.error(f"Episode index {ep_idx} out of range")
                continue
            episode_frame_num = episodes_frame_nums[ep_idx]
            episode_st_anno_indices_list = [[] for _ in range(episode_frame_num)]

            for range_item in episode_subtask_annotations:
                annotation = range_item.annotation
                start_frame_idx = range_item.start_frame_idx
                end_frame_idx = range_item.end_frame_idx
                annotation_idx = optimized_subtask_annotations_dict[annotation]
                # 标注文件使用的是1-based index及左闭右闭，这里转换为0-based index及左闭右开
                for frame_idx in range(start_frame_idx - 1, end_frame_idx):
                    if frame_idx >= episode_frame_num:
                        self.logger.error(
                            f"Frame index {frame_idx} out of range for episode {ep_idx}"
                        )
                        continue

                    episode_st_anno_indices_list[frame_idx].append(annotation_idx)

            for frame_idx in range(episode_frame_num):
                if not episode_st_anno_indices_list[frame_idx]:
                    episode_st_anno_indices_list[frame_idx].append(
                        optimized_subtask_annotations_dict["null"]
                    )

            # 已经拿到了每个episode 的每个frame对应的subtask_annotation list，接下来需要写入到parquet文件中

            import pandas as pd

            df = pd.read_parquet(parquet_file_path)
            # 先确保列存在且为 object 类型
            df["subtask_indices"] = pd.Series(
                [None] * len(df), dtype="object"
            )  # 显式初始化为 object
            for i in range(len(episode_st_anno_indices_list)):
                df.at[i, "subtask_indices"] = episode_st_anno_indices_list[i]

            df.to_parquet(parquet_file_path)

        self._upsert_leformat_dataset_episode_subtask_range_annotation_embedding_status(
            session,
            dataset_uuid=dataset_uuid,
            status=TaskStatus.COMPLETED,
        )

    def embed_leformat_dataset_episode_optimized_subtask_range_annotation_baai(
        self,
    ) -> None:
        self.sync_leformat_dataset_episode_subtask_range_annotation_embedding_task_baai()
        with self.db.with_session() as session:
            task_num = (
                session.query(LeformatDatasetEpisodeSubtaskRangeAnnotationEmbeddingStatusDB)
                .filter(
                    LeformatDatasetEpisodeSubtaskRangeAnnotationEmbeddingStatusDB.status
                    == TaskStatus.PENDING
                )
                .count()
            )

        pbar = tqdm(
            total=task_num,
            desc="Embedding Episode Optimized Range Subtask Annotations for Datasets",
            unit="dataset",
        )

        try:
            processed_count = 0
            while True:
                dataset_uuid = self._gen_one_leformat_dataset_episode_optimized_subtask_range_annotation_embedding_task()
                if dataset_uuid is None:
                    break
                self._embed_leformat_dataset_episode_optimized_subtask_range_annotation_baai(
                    dataset_uuid
                )
                pbar.update(1)
                processed_count += 1

            pbar.close()

        except Exception as e:
            pbar.close()
            raise e
