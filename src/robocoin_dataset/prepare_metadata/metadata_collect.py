"""
本脚本整合网页静态资源与 Hub README 生成所需的元数据收集逻辑。

所有外部调用统一通过 ``create_unified_metadata``，该函数会：
1. 读取 SQLite 数据库，解析 DatasetDB 记录（场景、物体、末端执行器等结构化信息）
2. 读取原始 YAML（dataset_info.yml）补充 YAML 原生字段
3. 扫描 hardlink 数据集目录下的 meta/ 与 annotations/ 内容，构建统计信息、任务描述等
4. 自动生成目录结构、文件大小、帧数范围等派生字段

最终返回 ``UnifiedMetadata``，供网页（YAML）和 README 模板复用，确保两端信息完全一致。
"""

import logging
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB, DatasetHardLinkDB, ObjectDB
from robocoin_dataset.prepare_metadata.metadata_collect_utils import (
    build_action_space_from_features,
    build_cameras_from_features,
    build_observation_space_from_features,
    calculate_dataset_size,
    collect_from_yaml,
    collect_meta_info,
    collect_subtask_annotations,
    format_file_size,
    generate_folder_structure,
    generate_size_label,
    match_device_name_from_folder,
)
from robocoin_dataset.prepare_metadata.unified_metadata_def import UnifiedMetadata

LOGGER = logging.getLogger(__name__)


def get_default_gated_access_config() -> dict[str, Any]:
    """
    获取默认的数据集访问控制配置。

    这个函数封装了所有数据集的标准访问控制配置，用于生成 HuggingFace Hub 的 README 头部。
    统一管理所有数据集的访问控制规则，便于后续修改和维护。

    Returns:
        dict[str, Any]: 包含以下字段的字典：
            - extra_gated_prompt (str): 用户访问数据集时显示的提示信息
            - extra_gated_fields (dict): 用户需要填写的表单字段配置
    """
    def _escape_yaml_string(value: str) -> str:
        """对字符串进行YAML完全安全的转义处理"""
        if isinstance(value, str):
            # 对于YAML单引号字符串，我们需要转义单引号为双单引号
            # 同时确保内容中没有可能破坏YAML结构的字符
            return value.replace("'", "''").replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
        return value

    return {
        "extra_gated_prompt": _escape_yaml_string(
            "By accessing this dataset, you agree to cite the associated paper in your research/publications—see the \"Citation\" section for details. "
            "You agree to not use the dataset to conduct experiments that cause harm to human subjects."
        ),
        "extra_gated_fields": {
            "Company/Organization": {
                "type": _escape_yaml_string("text"),
                "description": _escape_yaml_string(
                    'e.g., "ETH Zurich", "Boston Dynamics", "Independent Researcher"'
                ),
            },
            "Country": {
                "type": _escape_yaml_string("country"),
                "description": _escape_yaml_string('e.g., "Germany", "China", "United States"'),
            }
        },
    }


def create_unified_metadata(
    hardlink_path: str | Path,
    db_file_path: str | Path,
    dataset_uuid: str | None = None,
) -> UnifiedMetadata:
    """
    构建单个数据集的统一元数据，确保 README 与网页静态资源使用同一份内容。
    """
    dataset_path = Path(hardlink_path).expanduser().absolute()
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset path does not exist: {dataset_path}")

    db_path = Path(db_file_path).expanduser().absolute()
    if not db_path.exists():
        raise FileNotFoundError(f"Database file does not exist: {db_path}")

    db_payload = _load_dataset_payload(
        db_path=db_path,
        dataset_path=dataset_path,
        dataset_uuid=dataset_uuid,
    )
    yaml_payload = _load_yaml_payload(db_payload)

    meta_info, tasks_text = collect_meta_info(dataset_path / "meta")
    sub_tasks = collect_subtask_annotations(dataset_path / "annotations")

    features = meta_info.get("features", {}) if isinstance(meta_info, dict) else {}
    statistics = _merge_statistics(
        meta_info.get("statistics") if isinstance(meta_info, dict) else None,
        db_payload,
    )
    frame_total = statistics.get("total_frames") if statistics else None
    frame_range = generate_size_label(int(frame_total or 0))

    dataset_size = format_file_size(calculate_dataset_size(dataset_path))
    dataset_structure = generate_folder_structure(dataset_path, max_files_per_dir=5)
    dataset_slug = _derive_dataset_slug(dataset_path.name)

    robot_type = (
        meta_info.get("robot_type") if isinstance(meta_info, dict) else None
    ) or match_device_name_from_folder(dataset_path.name) or db_payload.get("device_model") or ""

    metadata = UnifiedMetadata()
    metadata.update(**get_default_gated_access_config())
    metadata.update(
        dataset_name=db_payload.get("dataset_name", dataset_path.name),
        dataset_uuid=db_payload.get("dataset_uuid"),
        scene_type=db_payload.get("scene_types") or yaml_payload.get("scene_type") or [],
        atomic_actions=db_payload.get("atomic_actions") or yaml_payload.get("atomic_actions") or [],
        objects=db_payload.get("objects") or yaml_payload.get("objects") or [],
        end_effector_type=_normalize_to_list(
            db_payload.get("end_effector_type")
            or (yaml_payload.get("raw_yaml") or {}).get("end_effector_type")
        ),
        operation_platform_height=db_payload.get("operation_platform_height")
        or (yaml_payload.get("raw_yaml") or {}).get("operation_platform_height"),
        path=dataset_slug,
        video_url=f"./assets/videos/{dataset_slug}.mp4",
        thumbnail_url=f"./assets/thumbnails/{dataset_slug}.jpg",
        frame_range=frame_range,
        dataset_size=dataset_size,
        robot_type=robot_type,
        codebase_version=meta_info.get("codebase_version", "") if isinstance(meta_info, dict) else "",
        statistics=statistics or metadata.statistics,
        splits=meta_info.get("splits") if isinstance(meta_info, dict) and meta_info.get("splits") else metadata.splits,
        data_path=meta_info.get("data_path") if isinstance(meta_info, dict) and meta_info.get("data_path") else metadata.data_path,
        video_path=meta_info.get("video_path") if isinstance(meta_info, dict) and meta_info.get("video_path") else metadata.video_path,
        features=features or metadata.features,
        depth_enabled=bool(meta_info.get("depth_enabled")) if isinstance(meta_info, dict) else False,
        tasks=tasks_text,
        sub_tasks=sub_tasks,
        structure=dataset_structure,
    )

    if features:
        metadata.cameras = build_cameras_from_features(features)
        metadata.observation_space = build_observation_space_from_features(features)
        metadata.action_space = build_action_space_from_features(features)

    metadata.raw = {
        "db_record": db_payload,
        "yaml": yaml_payload.get("raw_yaml", {}),
        "meta": meta_info,
    }

    return metadata


