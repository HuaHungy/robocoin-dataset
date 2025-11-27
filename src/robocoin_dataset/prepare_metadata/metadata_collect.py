'''
本脚本旨在将所有的元数据收集和加载返回流程以及对应的方法全部集成到这个脚本
以实现功能的模块化和统一化，减小后期的维护成本
如果需要修改元数据或修改他们的来源，请直接在这个脚本里进行修改
目前本脚本用于网页的元信息收集和生成yaml，以及数据集上传到Hub的元信息收集和生成README
'''


import json
import logging
from pathlib import Path
from typing import Any

import yaml

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB, DatasetHardLinkDB
from robocoin_dataset.hub_upload.gen_file.single_dataset_readme_generator import (
    generate_folder_structure,
)
from robocoin_dataset.prepare_metadata.unified_metadata_def import UnifiedMetadata

_logger = logging.getLogger(__name__)


def create_unified_metadata(
    hardlink_path: str | Path,
    db_file_path: str | Path,
    dataset_uuid: str | None = None,
) -> UnifiedMetadata:
    """
    从数据库和本地数据集目录创建并初始化一个标准的 UnifiedMetadata 实例，并返回。
    阶段 1：根据传入的路径收集信息并填充 UnifiedMetadata 各个字段：
        - 从数据库获取的信息 (datasets_new.db):
            * DatasetDB: dataset_name, dataset_uuid, device_model(*可能有错误请不要使用这个字段*),
              end_effector_type(*严格从数据库获取，原始yaml是错误的)
              operation_platform_height
            * yaml_file_path: 用于读取原始 YAML，填充 raw 字段
        - 从原始yaml文件里获取的信息：
            * 多对多关系: scene_types, atomic_actions, objects, 直接从yaml里复制
              这里的yaml是来自datasetDB的yaml_file_path对应的文件
        - 从数据集目录里获取的信息 (也就是hardlink_path对应的目录):
            * meta/info.json: robot_type, codebase_version, statistics, splits,
              data_path, video_path, features, depth_enabled
            * meta/tasks.jsonl: tasks（按行读取 task 字段并用换行拼接）
            * annotations/subtask_annotations.jsonl: sub_tasks（去重排序后的列表）
            * 目录结构: structure（使用 generate_folder_structure 自动生成）
        - 其它自动生成字段:
            * path: 由数据集文件夹名去除 `_qced_hardlink` / `_hardlink` 后得到
            * video_url, thumbnail_url: 根据 path 按网页约定生成
            * size_categories: 根据 statistics.total_frames 自动计算
    阶段 2：返回已经填充好的 UnifiedMetadata 实例。

    Args:
        hardlink_path: 单个数据集的根目录（通常是 *_hardlink 或 *_qced_hardlink 文件夹）。
        db_file_path: SQLite 数据库文件路径（如 db/datasets_new.db）。
        dataset_uuid: 可选，如果不提供，则会根据 dataset_path 在 DatasetHardLinkDB 中自动推断。
    """
    ds_path = Path(hardlink_path).expanduser().absolute()
    db_path = Path(db_file_path).expanduser().absolute()
    db = DatasetDatabase(db_path)

    # ---- 从数据库中获取 DatasetDB 记录 ----
    with db.with_session() as session:
        # 如果没有显式给出 UUID，则通过 hard_link_path 反查
        if dataset_uuid is None:
            hardlink_item = (
                session.query(DatasetHardLinkDB)
                .filter(DatasetHardLinkDB.hard_link_path == str(ds_path))
                .first()
            )
            if hardlink_item is None:
                raise ValueError(
                    f"Cannot find DatasetHardLinkDB record for hard_link_path={ds_path}"
                )
            dataset_uuid = hardlink_item.dataset_uuid

        item = (
            session.query(DatasetDB)
            .filter(DatasetDB.dataset_uuid == dataset_uuid)
            .first()
        )

        if item is None:
            raise ValueError(f"Dataset with uuid={dataset_uuid} not found in DB: {db_path}")

        # 基础字段（来自数据库）
        dataset_name = item.dataset_name
        yaml_file_path = item.yaml_file_path

        # 原始 YAML 内容仅保存在 raw 字段中，方便调试
        # 同时用于获取多对多关系字段 (scene_types, atomic_actions, objects)
        raw_yaml = _load_raw_yaml(yaml_file_path)

        # 直接从原始yaml文件获取多对多关系字段
        scene_type = []
        if "scene_type" in raw_yaml and raw_yaml["scene_type"]:
            scene_type = raw_yaml["scene_type"] if isinstance(raw_yaml["scene_type"], list) else []

        atomic_actions = []
        if "atomic_actions" in raw_yaml and raw_yaml["atomic_actions"]:
            atomic_actions = raw_yaml["atomic_actions"] if isinstance(raw_yaml["atomic_actions"], list) else []

        objects = []
        if "objects" in raw_yaml and raw_yaml["objects"]:
            raw_objects = raw_yaml["objects"] if isinstance(raw_yaml["objects"], list) else []
            objects.extend([
                {
                    "object_name": obj.get("object_name"),
                    "level1": obj.get("level1"),
                    "level2": obj.get("level2"),
                    "level3": obj.get("level3"),
                    "level4": obj.get("level4"),
                    "level5": obj.get("level5"),
                }
                for obj in raw_objects
                if isinstance(obj, dict) and "object_name" in obj
            ])

        # Debug logging for empty fields
        if not scene_type:
            _logger.warning(
                f"Dataset {dataset_name} (UUID: {dataset_uuid}) has empty scene_type in YAML. "
                f"YAML file: {yaml_file_path}"
            )
        if not atomic_actions:
            _logger.warning(
                f"Dataset {dataset_name} (UUID: {dataset_uuid}) has empty atomic_actions in YAML. "
                f"YAML file: {yaml_file_path}"
            )
        if not objects:
            _logger.warning(
                f"Dataset {dataset_name} (UUID: {dataset_uuid}) has empty objects in YAML. "
                f"YAML file: {yaml_file_path}"
            )

        # ---- 从 meta/ 和 annotations/ 中收集信息 ----
        meta_dir = ds_path / "meta"
        annotations_dir = ds_path / "annotations"
        info_file = meta_dir / "info.json"
        tasks_file = meta_dir / "tasks.jsonl"

        meta_info = _load_meta_info(info_file)
        tasks = _load_tasks(tasks_file)
        sub_tasks = _load_subtasks(annotations_dir)

    # ---- 计算自动生成字段 ----
    # path / video_url / thumbnail_url
    base_name = ds_path.name.removesuffix("_qced_hardlink").removesuffix("_hardlink")
    path = base_name
    video_url = f"./assets/videos/{path}.mp4"
    thumbnail_url = f"./assets/thumbnails/{path}.jpg"

    # statistics / size_categories
    statistics = UnifiedMetadata().statistics  # 默认结构
    statistics.update(meta_info.get("statistics", {}))
    total_frames = int(statistics.get("total_frames", 0) or 0)
    size_categories = _generate_size_label(total_frames)

    # depth_enabled / features / splits / data_path / video_path / robot_type / codebase_version
    depth_enabled = bool(meta_info.get("depth_enabled", False))
    features = meta_info.get("features", {})
    splits = meta_info.get("splits", UnifiedMetadata().splits)
    data_path = meta_info.get("data_path", UnifiedMetadata().data_path)
    video_path = meta_info.get("video_path", UnifiedMetadata().video_path)

    # robot_type: Use string matching from names.yml first, fallback to meta_info
    matched_device_name = _match_device_name_from_folder(base_name)
    if matched_device_name:
        robot_type = matched_device_name
    else:
        robot_type = meta_info.get("robot_type", "")

    codebase_version = meta_info.get("codebase_version", "")

    # cameras / observation_space / action_space
    cameras = _build_cameras_from_features(features) if features else UnifiedMetadata().cameras
    observation_space = (
        _build_observation_space_from_features(features)
        if features
        else UnifiedMetadata().observation_space
    )
    action_space = (
        _build_action_space_from_features(features)
        if features
        else UnifiedMetadata().action_space
    )

    # 目录结构
    structure = generate_folder_structure(ds_path, max_files_per_dir=5)

    # ---- 阶段 1：创建并初始化 UnifiedMetadata 实例 ----
    # ---- 阶段 2：返回实例 ----
    return UnifiedMetadata(
        # 来自数据库
        dataset_name=dataset_name,
        dataset_uuid=dataset_uuid,
        scene_type=scene_type,
        atomic_actions=atomic_actions,
        end_effector_type=item.end_effector_type or "",
        operation_platform_height=item.operation_platform_height,
        objects=objects,
        # 自动生成字段
        path=path,
        video_url=video_url,
        thumbnail_url=thumbnail_url,
        size_categories=size_categories,
        # meta/info.json
        robot_type=robot_type,
        codebase_version=codebase_version,
        statistics=statistics,
        splits=splits,
        data_path=data_path,
        video_path=video_path,
        features=features,
        depth_enabled=depth_enabled,
        cameras=cameras,
        observation_space=observation_space,
        action_space=action_space,
        # meta/tasks.jsonl & annotations/
        tasks=tasks,
        sub_tasks=sub_tasks,
        # 目录结构
        structure=structure,
        # 原始 YAML
        raw=raw_yaml,
    )


