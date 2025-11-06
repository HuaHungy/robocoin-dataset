from enum import Enum as PyEnum

from sqlalchemy import (
    Column,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


# =====================
# 枚举类型
# =====================


class TaskStatus(str, PyEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# =====================
# 主表：DatasetDB
# =====================


class DatasetDB(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    dataset_name = Column(String(255), unique=False, index=True, nullable=False)

    # ✅ 核心：dataset_uuid 作为全局唯一业务标识
    dataset_uuid = Column(String(255), unique=True, index=True, nullable=False)

    # 入库相关
    device_model = Column(String(100), nullable=True)
    device_model_version = Column(String(100), nullable=True)
    end_effector_type = Column(String(100), nullable=True)
    operation_platform_height = Column(Float, nullable=True)
    yaml_file_path = Column(String(255), nullable=True)

    data_path = Column(String(255), nullable=True)

    convert_path = Column(String(255), nullable=True)

    # 格式转换相关
    convert_test_status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=True)
    convert_test_version = Column(Integer, nullable=True, default=0)

    convert_status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=True)
    convert_version_ps = Column(Integer, nullable=True, default=0)
    convert_version = Column(Integer, nullable=True, default=0)

    total_episodes = Column(Integer, nullable=True, default=0)  # 总episode数
    converted_episodes = Column(Integer, nullable=True, default=0)  # 成功转换的episode数
    skipped_episodes = Column(Integer, nullable=True, default=0)  # 跳过的episode数

    convert_err_msg = Column(Text, nullable=True)

    # state 和 action后处理及Replay相关
    sa_dpp_status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=True)
    sa_dpp_version_ps = Column(Integer, nullable=True, default=0)
    sa_dpp_version = Column(Integer, nullable=True, default=0)
    sa_dpp_err_msg = Column(Text, nullable=True)

    sim_replay_status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=True)
    sim_replay_version_ps = Column(Integer, nullable=True, default=0)
    sim_replay_version = Column(Integer, nullable=True, default=0)
    sim_replay_error_msg = Column(Text, nullable=True)

    # 运动标注相关
    motion_annotation_status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=True)
    motion_annotation_version_ps = Column(Integer, nullable=True, default=0)
    motion_annotation_version = Column(Integer, nullable=True, default=0)
    motion_annotation_err_msg = Column(Text, nullable=True)

    # subtask标注相关
    ## 视频哈希相关
    video_hash_status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=True)
    video_hash_version_ps = Column(Integer, nullable=True, default=0)
    video_hash_version = Column(Integer, nullable=True, default=0)
    video_hash_err_msg = Column(Text, nullable=True)

    ## 视频匹配相关
    video_match_status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=True)
    video_match_version_ps = Column(Integer, nullable=True, default=0)
    video_match_version = Column(Integer, nullable=True, default=0)
    video_match_err_msg = Column(Text, nullable=True)

    ## 子任务标注相关
    video_ori_subtask_annotation_status = Column(
        Enum(TaskStatus), default=TaskStatus.PENDING, nullable=True
    )
    video_ori_subtask_annotation_version_ps = Column(Integer, nullable=True, default=0)
    video_ori_subtask_annotation_version = Column(Integer, nullable=True, default=0)
    video_ori_subtask_annotation_err_msg = Column(Text, nullable=True)

    ## 优化后的子任务标注相关
    video_opt_subtask_annotation_status = Column(
        Enum(TaskStatus), default=TaskStatus.PENDING, nullable=True
    )
    video_opt_subtask_annotation_version_ps = Column(Integer, nullable=True, default=0)
    video_opt_subtask_annotation_version = Column(Integer, nullable=True, default=0)
    video_opt_subtask_annotation_err_msg = Column(Text, nullable=True)

    ## 嵌入子任务标注数据相关
    video_embed_subtask_annotation_status = Column(
        Enum(TaskStatus), default=TaskStatus.PENDING, nullable=True
    )
    video_embed_subtask_annotation_version_ps = Column(Integer, nullable=True, default=0)
    video_embed_subtask_annotation_version = Column(Integer, nullable=True, default=0)
    video_embed_subtask_annotation_err_msg = Column(Text, nullable=True)

    ## 场景标注相关
    scene_annotation_status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=True)
    scene_annotation_version_ps = Column(Integer, nullable=True, default=0)
    scene_annotation_version = Column(Integer, nullable=True, default=0)
    scene_annotation_err_msg = Column(Text, nullable=True)

    # 数据合并相关
    data_merge_status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=True)
    data_merge_version_ps_sta = Column(Integer, nullable=True, default=0)
    data_merge_version_ps_sa = Column(Integer, nullable=True, default=0)
    data_merge_version_ps_ma = Column(Integer, nullable=True, default=0)
    data_merge_version = Column(Integer, nullable=True, default=0)
    data_merge_err_msg = Column(Text, nullable=True)

    # dataLoader 检测相关
    data_loader_detection_status = Column(
        Enum(TaskStatus), default=TaskStatus.PENDING, nullable=True
    )
    data_loader_detection_version_ps = Column(Integer, nullable=True, default=0)
    data_loader_detection_version = Column(Integer, nullable=True, default=0)
    data_loader_detection_err_msg = Column(Text, nullable=True)

    # 人工检测相关
    visualize_check_status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=True)
    visualize_check_version_ps = Column(Integer, nullable=True, default=0)
    visualize_check_version = Column(Integer, nullable=True, default=0)
    visualize_check_err_msg = Column(Text, nullable=True)

    # 数据集上传相关
    ## modelscope
    ms_upload_status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=True)
    ms_upload_version_ps = Column(Integer, nullable=True, default=0)
    ms_upload_version = Column(Integer, nullable=True, default=0)
    ms_upload_err_msg = Column(Text, nullable=True)

    ## huggingface
    huggingface_upload_status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=True)
    huggingface_upload_version_ps = Column(Integer, nullable=True, default=0)
    huggingface_upload_version = Column(Integer, nullable=True, default=0)
    huggingface_upload_err_msg = Column(Text, nullable=True)

    # 数据集信息同步相关
    dataset_info_sync_status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=True)
    dataset_info_sync_version_ps = Column(Integer, nullable=True, default=0)
    dataset_info_sync_version = Column(Integer, nullable=True, default=0)
    dataset_info_sync_err_msg = Column(Text, nullable=True)

    # 多对多关系
    scene_types = relationship(
        "SceneTypeDB", secondary="dataset_scene_types", back_populates="datasets"
    )
    task_descriptions = relationship(
        "TaskDescriptionDB", secondary="dataset_task_descriptions", back_populates="datasets"
    )
    objects = relationship("ObjectDB", secondary="dataset_objects", back_populates="datasets")
    atomic_actions = relationship(
        "AtomicActionDB", secondary="dataset_atomic_actions", back_populates="datasets"
    )