def _normalize_to_list(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        separators = [",", "/", "|"]
        for sep in separators:
            if sep in value:
                return [segment.strip() for segment in value.split(sep) if segment.strip()]
        return [value.strip()] if value.strip() else []
    return [str(value)]


def _derive_dataset_slug(folder_name: str) -> str:
    return (
        folder_name.removesuffix("_qced_hardlink")
        .removesuffix("_hardlink")
        .removesuffix("/")
    )


def _load_dataset_payload(
    db_path: Path,
    dataset_path: Path,
    dataset_uuid: str | None,
) -> dict[str, Any]:
    db = DatasetDatabase(db_path)
    with db.with_session() as session:
        resolved_uuid = dataset_uuid or _lookup_uuid_by_hardlink(session, dataset_path)
        record = _query_dataset_record(session, resolved_uuid, dataset_path.name)
        if record is None:
            raise ValueError(
                f"Failed to locate dataset metadata in DB for dataset '{dataset_path.name}'"
            )
        return _serialize_dataset_record(record)


def _lookup_uuid_by_hardlink(session: Session, dataset_path: Path) -> str | None:
    entry = (
        session.query(DatasetHardLinkDB)
        .filter(DatasetHardLinkDB.hard_link_path == str(dataset_path))
        .first()
    )
    if entry:
        return entry.dataset_uuid
    LOGGER.warning(
        "Hardlink mapping missing for %s, falling back to dataset name lookup",
        dataset_path,
    )
    return None


def _query_dataset_record(
    session: Session,
    dataset_uuid: str | None,
    dataset_name: str,
) -> DatasetDB | None:
    query = session.query(DatasetDB)
    if dataset_uuid:
        dataset = query.filter(DatasetDB.dataset_uuid == dataset_uuid).first()
        if dataset:
            return dataset

    dataset = query.filter(DatasetDB.dataset_name == dataset_name).first()
    if dataset:
        return dataset

    return (
        query.filter(DatasetDB.convert_path.like(f"%{dataset_name}%"))
        .order_by(DatasetDB.id.desc())
        .first()
    )


def _serialize_dataset_record(dataset: DatasetDB) -> dict[str, Any]:
    def _object_to_dict(obj: ObjectDB) -> dict[str, Any]:
        return {
            "object_name": obj.object_name,
            "level1": obj.level1_category,
            "level2": obj.level2_category,
            "level3": obj.level3_category,
            "level4": obj.level4_category,
            "level5": obj.level5_category,
        }

    return {
        "id": dataset.id,
        "dataset_name": dataset.dataset_name,
        "dataset_uuid": dataset.dataset_uuid,
        "device_model": dataset.device_model,
        "end_effector_type": dataset.end_effector_type,
        "operation_platform_height": dataset.operation_platform_height,
        "yaml_file_path": dataset.yaml_file_path,
        "convert_path": dataset.convert_path,
        "scene_types": [scene.name for scene in dataset.scene_types],
        "atomic_actions": [action.action_name for action in dataset.atomic_actions],
        "objects": [_object_to_dict(obj) for obj in dataset.objects],
        "total_episodes": dataset.total_episodes,
    }


def _load_yaml_payload(db_payload: dict[str, Any]) -> dict[str, Any]:
    yaml_path = db_payload.get("yaml_file_path")
    if not yaml_path:
        return {"raw_yaml": {}, "scene_type": [], "atomic_actions": [], "objects": []}

    path = Path(str(yaml_path)).expanduser()
    if not path.exists():
        LOGGER.warning("YAML file %s does not exist, skipping YAML metadata merge", path)
        return {"raw_yaml": {}, "scene_type": [], "atomic_actions": [], "objects": []}

    try:
        return collect_from_yaml(
            yaml_file_path=path,
            dataset_name=db_payload.get("dataset_name", ""),
            dataset_uuid=db_payload.get("dataset_uuid", ""),
        )
    except Exception as exc:  # noqa: PERF203
        LOGGER.warning("Failed to parse YAML file %s: %s", path, exc)
        return {"raw_yaml": {}, "scene_type": [], "atomic_actions": [], "objects": []}


def _merge_statistics(
    meta_stats: dict[str, Any] | None,
    db_payload: dict[str, Any],
) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    if isinstance(meta_stats, dict):
        stats.update({k: v for k, v in meta_stats.items() if v is not None})

    if "total_episodes" not in stats and db_payload.get("total_episodes") is not None:
        stats["total_episodes"] = db_payload["total_episodes"]
    return stats