def _match_device_name_from_folder(dataset_folder_name: str) -> str | None:
    """
    Match device name from names.yml based on dataset folder name string matching.

    This function:
    1. Loads device names from names.yml
    2. Searches for any device name that appears in the dataset_name
    3. Returns the first match found, or None if no match

    Args:
        dataset_name: The dataset folder name to check against

    Returns:
        Matched device name from names.yml, or None if no match found
    """
    # Load names.yml from page_sync module
    names_file = Path(__file__).parent.parent / "page_sync" / "names.yml"
    if not names_file.exists():
        _logger.warning(f"Names file does not exist: {names_file}. Cannot match device name.")
        return None

    try:
        with open(names_file, encoding='utf-8') as f:
            device_names = yaml.safe_load(f)
    except Exception as e:
        _logger.error(f"Failed to load names.yml: {e}. Cannot match device name.")
        return None

    if not isinstance(device_names, list):
        _logger.error(f"names.yml should contain a list, but got {type(device_names)}. Cannot match device name.")
        return None

    # Search for matching device name in dataset_name
    for device_name in device_names:
        if device_name in dataset_folder_name:
            _logger.info(f"Matched device name '{device_name}' in dataset name '{dataset_folder_name}'")
            return device_name

    _logger.debug(f"No device name from names.yml matched in dataset name '{dataset_folder_name}'")
    return None


