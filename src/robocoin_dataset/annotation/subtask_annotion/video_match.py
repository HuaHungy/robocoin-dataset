import base64
import logging
import pickle
import traceback
from collections import defaultdict
from pathlib import Path

import imagehash
import tqdm
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from robocoin_dataset.annotation.subtask_annotion.utils import (
    match_video_file_hash,
    match_video_image_hash,
)
from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DatasetDB,
    StAnnotationVideoDB,
    TaskStatus,
    VideoHashDB,
    VideoMatchDB,
)


def prepare_video_filehash_lib(session: Session) -> dict[str, str]:
    hash_items = (
        session.query(
            StAnnotationVideoDB,
        )
        .filter(StAnnotationVideoDB.video_hash_status == TaskStatus.COMPLETED)
        .all()
    )
    sha256_list = [item.file_hash for item in hash_items]
    video_id_list = [item.id for item in hash_items]

    return {sha256_list[i]: video_id_list[i] for i in range(len(video_id_list))}


def prepare_video_imagehashes_lib(session: Session) -> dict[str, dict[int, imagehash.ImageHash]]:
    items = (
        session.query(StAnnotationVideoDB)
        .filter(
            StAnnotationVideoDB.video_hash_status == TaskStatus.COMPLETED
        )  # 可选：确保 sha256 存在
        .all()
    )

    image_hashes_list = [pickle.loads(base64.b64decode(item.video_hash)) for item in items]
    id_list = [row.id for row in items]

    video_imagehashes = {id_list[i]: image_hashes_list[i] for i in range(len(id_list))}
    frame_num_list = [row.frame_num for row in items]

    frame_num_dict = {id_list[i]: frame_num_list[i] for i in range(len(id_list))}
    result = defaultdict(dict)

    for id_, image_hash in video_imagehashes.items():
        frame_num = frame_num_dict[id_]
        result[frame_num][id_] = image_hash

    return result


def match_episode_with_url_video(
    ep_videos_file_hashes: list[str],
    ep_video_image_hashes: list[imagehash.ImageHash],
    frame_num: int,
    file_hash_lib: dict[str, int],
    image_hashes_lib: dict[int, dict[int, imagehash.ImageHash]],
) -> int | None:
    for file_hash in ep_videos_file_hashes:
        matched_video_id = match_video_file_hash(file_hash, file_hash_lib)
        if matched_video_id:
            return matched_video_id
    for video_image_hash in ep_video_image_hashes:
        matched_video_id = match_video_image_hash(
            frame_num=frame_num,
            image_phash=video_image_hash,
            video_image_phashes_lib=image_hashes_lib,
        )
        if matched_video_id:
            return matched_video_id
    return None


def match_dataset_with_url_video(
    dataset_file_hashes: dict[int, list[str]],
    dataset_image_hashes: dict[int, list[imagehash.ImageHash]],
    dataset_frame_nums: dict[int, int],
    file_hash_lib: dict[str, int],
    image_hashes_lib: dict[int, dict[int, imagehash.ImageHash]],
) -> dict[int, int | None]:
    results = {}
    for ep_idx in tqdm.tqdm(dataset_file_hashes.keys(), desc="match episodes", unit="episode"):
        ep_video_file_hashes = dataset_file_hashes[ep_idx]
        ep_video_image_hashes = dataset_image_hashes[ep_idx]
        frame_num = dataset_frame_nums[ep_idx]
        matched_video_id = match_episode_with_url_video(
            ep_video_file_hashes,
            ep_video_image_hashes,
            frame_num,
            file_hash_lib,
            image_hashes_lib,
        )
        results[ep_idx] = matched_video_id

    return results


def _list_to_range_string(nums: list[int]) -> str:
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


