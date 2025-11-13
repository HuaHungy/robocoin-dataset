import logging
import shutil
import threading
from pathlib import Path

import requests
import tqdm
from sqlalchemy import and_
from sqlalchemy.orm import Session

from robocoin_dataset.annotation.subtask_annotion.utils import (
    compute_video_hash,
    get_frame_num,
)
from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    StAnnotationVideoDB,
    TaskStatus,
)
from robocoin_dataset.distribution_computation.constant import (
    TASK_RESULT_CONTENT,
)
from robocoin_dataset.distribution_computation.task_client import TaskClient
from robocoin_dataset.distribution_computation.task_server import TaskServer

VIDEO_HASHES_RESULT = "video_hashes_result"
VIDEO_PATHS = "video_paths"


def _gen_video_hash_tasks(session: Session, num: int = 100) -> dict[int, str]:
    if num < 1 or num > 10000:
        raise ValueError("num must be between 1 and 10000")
    query = (
        session.query(StAnnotationVideoDB)
        .filter(
            StAnnotationVideoDB.video_hash_status == TaskStatus.PENDING,
            StAnnotationVideoDB.download_status == TaskStatus.COMPLETED,
        )
        .order_by(StAnnotationVideoDB.id)
    ).limit(num)
    results = {}
    items = query.all()
    for item in items:
        if Path(item.local_video_path).exists():
            results[item.id] = item.local_video_path
            item.video_hash_status = TaskStatus.PROCESSING
        else:
            item.video_hash_status = TaskStatus.FAILED
    session.commit()
    return results


def _compute_url_video_hashes(
    video_paths: dict[int, str],
) -> dict[int, tuple[str, int, str]]:
    """
    计算视频的 hash
    """
    hashes = {}
    for video_id, video_path in tqdm.tqdm(
        video_paths.items(), desc="Compute Url Video Hashes", unit="video"
    ):
        file_hash, frame_num, serialized_phashes = compute_video_hash(video_path)
        hashes[video_id] = (file_hash, frame_num, serialized_phashes)
    return hashes


def _upsert_url_videos_hashes(
    session: Session,
    hashes: dict[int, tuple[str, int, str]],
) -> None:
    query = session.query(StAnnotationVideoDB).filter(
        StAnnotationVideoDB.id.in_(list(hashes.keys()))
    )
    items = query.all()
    for item in items:
        video_id = item.id
        file_hash, frame_num, serialized_phashes = hashes[video_id]
        item.frame_num = frame_num
        item.file_hash = file_hash
        item.video_hash = serialized_phashes
        item.video_hash_status = TaskStatus.COMPLETED

    session.commit()