def _load_subtasks(annotations_dir: Path) -> list[str]:
    """
    从 annotations/subtask_annotations.jsonl 中提取去重后的 subtask 列表。
    逻辑与 dataset_info_util._get_subtasks_from_annotation 基本一致。
    """
    if not annotations_dir.exists():
        return []

    subtask_file = annotations_dir / "subtask_annotations.jsonl"
    if not subtask_file.exists():
        return []

    subtasks_dict: dict[str, str] = {}
    try:
        with subtask_file.open(encoding="utf-8") as f:
            for line in f:
                if line := line.strip():
                    data = json.loads(line)
                    if "subtask" in data:
                        subtask = data["subtask"]
                        key = str(subtask).lower()
                        if key not in subtasks_dict:
                            subtasks_dict[key] = subtask
    except Exception:
        return []

    return [subtasks_dict[k] for k in sorted(subtasks_dict.keys())]


def _load_raw_yaml(yaml_file_path: str | None) -> dict[str, Any]:
    """读取原始 YAML 配置，作为 raw 字段保留（若不存在则返回空字典）。"""
    if not yaml_file_path:
        return {}

    path = Path(yaml_file_path).expanduser()
    if not path.exists():
        return {}

    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _build_cameras_from_features(features: dict[str, Any]) -> list[dict[str, Any]]:
    """
    根据 features 中 observation.images.* 字段生成 cameras 列表。
    返回的每个元素包含基础的相机信息，便于 README 模板统计数量或展示详情。
    """
    cameras: list[dict[str, Any]] = []
    for key, value in features.items():
        if not (isinstance(key, str) and key.startswith("observation.images.")):
            continue
        if not isinstance(value, dict):
            continue

        name = key.split(".")[-1]
        info = value.get("info", {}) if isinstance(value.get("info", {}), dict) else {}
        camera = {
            "key": key,
            "name": name,
            "dtype": value.get("dtype"),
            "shape": value.get("shape"),
            "resolution": [
                info.get("video.height"),
                info.get("video.width"),
            ],
            "fps": info.get("video.fps"),
            "is_depth": bool(info.get("video.is_depth_map", False)),
        }
        cameras.append(camera)

    return cameras