class VideoMatch:
    def __init__(
        self,
        db_file_path: str | Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)
        with self.db.with_session() as session:
            self.file_hash_lib = prepare_video_filehash_lib(session)
            self.image_hash_lib = prepare_video_imagehashes_lib(session)

    def sync_video_match_status(self, match_failed_videos: bool = False) -> None:
        with self.db.with_session() as session:
            if match_failed_videos:
                status_list = [
                    TaskStatus.FAILED,
                    TaskStatus.PENDING,
                ]
            else:
                status_list = [TaskStatus.PENDING]
            query = session.query(DatasetDB).filter(
                and_(
                    # 必要前提：convert必须成功
                    DatasetDB.video_hash_status == TaskStatus.COMPLETED,
                    # 两个触发分支
                    or_(
                        # 分支1: 正在排队
                        DatasetDB.video_match_status.in_(status_list),
                        # 分支2: 已完成但版本过期
                        and_(
                            DatasetDB.video_match_status == TaskStatus.COMPLETED,
                            DatasetDB.video_match_version_ps < DatasetDB.video_hash_version,
                        ),
                    ),
                )
            )

            for item in query.all():
                item.video_match_status = TaskStatus.PENDING
                item.video_match_version_ps = item.video_hash_version
            session.commit()

    def gen_one_dataset_video_match_task(self) -> str:
        with self.db.with_session() as session:
            query = session.query(DatasetDB).filter(
                and_(
                    DatasetDB.video_hash_status == TaskStatus.COMPLETED,
                    DatasetDB.video_match_status == TaskStatus.PENDING,
                )
            )
            item = query.first()
            if not item:
                return None

            item.video_match_status = TaskStatus.PROCESSING
            item.video_match_version = item.video_match_version + 1
            session.commit()
            return item.dataset_uuid

    def get_ep_video_hashes(
        self, dataset_uuid: str
    ) -> tuple[dict[int, list[str]], dict[int, int], dict[int, list[list[imagehash.ImageHash]]]]:
        with self.db.with_session() as session:
            query = session.query(VideoHashDB).filter(
                VideoHashDB.dataset_uuid == dataset_uuid,
            )
            items = query.all()
            ep_video_file_hashes = defaultdict(list)
            ep_video_image_hashes = defaultdict(list)
            dataset_frame_nums = {}

            for item in items:
                ep_idx = item.ep_idx
                frame_num = item.frame_num
                file_hash = item.file_hash
                image_hashes = pickle.loads(base64.b64decode(item.image_hashes))

                ep_video_file_hashes[ep_idx].append(file_hash)
                ep_video_image_hashes[ep_idx].append(image_hashes)
                dataset_frame_nums[ep_idx] = frame_num

        return ep_video_file_hashes, dataset_frame_nums, ep_video_image_hashes

    def _match_videos_one_dataset(self, dataset_uuid: str) -> None:
        if not dataset_uuid:
            return

        ep_video_file_hashes, dataset_frame_nums, ep_video_image_hashes = self.get_ep_video_hashes(
            dataset_uuid
        )

        try:
            match_results = match_dataset_with_url_video(
                ep_video_file_hashes,
                ep_video_image_hashes,
                dataset_frame_nums,
                self.file_hash_lib,
                self.image_hash_lib,
            )

            unmatched_ep_idxs = [k for k, v in match_results.items() if v is None]
            if unmatched_ep_idxs:
                unmactched_ep_idxs_str = _list_to_range_string(unmatched_ep_idxs)
                self.logger.warning(
                    f"Dataset {dataset_uuid} has {len(unmatched_ep_idxs)} unmatched episodes: {unmactched_ep_idxs_str}"
                )
                with self.db.with_session() as session:
                    item = (
                        session.query(DatasetDB)
                        .filter(
                            DatasetDB.dataset_uuid == dataset_uuid,
                        )
                        .first()
                    )
                    if not item:
                        raise ValueError(f"Dataset {dataset_uuid} not found")
                    item.video_match_status = TaskStatus.FAILED
                    item.video_match_err_msg = unmactched_ep_idxs_str
                    session.query(VideoMatchDB).filter(
                        VideoMatchDB.dataset_uuid == dataset_uuid,
                    ).delete()

                    for ep_idx, url_video_id in match_results.items():
                        if url_video_id is None:
                            continue
                        session.add(
                            VideoMatchDB(
                                dataset_uuid=dataset_uuid,
                                episode_idx=ep_idx,
                                url_video_id=url_video_id,
                            )
                        )

                    session.commit()
            else:
                with self.db.with_session() as session:
                    session.query(DatasetDB).filter(
                        DatasetDB.dataset_uuid == dataset_uuid,
                    ).update(
                        {
                            DatasetDB.video_match_status: TaskStatus.COMPLETED,
                        }
                    )

                    session.query(VideoMatchDB).filter(
                        VideoMatchDB.dataset_uuid == dataset_uuid,
                    ).delete()

                    for ep_idx, url_video_id in match_results.items():
                        if url_video_id is None:
                            continue
                        session.add(
                            VideoMatchDB(
                                dataset_uuid=dataset_uuid,
                                episode_idx=ep_idx,
                                url_video_id=url_video_id,
                            )
                        )

                    session.commit()

        except Exception:
            with self.db.with_session() as session:
                query = session.query(DatasetDB).filter(
                    DatasetDB.dataset_uuid == dataset_uuid,
                )
                item = query.first()
                if not item:
                    raise ValueError(f"Dataset {dataset_uuid} not found")

                item.video_match_status = TaskStatus.FAILED
                item.video_match_err_msg = traceback.format_exc()
                self.logger.error(
                    f"Dataset {dataset_uuid} video match failed: {traceback.format_exc()}"
                )
                session.commit()

    def match_videos(self, match_failed_videos: bool = True) -> None:
        self.sync_video_match_status(match_failed_videos=match_failed_videos)
        with self.db.with_session() as session:
            task_num = (
                session.query(DatasetDB)
                .filter(
                    and_(
                        DatasetDB.video_hash_status == TaskStatus.COMPLETED,
                        DatasetDB.video_match_status == TaskStatus.PENDING,
                    )
                )
                .count()
            )
            if task_num == 0:
                self.logger.info("No video match task")
                return
        pbar = tqdm.tqdm(total=task_num, desc="Match Videos with URL Videos", unit="dataset")
        while True:
            dataset_uuid = self.gen_one_dataset_video_match_task()
            if dataset_uuid is None:
                break

            self._match_videos_one_dataset(dataset_uuid=dataset_uuid)
            pbar.update(1)

        pbar.close()
