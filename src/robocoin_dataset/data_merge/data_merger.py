import json
import logging
import uuid
from collections import defaultdict
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DatasetDB,
    TaskStatus,
)
from robocoin_dataset.utils.parquet_paths import (
    get_episode_stats_file_path,
    get_meta_info_file_path,
    get_parquet_paths,
)


def _get_uuid_list_from_string(uuids_str: str) -> list[str]:
    return [uuid_str.strip() for uuid_str in uuids_str.split(",") if uuid_str]


def _get_string_from_uuid_list(uuids: list[str]) -> str:
    return ",".join(uuids)


class DataMergeConfig:
    pre_stage_set: set[tuple[str, str, str]] = {
        (
            DatasetDB.video_embed_subtask_annotation_status,
            DatasetDB.video_embed_subtask_annotation_version,
            DatasetDB.data_merge_version_ps_sta,
        ),
        (
            DatasetDB.scene_annotation_status,
            DatasetDB.scene_annotation_version,
            DatasetDB.data_merge_version_ps_sa,
        ),
        (
            DatasetDB.motion_annotation_status,
            DatasetDB.motion_annotation_version,
            DatasetDB.data_merge_version_ps_ma,
        ),
    }
    patch_features = ["subtask_annotation", "scene_annotation", "motion_annotation", "state_action"]

    merge_feature = "merged"


def _merge_episode_parquet_files(
    ori_path: str | Path,
    patch_paths: list[str | Path],
    output_path: str | Path,
) -> None:
    # 1. 读取原始数据
    ori_df = pd.read_parquet(ori_path)

    # 2. 逐个应用 patch
    result_df = ori_df.copy()
    updated_columns = set()

    for i, p_path in enumerate(patch_paths, 1):
        p_path = Path(p_path)
        if not p_path.exists():
            continue

        patch_df = pd.read_parquet(p_path)
        if len(patch_df) != len(result_df):
            raise ValueError(
                f"文件行数不一致: {p_path.name} ({len(patch_df)} 行) vs 原始数据 ({len(result_df)} 行)"
            )

        # 找出 patch 中存在的数据列（排除主键类列，但这里我们只更新实际数据）
        for col in patch_df.columns:
            result_df[col] = patch_df[col].values  # 直接按位置赋值
            updated_columns.add(col)

    # 3. 保存结果
    result_df.to_parquet(output_path, index=False)


def _merge_parquet_files(
    ori_parquet_files: list[str | Path],
    patch_parquet_files: list[list[str | Path]],
    merged_parquet_files: list[str | Path],
) -> None:
    if len(ori_parquet_files) != len(merged_parquet_files):
        raise ValueError(
            f"The number of original parquet files ({len(ori_parquet_files)}) "
            f"does not match the number of merged parquet files ({len(merged_parquet_files)})."
        )
    for parquet_files in patch_parquet_files:
        if len(parquet_files) != len(merged_parquet_files):
            raise ValueError(
                f"parquet_files length {len(parquet_files)} != merge_parquet_files length {len(merged_parquet_files)}"
            )

    for ep_idx in range(len(merged_parquet_files)):
        feature_patch_parquet_files = [
            parquet_files[ep_idx] for parquet_files in patch_parquet_files
        ]
        _merge_episode_parquet_files(
            ori_parquet_files[ep_idx], feature_patch_parquet_files, merged_parquet_files[ep_idx]
        )


def merge_dataset_parquet_files(
    root_dir: str | Path, patch_features: list[str], merge_feature: str = "merged"
) -> None:
    features_parquet_files = []
    ori_parquet_files: list[Path] = []
    ori_parquet_files, merge_parquet_files = get_parquet_paths(root_dir, merge_feature)
    for feature in patch_features:
        _, feature_parquet_files = get_parquet_paths(root_dir, feature)
        if not feature_parquet_files[0].exists():
            raise ValueError(f"{features_parquet_files[0]} file not found")
        features_parquet_files.append(feature_parquet_files)

    _merge_parquet_files(ori_parquet_files, features_parquet_files, merge_parquet_files)


def _deep_merge_dict(ori: dict, patch: dict) -> dict:
    for key, value in patch.items():
        if key in ori:
            if isinstance(ori[key], dict) and isinstance(value, dict):
                # 递归合并字典
                _deep_merge_dict(ori[key], value)
            elif isinstance(ori[key], list) and isinstance(value, list):
                ori[key] = value
            else:
                # 基本类型或类型不同 → 直接替换
                ori[key] = value
        else:
            # 新增键
            ori[key] = value
    return ori