def _build_observation_space_from_features(features: dict[str, Any]) -> dict[str, Any]:
    """
    根据 features 构建 observation_space 字段。
    - images: 所有 observation.images.* 的摘要信息列表
    - state: observation.state 的 shape / names / dtype 信息
    """
    images: list[dict[str, Any]] = []
    for key, value in features.items():
        if not (isinstance(key, str) and key.startswith("observation.images.")):
            continue
        if not isinstance(value, dict):
            continue
        images.append(
            {
                "key": key,
                "dtype": value.get("dtype"),
                "shape": value.get("shape"),
                "names": value.get("names"),
            }
        )

    state_info: dict[str, Any] | None = None
    state_feat = features.get("observation.state")
    if isinstance(state_feat, dict):
        state_info = {
            "dtype": state_feat.get("dtype"),
            "shape": state_feat.get("shape"),
            "names": state_feat.get("names"),
        }

    obs_space = UnifiedMetadata().observation_space
    # 如果能解析出更详细的信息，则覆盖默认的 auto_generated 占位
    if images:
        obs_space["images"] = images
    if state_info is not None:
        obs_space["state"] = state_info
    return obs_space


def _build_action_space_from_features(features: dict[str, Any]) -> dict[str, Any] | str:
    """
    根据 features 构建 action_space 字段。
    如果存在 features['action']，则返回其 shape / names / dtype 的摘要；
    否则保留默认的 auto_generated。
    """
    action_feat = features.get("action")
    if isinstance(action_feat, dict):
        return {
            "dtype": action_feat.get("dtype"),
            "shape": action_feat.get("shape"),
            "names": action_feat.get("names"),
        }
    return UnifiedMetadata().action_space


def _generate_size_label(size: int) -> str:
    """
    根据 total_frames 自动生成 size_categories 标签。
    规则与 dataset_info_util.py 中保持一致。
    """
    if size < 1000:
        return "<1K"
    if size < 10000:
        return "1K-10K"
    if size < 100000:
        return "10K-100K"
    if size < 1000000:
        return "100K-1M"
    if size < 10000000:
        return "1M-10M"
    if size < 100000000:
        return "10M-100M"
    if size < 1000000000:
        return "100M-1B"
    if size < 10000000000:
        return "1B-10B"
    if size < 100000000000:
        return "10B-1T"
    return ">1T"


def _load_meta_info(meta_info_file: Path) -> dict[str, Any]:
    """从 meta/info.json 中提取 UnifiedMetadata 需要的字段。"""
    if not meta_info_file.exists():
        return {}

    try:
        with meta_info_file.open(encoding="utf-8") as f:
            meta_info: dict[str, Any] = json.load(f)
    except Exception:
        return {}

    extracted: dict[str, Any] = {}

    # 机器人 & 代码版本
    if "robot_type" in meta_info:
        extracted["robot_type"] = meta_info["robot_type"]
    if "codebase_version" in meta_info:
        extracted["codebase_version"] = meta_info["codebase_version"]

    # 统计信息
    statistics: dict[str, Any] = {}
    for key in [
        "total_episodes",
        "total_frames",
        "total_tasks",
        "total_videos",
        "total_chunks",
        "chunks_size",
        "fps",
        "total_duration",
        "video_resolution",
        "state_dim",
        "action_dim",
        "camera_views",
    ]:
        if key in meta_info:
            statistics[key] = meta_info[key]
    if statistics:
        extracted["statistics"] = statistics

    # 数据组织
    if "splits" in meta_info:
        extracted["splits"] = meta_info["splits"]
    if "data_path" in meta_info:
        extracted["data_path"] = meta_info["data_path"]
    if "video_path" in meta_info:
        extracted["video_path"] = meta_info["video_path"]

    # features & depth_enabled
    if "features" in meta_info:
        features = meta_info["features"]
        extracted["features"] = features

        depth_enabled = False
        for key, value in features.items():
            if key.startswith("observation.images.") and isinstance(value, dict):
                info = value.get("info", {})
                if info.get("video.is_depth_map", False):
                    depth_enabled = True
                    break
        extracted["depth_enabled"] = depth_enabled

    return extracted


def _load_tasks(tasks_file: Path) -> str:
    """从 meta/tasks.jsonl 中读取所有 task 字段并拼接为一个字符串。"""
    if not tasks_file.exists():
        return ""

    tasks: list[str] = []
    try:
        with tasks_file.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    task = data.get("task", "")
                    if task:
                        tasks.append(task)
                except json.JSONDecodeError:
                    continue
    except Exception:
        return ""

    return "\n".join(tasks)
