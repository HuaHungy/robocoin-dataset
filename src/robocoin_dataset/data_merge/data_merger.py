import json
import logging
import uuid
from collections import defaultdict
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DmvAnnotationDB,
    LeFormatConvertDB,
    LeformatDatasetDataMergeStatusDB,
    LeformatDatasetEpisodeSubtaskRangeAnnotationEmbeddingStatusDB,
    LeformatDatasetMotionAnnotationStatusDB,
    LeformatDateasetStateActionPostProcessingStatusDB,
    TaskStatus,
)
from robocoin_dataset.utils.parquet_paths import get_meta_info_file_path, get_parquet_paths


def _get_uuid_list_from_string(uuids_str: str) -> list[str]:
    return [uuid_str.strip() for uuid_str in uuids_str.split(",") if uuid_str]


def _get_string_from_uuid_list(uuids: list[str]) -> str:
    return ",".join(uuids)


class DataMerger:
    def __init__(
        self,
        db_file_path: str | Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)

        self.pre_stage_classes: list = [
            LeformatDateasetStateActionPostProcessingStatusDB,
            LeformatDatasetEpisodeSubtaskRangeAnnotationEmbeddingStatusDB,
            LeformatDatasetMotionAnnotationStatusDB,
        ]
        self.pre_stage_feature_names: list = [
            "state_action",
            "subtask_indices",
            "motion_annotations",
        ]
        if len(self.pre_stage_classes) != len(self.pre_stage_feature_names):
            raise ValueError("pre_stage_classes and pre_stage_feature_names must have same length.")

    def _merge_data(self, convert_path: str) -> None:
        convert_path = Path(convert_path).expanduser().absolute()
        ori_parquet_files, merged_parquet_files = get_parquet_paths(convert_path, "merged")
        merged_meta_info_file_path = get_meta_info_file_path(convert_path, "merged")
        ori_meta_file_path = convert_path / "meta/info.json"
        with open(ori_meta_file_path) as f:
            ori_meta_info: dict = json.load(f)
            merged_meta_info = ori_meta_info

        feature_parquet_files = {}
        feature_meta_info_files = {}
        for feature in self.pre_stage_feature_names:
            _, parquet_files = get_parquet_paths(convert_path, feature)
            meta_info_file = get_meta_info_file_path(convert_path, feature)

            if len(feature_parquet_files) != len(ori_parquet_files):
                raise ValueError(
                    f"{feature} parquet files number is not equal to original parquet files number"
                )
            feature_parquet_files[feature] = parquet_files
            feature_meta_info_files[feature] = meta_info_file

        for i, ori_parquet_file in enumerate(ori_parquet_files):
            if not ori_parquet_file.exists():
                raise FileNotFoundError(f"{ori_parquet_file} does not exist")
            merged_parquet_file = merged_parquet_files[i]
            merged_df = pd.read_parquet(ori_parquet_file)
            for feature in self.pre_stage_feature_names:
                feature_parquet_file = feature_parquet_files[feature][i]
                if not feature_parquet_file.exists():
                    raise FileNotFoundError(f"{feature_parquet_file} does not exist")

                feature_df = pd.read_parquet(feature_parquet_file)
                merged_df[feature] = feature_df[feature]

            merged_parquet_file.parent.mkdir(exist_ok=True, parents=True)
            merged_df.to_parquet(merged_parquet_file)

        merged_parquet_file = merged_parquet_files[0]
        merged_df = pd.read_parquet(merged_parquet_file)
        for column in merged_df.columns:
            dtype = merged_df[column].dtype
            shape = merged_df[column].shape[1]

    def _get_convert_path(self, dataset_uuid: str) -> str | None:
        with self.db.with_session() as session:
            item = (
                session.query(LeFormatConvertDB)
                .filter(LeFormatConvertDB.dataset_uuid == dataset_uuid)
                .first()
            )
            if item:
                return item.convert_path
            return None

    def _get_device_model_and_version(self, dataset_uuid: str) -> tuple[str, str]:
        with self.db.with_session() as session:
            item = (
                session.query(DmvAnnotationDB)
                .filter(DmvAnnotationDB.dataset_uuid == dataset_uuid)
                .first()
            )
            if item is None:
                return None, None
            return item.device_model, item.device_model_version

    def _upsert_leformat_dataset_data_merge_status(
        self,
        session: Session,
        dataset_uuid: str,
        convert_path: str,
        status: TaskStatus,
        prestage_version_uuids: list[str],
        device_model: str,
        device_model_version: str,
        err_msg: str = "",
    ) -> None:
        item = (
            session.query(LeformatDatasetDataMergeStatusDB)
            .filter(LeformatDatasetDataMergeStatusDB.dataset_uuid == dataset_uuid)
            .first()
        )
        prestage_version_uuids = _get_string_from_uuid_list(prestage_version_uuids)
        version_uuid = str(uuid.uuid4())
        if item:
            item.convert_path = convert_path
            item.status = status
            item.prestage_version_uuids = prestage_version_uuids
            item.device_model = device_model
            item.device_model_version = device_model_version
            item.version_uuid = version_uuid
            item.err_msg = err_msg
        else:
            item = LeformatDatasetDataMergeStatusDB(
                dataset_uuid=dataset_uuid,
                convert_path=convert_path,
                status=status,
                prestage_version_uuids=prestage_version_uuids,
                device_model=device_model,
                device_model_version=device_model_version,
                version_uuid=version_uuid,
                err_msg=err_msg,
            )
            session.add(item)
        session.commit()

    def _sync_data_merge_tasks(
        self, device_model: str | None = None, device_model_version: str | None = None
    ) -> None:
        with self.db.with_session() as session:
            dirty_items = {}
            completed_items = {
                item.dataset_uuid: item.prestage_version_uuids
                for item in session.query(LeformatDatasetDataMergeStatusDB)
                .filter(LeformatDatasetDataMergeStatusDB.status == TaskStatus.COMPLETED)
                .all()
            }
            for dataset_uuid, prestage_version_uuids in completed_items:
                prestage_version_uuid_list = []
                prestage_version_uuids = _get_uuid_list_from_string(prestage_version_uuids)
                success = False
                for i, prestage_version_uuid in enumerate(prestage_version_uuids):
                    cls = self.pre_stage_classes[i]
                    item = session.query(cls).filter(cls.dataset_uuid == dataset_uuid).first()
                    if item is None:
                        success = False
                        break
                    version_uuid = item.version_uuid
                    if version_uuid != prestage_version_uuid:
                        success = True
                    prestage_version_uuid_list.append(version_uuid)
                if success:
                    dirty_items[dataset_uuid] = prestage_version_uuid_list

            unexist_items = defaultdict(list)
            for cls in self.pre_stage_classes:
                items = (
                    session.query(cls)
                    .filter(
                        cls.dataset_uuid
                        != LeformatDatasetDataMergeStatusDB.dataset_uuid.filter(
                            cls.status == TaskStatus.COMPLETED
                        )
                    )
                    .all()
                )
                for item in items:
                    unexist_items[item.dataset_uuid].append(item.version_uuid)

            unexist_items = {
                k: v for k, v in unexist_items.items() if len(v) == len(self.pre_stage_classes)
            }

            sync_items = dirty_items | unexist_items

        for dataset_uuid, prestage_version_uuid_list in sync_items.items():
            convert_path = self._get_convert_path(dataset_uuid)
            device_model, device_model_version = self._get_device_model_and_version(dataset_uuid)
            prestage_version_uuids = _get_string_from_uuid_list(prestage_version_uuid_list)
            with self.db.with_session() as session:
                self._upsert_leformat_dataset_data_merge_status(
                    session=session,
                    dataset_uuid=dataset_uuid,
                    convert_path=convert_path,
                    prestage_version_uuid=prestage_version_uuids,
                    device_model=device_model,
                    device_model_version=device_model_version,
                    status=TaskStatus.PENDING,
                )

    def _gen_one_data_merge_task(
        self, device_model: str | None = None, device_model_version: str | None = None
    ) -> tuple[str, str, str, str]:
        with self.db.with_session() as session:
            query = session.query(LeformatDatasetDataMergeStatusDB).filter(
                LeformatDatasetDataMergeStatusDB.status == TaskStatus.PENDING,
            )
            if device_model:
                query = query.filter(LeformatDatasetDataMergeStatusDB.device_model == device_model)
                if device_model_version:
                    query = query.filter(
                        LeformatDatasetDataMergeStatusDB.device_model_version
                        == device_model_version
                    )
            item = query.first()
            if not item:
                return None, None, None, None
            item.status = TaskStatus.PROCESSING
            return (
                item.dataset_uuid,
                item.prestage_version_uuids,
                item.device_model,
                item.device_model_version,
            )

    def merge_data(
        self, device_model: str | None = None, device_model_version: str | None = None
    ) -> None:
        self._sync_data_merge_tasks(device_model, device_model_version=device_model_version)
        dataset_uuid, prestage_version_uuid, device_model, device_model_version = (
            self._gen_one_data_merge_task(
                device_model=device_model, device_model_version=device_model_version
            )
        )

        if dataset_uuid is None:
            return
        convert_path = self._get_convert_path(dataset_uuid)
        try:
            self._sim_replay_dataset(dataset_uuid)
            with self.db.with_session() as session:
                self._upsert_leformat_dataset_simulation_replay_status(
                    session=session,
                    dataset_uuid=dataset_uuid,
                    convert_path=convert_path,
                    prestage_version_uuid=prestage_version_uuid,
                    device_model=device_model,
                    device_model_version=device_model_version,
                    status=TaskStatus.COMPLETED,
                )

        except Exception as e:
            print(e)
            with self.db.with_session() as session:
                self._upsert_leformat_dataset_simulation_replay_status(
                    session=session,
                    dataset_uuid=dataset_uuid,
                    convert_path=convert_path,
                    status=TaskStatus.FAILED,
                    prestage_version_uuid=prestage_version_uuid,
                    device_model=device_model,
                    device_model_version=device_model_version,
                    err_msg=str(e),
                )