def _merge_info_files(
    ori_path: str | Path,
    patch_paths: list[str | Path],
) -> dict:
    with open(ori_path) as f:
        ori_info = json.load(f)
    for patch_path in patch_paths:
        with open(patch_path) as f:
            patch_info = json.load(f)
        ori_info = _deep_merge_dict(ori_info, patch_info)

    return ori_info


def _fill_dtype_and_shape(info: dict[str, dict], parquet_file_path: str | Path) -> dict:
    parquet_file_path = Path(parquet_file_path)
    df = pd.read_parquet(str(parquet_file_path))

    for feature_name in info["features"].keys():
        if feature_name in df.columns:
            first_value = df[feature_name].iloc[0]
            import numpy as np

            arr = np.array(first_value)
            if arr.shape == ():
                shape = [1]
            else:
                shape = list(arr.shape)

            info["features"][feature_name]["dtype"] = str(first_value.dtype)
            info["features"][feature_name]["shape"] = shape

    return info


def merge_dataset_info_files(
    root_dir: str | Path, patch_features: list[str], merged_feature: str = "merged"
) -> dict:
    root_dir = Path(root_dir).expanduser().absolute()
    ori_info_path, merged_info_path = get_meta_info_file_path(root_dir, merged_feature)
    _, merged_parquet_paths = get_parquet_paths(root_dir, merged_feature)
    patch_info_paths = []
    for feature in patch_features:
        _, path = get_meta_info_file_path(root_dir, feature)
        if not path.exists():
            raise FileNotFoundError(f"{path} not found")
        patch_info_paths.append(path)

    merged_info = _merge_info_files(ori_info_path, patch_info_paths)
    merged_info = _fill_dtype_and_shape(merged_info, merged_parquet_paths[0])

    with open(merged_info_path, "w") as f:
        json.dump(merged_info, f)
    return merged_info


def _merge_jsonl_files(
    ori_file: str | Path, patch_files: list[str, Path], output_file: str | Path
) -> None:
    with open(ori_file) as f:
        ori_jsonl = [json.loads(line) for line in f]

    patch_jsonls = []
    for patch_file in patch_files:
        with open(patch_file) as f:
            patch_jsonl = [json.loads(line) for line in f]
        patch_jsonls.append(patch_jsonl)

    for patch_jsonl in patch_jsonls:
        if len(ori_jsonl) != len(patch_jsonl):
            raise ValueError(f"patch_jsonl 长度不一致: {len(ori_jsonl)} != {len(patch_jsonl)}")

    new_jsonl = []
    for i in range(len(ori_jsonl)):
        ori_json = ori_jsonl[i]
        for patch_json in patch_jsonl:
            ori_json = _deep_merge_dict(ori_json, patch_json)
        new_jsonl.append(ori_json)

    with open(output_file, "w") as f:
        for json_obj in new_jsonl:
            json.dump(json_obj, f)
            f.write("\n")


def merge_dataset_stats_jsonl_files(
    root_dir: str | Path, patch_features: list[str], merge_feature: str = "merged"
) -> None:
    ori_stats_file, merged_stats_file = get_episode_stats_file_path(root_dir, merge_feature)
    patch_stats_files = []
    for patch_feature in patch_features:
        _, patch_stats_file = get_episode_stats_file_path(root_dir, patch_feature)
        if not patch_stats_file.exists():
            raise FileNotFoundError(f"{patch_stats_file} does not exist")
        patch_stats_files.append(patch_stats_file)

    _merge_jsonl_files(ori_stats_file, patch_stats_files, merged_stats_file)


def merge_dataset_data(
    root_dir: str | Path, ori_stats_file: str | Path, patch_features: list[str], merge_feature: str
) -> None:
    merge_dataset_parquet_files(root_dir, ori_stats_file, patch_features, merge_feature)
    merge_dataset_info_files(root_dir, ori_stats_file, patch_features, merge_feature)
    merge_dataset_stats_jsonl_files(root_dir, ori_stats_file, patch_features, merge_feature)


class DataMerger:
    def __init__(
        self,
        db_file_path: str | Path,
        logger: logging.Logger | None = None,
        data_merge_config: DataMergeConfig = DataMergeConfig(),
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)
        self.data_merge_config = data_merge_config

    def _merge_data(self, convert_path: str) -> None:
        merge_dataset_data(
            convert_path,
            self.data_merge_config.patch_features,
            self.data_merge_config.merge_feature,
        )

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