class SceneTypeDB(Base):
    __tablename__ = "scene_types"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)

    # 反向关系
    datasets = relationship(
        "DatasetDB", secondary="dataset_scene_types", back_populates="scene_types"
    )


class AtomicActionDB(Base):
    __tablename__ = "atomic_actions"
    id = Column(Integer, primary_key=True, index=True)
    action_name = Column(String(100), unique=True, nullable=False)

    # 反向关系
    datasets = relationship(
        "DatasetDB", secondary="dataset_atomic_actions", back_populates="atomic_actions"
    )


class TaskDescriptionDB(Base):
    __tablename__ = "task_descriptions"
    id = Column(Integer, primary_key=True, index=True)
    desc = Column(String(255), unique=True, index=True, nullable=False)

    # 反向关系：注意是 "datasets"，不是 "task_descriptions"
    datasets = relationship(
        "DatasetDB", secondary="dataset_task_descriptions", back_populates="task_descriptions"
    )


class ObjectDB(Base):
    __tablename__ = "object"
    id = Column(Integer, primary_key=True, index=True)
    object_name = Column(String(100), nullable=False, index=True)

    level1_category = Column(String(100), unique=False, nullable=True)
    level2_category = Column(String(100), unique=False, nullable=True)
    level3_category = Column(String(100), unique=False, nullable=True)
    level4_category = Column(String(100), unique=False, nullable=True)
    level5_category = Column(String(100), unique=False, nullable=True)

    # 反向关系：ObjectDB -> DatasetDB 多对多
    datasets = relationship("DatasetDB", secondary="dataset_objects", back_populates="objects")


# =====================
# 多对多关联表
# =====================

dataset_scene_types = Table(
    "dataset_scene_types",
    Base.metadata,
    Column("dataset_id", Integer, ForeignKey("datasets.id"), primary_key=True),
    Column("scene_type_id", Integer, ForeignKey("scene_types.id"), primary_key=True),
)

dataset_task_descriptions = Table(
    "dataset_task_descriptions",
    Base.metadata,
    Column("dataset_id", Integer, ForeignKey("datasets.id"), primary_key=True),
    Column("task_description_id", Integer, ForeignKey("task_descriptions.id"), primary_key=True),
)