class UrlVideoDownload:
    def __init__(
        self,
        db_file_path: str | Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)

    def _download_or_copy_video(self, url: str, file_path: Path) -> bool:
        file_path = Path(file_path).expanduser().absolute()
        try:
            tmp_file_path = file_path.parent / f"{file_path.name}.tmp"
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            with open(tmp_file_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:  # 过滤掉保持连接的空 chunk
                        file.write(chunk)
                shutil.move(tmp_file_path, file_path)
                return True

        except Exception as dowload_error:
            if tmp_file_path.exists():
                shutil.rmtree(tmp_file_path)
            try:
                local_path = Path(url).expanduser().absolute()
                shutil.copyfile(local_path, file_path)
                return True
            except Exception as move_error:
                self.logger.error(f"复制文件: {url}, 错误: {move_error}")
            self.logger.error(f"下载失败: {url}, 错误: {dowload_error}")
            return False

    def download_videos_multi_threads(self, num_workers: int = 8) -> None:
        """
        启动多个工作线程，并发下载所有待处理任务
        """

        with self.db.with_session() as session:
            undownloaded_videos_num = (
                session.query(StAnnotationVideoDB)
                .filter(StAnnotationVideoDB.download_status == TaskStatus.PENDING)
                .count()
            )

        if undownloaded_videos_num <= 0:
            self.logger.info("没有待处理的任务")
            return
        self.logger.info(f"🚀 启动 {num_workers} 个下载线程，下载{undownloaded_videos_num}个视频")

        pbar = tqdm.tqdm(
            total=undownloaded_videos_num, desc="📥 下载进度", unit="file", dynamic_ncols=True
        )

        pbar_lock = threading.Lock()

        def _worker_download(worker_id: int) -> None:
            while True:
                with self.db.with_session() as session:
                    item = (
                        session.query(StAnnotationVideoDB)
                        .filter(StAnnotationVideoDB.download_status == TaskStatus.PENDING)
                        .first()
                    )
                    if not item:
                        break
                    item.download_status = TaskStatus.PROCESSING
                    video_url = item.video_url
                    download_path = item.local_video_path
                    video_id = item.id
                    session.commit()

                # 获取任务
                success = self._download_or_copy_video(video_url, download_path)
                if success:
                    try:
                        frame_num = get_frame_num(download_path)
                        with self.db.with_session() as session:
                            item = (
                                session.query(StAnnotationVideoDB)
                                .filter(StAnnotationVideoDB.id == video_id)
                                .first()
                            )
                            if item:
                                item.frame_num = frame_num
                                item.download_status = TaskStatus.COMPLETED
                                session.commit()
                    except Exception:
                        with self.db.with_session() as session:
                            item = (
                                session.query(StAnnotationVideoDB)
                                .filter(StAnnotationVideoDB.id == video_id)
                                .first()
                            )
                            if item:
                                item.download_status = TaskStatus.FAILED
                                session.commit()
                        success = False
                        self.logger.info(f"video decoding failed: {download_path}")
                else:
                    with self.db.with_session() as session:
                        item = (
                            session.query(StAnnotationVideoDB)
                            .filter(StAnnotationVideoDB.id == video_id)
                            .first()
                        )
                        if item:
                            item.download_status = TaskStatus.FAILED
                        session.commit()
                    success = False

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


class UrlVideoHash:
    def __init__(
        self,
        db_file_path: str | Path,
        batch_size: int = 100,
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.batch_size: int = batch_size
        self.logger = logger or logging.getLogger(__name__)

    def compute_url_video_hashes(self) -> None:
        with self.db.with_session() as session:
            task_num = (
                session.query(StAnnotationVideoDB)
                .filter(
                    and_(
                        StAnnotationVideoDB.video_hash_status == TaskStatus.PENDING,
                        StAnnotationVideoDB.download_status == TaskStatus.COMPLETED,
                    )
                )
                .count()
            )
        if not task_num:
            return

        batch_num = (task_num + self.batch_size - 1) // self.batch_size
        for _ in tqdm.tqdm(range(batch_num), desc="Generate Url Video Hashes", unit="batch"):
            with self.db.with_session() as session:
                video_paths: dict[int, str] = _gen_video_hash_tasks(
                    session=session, num=self.batch_size
                )
            if not video_paths:
                break
            batch_videos_hashes = _compute_url_video_hashes(video_paths)

            with self.db.with_session() as session:
                _upsert_url_videos_hashes(session, batch_videos_hashes)


class UrlVideoHashServer(TaskServer):
    def __init__(
        self,
        db_file_path: str | Path,
        batch_size: int = 100,
        host: str = "0.0.0.0",
        port: int = 8769,
        heartbeat_interval: float = 30.0,  # 服务端每30秒发一次 ping
        timeout: float = 15.0,  # 等待 pong 超过15秒则断开
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(
            logger=logger,
            host=host,
            port=port,
            heartbeat_interval=heartbeat_interval,
            timeout=timeout,
        )
        db_file_path = Path(db_file_path).expanduser().absolute()

        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.batch_size = batch_size
        self.logger = logger or logging.getLogger(__name__)
        self.logger.info("Video Hash Server started, ")

    def get_task_category(self) -> str:
        return "url_video_hash"

    def generate_task_content(self) -> dict | None:
        with self.db.with_session() as session:
            items = (
                session.query(StAnnotationVideoDB)
                .filter(
                    and_(
                        StAnnotationVideoDB.download_status == TaskStatus.COMPLETED,
                        StAnnotationVideoDB.video_hash_status == TaskStatus.PENDING,
                    )
                )
                .limit(self.batch_size)
            ).all()

            video_paths = {item.id: item.local_video_path for item in items}

            if not video_paths:
                return None

            for item in items:
                item.video_hash_status = TaskStatus.PROCESSING

            session.commit()
            return {
                VIDEO_PATHS: video_paths,
            }

    def handle_task_result(self, task_content: dict, task_result_content: dict) -> None:
        video_hash_results: dict = task_result_content.get(TASK_RESULT_CONTENT).get(
            VIDEO_HASHES_RESULT
        )
        video_hash_results = {int(k): v for k, v in video_hash_results.items()}
        with self.db.with_session() as session:
            _upsert_url_videos_hashes(session, video_hash_results)


class UrlVideoHashClient(TaskClient):
    def __init__(
        self,
        server_uri: str = "ws://localhost:8769",
        heartbeat_interval: float = 10.0,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(
            server_uri=server_uri,
            heartbeat_interval=heartbeat_interval,
            logger=logger,
        )

    def get_task_category(self) -> str:
        return "url_video_hash"

    def generate_task_request_desc(self) -> dict:
        """客户端可自定义任务请求参数"""
        return {}

    def _sync_process_task(self, task_content: dict) -> dict:
        try:
            video_paths = task_content.get(VIDEO_PATHS)
            video_hashes = _compute_url_video_hashes(video_paths)
            return {VIDEO_HASHES_RESULT: video_hashes}
        except Exception as e:
            raise RuntimeError("url video hash failed") from e
