'''
本脚本旨在将所有的元数据收集和加载返回流程以及对应的方法全部集成到这个脚本
以实现功能的模块化和统一化，减小后期的维护成本
如果需要修改元数据或修改他们的来源，请直接在这个脚本里进行修改
目前本脚本用于网页的元信息收集和生成yaml，以及数据集上传到Hub的元信息收集和生成README
'''


from pathlib import Path
from typing import Any

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB, DatasetHardLinkDB
from robocoin_dataset.prepare_metadata.metadata_collect_utils import (
    build_action_space_from_features,
    build_cameras_from_features,
    build_observation_space_from_features,
    calculate_dataset_size,
    collect_directory_structure,
    collect_from_yaml,
    collect_meta_info,
    collect_subtask_annotations,
    format_file_size,
    generate_size_label,
    match_device_name_from_folder,
)
from robocoin_dataset.prepare_metadata.unified_metadata_def import UnifiedMetadata


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
    return {
        "extra_gated_prompt": (
            "You agree to not use the dataset to conduct experiments "
            "that cause harm to human subjects."
        ),
        "extra_gated_fields": {
            "Company/Organization": {
                "type": "text",
                "description": (
                    'e.g., "ETH Zurich", "Boston Dynamics", "Independent Researcher"'
                ),
            },
            "Country": {
                "type": "country",
                "description": 'e.g., "Germany", "China", "United States"',
            },
            "Intended use": {
                "type": "text",
                "description": (
                    'e.g., "imitation learning", "policy generalization", '
                    '"bimanual manipulation research"'
                ),
            },
        },
    }


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
            * frame_range: 根据 statistics.total_frames 自动计算的帧数范围标签
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
        yaml_metadata = collect_from_yaml(yaml_file_path, dataset_name, dataset_uuid)
        scene_type = yaml_metadata["scene_type"]
        atomic_actions = yaml_metadata["atomic_actions"]
        objects = yaml_metadata["objects"]
        raw_yaml = yaml_metadata["raw_yaml"]

        # ---- 从 meta/ 和 annotations/ 中收集信息 ----
        meta_dir = ds_path / "meta"
        annotations_dir = ds_path / "annotations"

        meta_info, tasks = collect_meta_info(meta_dir)
        sub_tasks = collect_subtask_annotations(annotations_dir)

    # ---- 计算自动生成字段 ----
    # path / video_url / thumbnail_url
    base_name = ds_path.name.removesuffix("_qced_hardlink").removesuffix("_hardlink")
    path = base_name
    video_url = f"./assets/videos/{path}.mp4"
    thumbnail_url = f"./assets/thumbnails/{path}.jpg"

    # statistics / dataset_size (计算实际文件大小)
    statistics = UnifiedMetadata().statistics  # 默认结构
    statistics.update(meta_info.get("statistics", {}))
    total_frames = int(statistics.get("total_frames", 0) or 0)

    # 计算数据集总文件大小
    dataset_size_bytes = calculate_dataset_size(ds_path)
    dataset_size = format_file_size(dataset_size_bytes)

    # 生成帧数范围标签
    frame_range = generate_size_label(total_frames)

    # depth_enabled / features / splits / data_path / video_path / robot_type / codebase_version
    depth_enabled = bool(meta_info.get("depth_enabled", False))
    features = meta_info.get("features", {})
    splits = meta_info.get("splits", UnifiedMetadata().splits)
    data_path = meta_info.get("data_path", UnifiedMetadata().data_path)
    video_path = meta_info.get("video_path", UnifiedMetadata().video_path)

    # robot_type: Use string matching from names.yml first, fallback to meta_info
    matched_device_name = match_device_name_from_folder(base_name)
    if matched_device_name:
        robot_type = matched_device_name
    else:
        robot_type = meta_info.get("robot_type", "")

    codebase_version = meta_info.get("codebase_version", "")

    # cameras / observation_space / action_space
    cameras = build_cameras_from_features(features) if features else UnifiedMetadata().cameras
    observation_space = (
        build_observation_space_from_features(features)
        if features
        else UnifiedMetadata().observation_space
    )
    action_space = (
        build_action_space_from_features(features)
        if features
        else UnifiedMetadata().action_space
    )

    # 目录结构
    structure = collect_directory_structure(ds_path)

    # 解析末端执行器（可能包含 "/" 分隔多个值）
    raw_end_effector_type = item.end_effector_type or ""
    end_effector_types = [
        part.strip()
        for part in raw_end_effector_type.split("/")
        if part.strip()
    ]

    # 获取数据集访问控制配置
    gated_access_config = get_default_gated_access_config()

    # ---- 阶段 1：创建并初始化 UnifiedMetadata 实例 ----
    # ---- 阶段 2：返回实例 ----
    return UnifiedMetadata(
        # 来自数据库
        dataset_name=dataset_name,
        dataset_uuid=dataset_uuid,
        scene_type=scene_type,
        atomic_actions=atomic_actions,
        end_effector_type=end_effector_types,
        operation_platform_height=item.operation_platform_height,
        objects=objects,
        # 自动生成字段
        path=path,
        video_url=video_url,
        thumbnail_url=thumbnail_url,
        frame_range=frame_range,
        dataset_size=dataset_size,
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
        # 数据集访问控制（HuggingFace Hub gated dataset）
        extra_gated_prompt=gated_access_config["extra_gated_prompt"],
        extra_gated_fields=gated_access_config["extra_gated_fields"],
    )