dataset_atomic_actions = Table(
    "dataset_atomic_actions",
    Base.metadata,
    Column("dataset_id", Integer, ForeignKey("datasets.id"), primary_key=True),
    Column("atomic_actions_id", Integer, ForeignKey("atomic_actions.id"), primary_key=True),
)


dataset_objects = Table(
    "dataset_objects",
    Base.metadata,
    Column("dataset_id", Integer, ForeignKey("datasets.id"), primary_key=True),
    Column("object_id", Integer, ForeignKey("object.id"), primary_key=True),
)


class VideoHashDB(Base):
    __tablename__ = "video_hash"
    id = Column(Integer, primary_key=True, index=True)
    dataset_uuid = Column(String(255), index=True, nullable=False)
    ep_idx = Column(Integer, index=True, nullable=False)
    frame_num = Column(Integer, index=True, nullable=False)
    video_path = Column(String(255), index=False, nullable=False, unique=True)
    file_hash = Column(String(255), index=False, nullable=False)
    image_hashes = Column(Text, index=False, nullable=False)


class StAnnotationVideoDB(Base):
    __tablename__ = "st_annotation_video"

    id = Column(Integer, primary_key=True, index=True)
    # 视频 URL 唯一
    video_url = Column(String(255), nullable=False, unique=True, index=True)
    # 本地路径唯一
    local_video_path = Column(String(255), nullable=True, unique=True, index=True)

    # 下载状态
    download_status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False)

    video_hash_status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False)
    # 文件哈希（如 MD5/SHA1）
    file_hash = Column(String(255), nullable=True, index=True)

    # 视频内容哈希（如感知哈希）
    video_hash = Column(Text, nullable=True)  # 不建索引，太大

    # 总帧数
    frame_num = Column(Integer, nullable=True, default=None)  # 默认 None 比 0 更准确

    # 关联的标注片段
    annotations = relationship(
        "UrlVideoStAnnotationDB", back_populates="video", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_st_annotation_video_video_hash_status", "video_hash_status"),)


class UrlVideoStAnnotationDB(Base):
    __tablename__ = "url_video_st_annotation"

    id = Column(Integer, primary_key=True, index=True)

    # 外键关联到 st_annotation_video.id
    video_id = Column(
        Integer,
        ForeignKey("st_annotation_video.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 如果还需要快速按 URL 查询标注，可以保留 video_url 但不强制唯一
    # video_url = Column(String(255), index=True)  # 可选：用于快速查询，非必需

    annotation = Column(Text, nullable=False)
    start_frame_idx = Column(Integer, nullable=False, index=True)
    end_frame_idx = Column(Integer, nullable=False, index=True)

    # 关联回主表
    video = relationship("StAnnotationVideoDB", back_populates="annotations")

    # 复合索引：按 video_id + 时间范围查询更快
    __table_args__ = (
        Index(
            "ix_url_video_st_annotation_video_frames",
            "video_id",
            "start_frame_idx",
            "end_frame_idx",
        ),
    )


class VideoMatchDB(Base):
    __tablename__ = "video_match"
    id = Column(Integer, primary_key=True, index=True)
    dataset_uuid = Column(String(255), index=True, nullable=False)
    episode_idx = Column(Integer, index=True, nullable=False)
    url_video_id = Column(
        Integer,
        ForeignKey("st_annotation_video.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class VideoStAnnotationDB(Base):
    __tablename__ = "video_st_annotation"
    id = Column(Integer, primary_key=True, index=True)
    dataset_uuid = Column(String(255), index=True, nullable=False)
    episode_idx = Column(Integer, index=True, nullable=False)
    start_frame_idx = Column(Integer, nullable=False, index=True)
    end_frame_idx = Column(Integer, nullable=False, index=True)
    annotation = Column(Text, nullable=False)


class VideoOptStAnnotationDB(Base):
    __tablename__ = "video_opt_st_annotation"
    id = Column(Integer, primary_key=True, index=True)
    dataset_uuid = Column(String(255), index=True, nullable=False)
    episode_idx = Column(Integer, index=True, nullable=False)
    start_frame_idx = Column(Integer, nullable=False, index=True)
    end_frame_idx = Column(Integer, nullable=False, index=True)
    annotation = Column(Text, nullable=False)


class DatasetHardLinkDB(Base):
    __tablename__ = "dataset_hard_link"
    id = Column(Integer, primary_key=True, index=True)
    dataset_uuid = Column(String(255), index=True, nullable=False)
    hard_link_path = Column(String(255), index=True, nullable=True)
