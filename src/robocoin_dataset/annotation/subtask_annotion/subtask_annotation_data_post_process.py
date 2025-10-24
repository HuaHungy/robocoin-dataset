import logging
import uuid
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy.sql import not_

from robocoin_dataset.database.database import (
    DatasetDatabase,
)
from robocoin_dataset.database.models import (
    LeFormatConvertDB,
    LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationDB,
    LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationStatusDB,
    LeformatDatasetEpisodeSubtaskRangeAnnotationEmbeddingStatusDB,
    TaskStatus,
)


class SubtaskAnnotationDataPostProcess:
    def __init__(
        self,
        db_path: str | Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.logger = logger or logging.getLogger(__name__)
        self.db_path = Path(db_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_path)

    def _upsert_leformat_dataset_episode_subtask_range_annotation_embedding_status(
        self,
        session: Session,
        dataset_uuid: str,
        prestage_version_uuid: str,
        convert_path: str | None = None,
        status: TaskStatus | None = None,
        err_msg: str | None = None,
    ) -> None:
        version_uuid = str(uuid.uuid4())
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
            item.prestage_version_uuid = item.prestage_version_uuid
            item.version_uuid = version_uuid
        else:
            # 插入新记录
            record = LeformatDatasetEpisodeSubtaskRangeAnnotationEmbeddingStatusDB(
                dataset_uuid=dataset_uuid,
                convert_path=convert_path,
                status=status or TaskStatus.PENDING,
                err_msg=err_msg,
                prestage_version_uuid=prestage_version_uuid,
                version_uuid=version_uuid,
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
                        .filter(
                            LeformatDatasetEpisodeSubtaskRangeAnnotationEmbeddingStatusDB.prestage_version_uuid
                            == LeformatDatasetEpisodeOptimizedSubtaskRangeAnnotationStatusDB.version_uuid
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
                    prestage_version_uuid=item.version_uuid,
                )

        self.logger.info(
            f"sync {len(list(items))} leformat_dataset_episode_subtask_range_annotation_embedding_task_baai: {len(list(items))}"
        )

    def _gen_one_leformat_dataset_episode_optimized_subtask_range_annotation_embedding_task(
        self,
    ) -> tuple[str, str]:
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
                return None, None

            self._upsert_leformat_dataset_episode_subtask_range_annotation_embedding_status(
                session,
                dataset_uuid=item.dataset_uuid,
                convert_path=item.convert_path,
                status=TaskStatus.PROCESSING,
                prestage_version_uuid=item.prestage_version_uuid,
            )
            return item.dataset_uuid, item.prestage_version_uuid

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
                item = (
                    session.query(LeformatDatasetEpisodeSubtaskRangeAnnotationEmbeddingStatusDB)
                    .filter(
                        LeformatDatasetEpisodeSubtaskRangeAnnotationEmbeddingStatusDB.dataset_uuid
                        == dataset_uuid
                    )
                    .first()
                )
                if not item:
                    self.logger.error(
                        f"No episode optimized subtask range annotation for {dataset_uuid}"
                    )
                self._upsert_leformat_dataset_episode_subtask_range_annotation_embedding_status(
                    session,
                    dataset_uuid=dataset_uuid,
                    status=TaskStatus.FAILED,
                    err_msg="No episode optimzed subtask range annotation found for this dataset",
                    prestage_version_uuid=item.prestage_version_uuid,
                )
                return

        # 获取 leformat_path
        with self.db.with_session() as session:
            item = (
                session.query(LeFormatConvertDB)
                .filter(LeFormatConvertDB.dataset_uuid == dataset_uuid)
                .first()
            )
            if not item:
                self.logger.error(f"No convert path for {dataset_uuid}")
                return
            leformat_path = Path(item.convert_path).expanduser().absolute()
            item = (
                session.query(LeformatDatasetEpisodeSubtaskRangeAnnotationEmbeddingStatusDB)
                .filter(
                    LeformatDatasetEpisodeSubtaskRangeAnnotationEmbeddingStatusDB.dataset_uuid
                    == dataset_uuid
                )
                .first()
            )
            if not item:
                self.logger.error(
                    f"No episode optimized subtask range annotation for {dataset_uuid}"
                )
                return
            if not leformat_path.exists():
                self.logger.error(f"{leformat_path} does not exist")
                self._upsert_leformat_dataset_episode_subtask_range_annotation_embedding_status(
                    session,
                    dataset_uuid=dataset_uuid,
                    status=TaskStatus.FAILED,
                    err_msg=f"{leformat_path} does not exist",
                    prestage_version_uuid=item.prestage_version_uuid,
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
                frame_anno_indices = episode_st_anno_indices_list[i]
                if len(frame_anno_indices) > MAX_SUBTASK_NUM:
                    frame_anno_indices = frame_anno_indices[:MAX_SUBTASK_NUM]
                elif len(frame_anno_indices) < MAX_SUBTASK_NUM:
                    frame_anno_indices.extend(
                        [optimized_subtask_annotations_dict["null"]]
                        * (MAX_SUBTASK_NUM - len(frame_anno_indices))
                    )
                df.at[i, "subtask_indices"] = frame_anno_indices

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
