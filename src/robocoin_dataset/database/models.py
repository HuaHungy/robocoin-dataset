from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from sqlalchemy.types import LargeBinary

Base = declarative_base()


# =====================
# 枚举类型
# =====================


class TaskStatus(str, PyEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# =====================
# 主表：DatasetDB
# =====================


class DatasetDB(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    dataset_name = Column(String(255), unique=False, index=True, nullable=False)

    # ✅ 核心：dataset_uuid 作为全局唯一业务标识
    dataset_uuid = Column(String(255), unique=True, index=True, nullable=False)

    device_model = Column(String(100), nullable=False)
    end_effector_type = Column(String(100), nullable=False)
    operation_platform_height = Column(Float, nullable=True)
    yaml_file_path = Column(String(255), nullable=True, unique=True)

    # 多对多关系
    scene_types = relationship(
        "SceneTypeDB", secondary="dataset_scene_types", back_populates="datasets"
    )
    task_descriptions = relationship(
        "TaskDescriptionDB", secondary="dataset_task_descriptions", back_populates="datasets"
    )
    objects = relationship("ObjectDB", secondary="dataset_objects", back_populates="datasets")


# =====================
# 分类与多对多表
# =====================


class SceneTypeDB(Base):
    __tablename__ = "scene_types"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)

    # 反向关系
    datasets = relationship(
        "DatasetDB", secondary="dataset_scene_types", back_populates="scene_types"
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

dataset_objects = Table(
    "dataset_objects",
    Base.metadata,
    Column("dataset_id", Integer, ForeignKey("datasets.id"), primary_key=True),
    Column("object_id", Integer, ForeignKey("object.id"), primary_key=True),
)


# =====================
# 独立状态表：使用 dataset_uuid 关联
# =====================


class AnnotationDB(Base):
    __tablename__ = "annotations"

    id = Column(Integer, primary_key=True, index=True)

    # ✅ 使用 dataset_uuid 作为关联字段
    dataset_uuid = Column(String(255), index=True, nullable=False)

    # 标注状态
    annotation_status = Column(Boolean, default=False, nullable=False)

    # ✅ 唯一约束：确保一个数据集最多一条标注记录
    __table_args__ = (UniqueConstraint("dataset_uuid", name="uix_dataset_uuid_annotation"),)


class LeFormatConvertDB(Base):
    __tablename__ = "lerobot_format_convert"

    id = Column(Integer, primary_key=True, index=True)

    # ✅ 使用 dataset_uuid 作为关联字段
    dataset_uuid = Column(String(255), index=True, nullable=False)

    convert_status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False)
    convert_path = Column(String(255), nullable=True)  # 移除 unique=True，允许多个不同路径

    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),  # 插入时默认时间
        onupdate=func.now(),  # 更新时自动更新为当前时间
        nullable=False,
    )

    # 📝 新增字段：最后更新信息（可用于记录状态变更详情、错误信息等）
    err_message = Column(
        Text,  # 使用 Text 类型支持较长内容
        nullable=True,  # 允许为空，初始无信息
    )

    # ✅ 唯一约束：一个 uuid 最多一个转换记录
    __table_args__ = (UniqueConstraint("dataset_uuid", name="uix_dataset_uuid_convert"),)


class LeFormatConvertTestDB(Base):
    __tablename__ = "lerobot_format_convert_test"

    id = Column(Integer, primary_key=True, index=True)

    # ✅ 使用 dataset_uuid 作为关联字段
    dataset_uuid = Column(String(255), index=True, nullable=False)

    convert_status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False)
    convert_path = Column(String(255), nullable=True)  # 移除 unique=True，允许多个不同路径

    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),  # 插入时默认时间
        onupdate=func.now(),  # 更新时自动更新为当前时间
        nullable=False,
    )

    # 📝 新增字段：最后更新信息（可用于记录状态变更详情、错误信息等）
    err_message = Column(
        Text,  # 使用 Text 类型支持较长内容
        nullable=True,  # 允许为空，初始无信息
    )

    # ✅ 唯一约束：一个 uuid 最多一个转换记录
    __table_args__ = (UniqueConstraint("dataset_uuid", name="uix_dataset_uuid_convert"),)


class EpisodeFrameDB(Base):
    __tablename__ = "episode_frames"

    id = Column(Integer, primary_key=True, index=True)

    # 存储 dataset_uuid（字符串格式）
    dataset_uuid = Column(String(255), index=True, nullable=False)  # 改为 255，与 datasets 表一致

    episode_index = Column(Integer, index=True, nullable=False)
    frames_num = Column(Integer, nullable=False)


# class SubtaskAnnotationDB(Base):
#     __tablename__ = "subtask_annotations"

#     id = Column(Integer, primary_key=True, index=True)

#     # 存储 dataset_uuid（字符串格式）
#     dataset_uuid = Column(String(255), index=True, nullable=False)  # 改为 255，与 datasets 表一致

#     episode_index = Column(Integer, index=True, nullable=False, unique=True)
#     frame_start_index = Column(Integer, index=True, nullable=False)
#     frame_end_index = Column(Integer, index=True, nullable=False)
#     subtask_annotation = Column(String(255), nullable=False)
#     convert_status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False)


class SubtaskAnnotationDB(Base):
    __tablename__ = "subtask_annotation"

    id = Column(Integer, primary_key=True, index=True)

    # 存储 dataset_uuid（字符串格式）
    dataset_uuid = Column(
        String(255), index=True, nullable=False, unique=True
    )  # 改为 255，与 datasets 表一致

    annotation_status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False)


class DmvAnnotationDB(Base):
    __tablename__ = "device_model_annotation"

    id = Column(Integer, primary_key=True, index=True)

    # 存储 dataset_uuid（字符串格式）
    dataset_uuid = Column(
        String(255), index=True, nullable=False, unique=True
    )  # 改为 255，与 datasets 表一致

    annotation_status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False)

    annotatio_file_path = Column(String(255), nullable=True)

    device_model = Column(String(255), nullable=True)

    device_model_version = Column(String(255), nullable=True)


class SubtaskAnnotationJsonDB(Base):
    __tablename__ = "subtask_annotation_json"

    id = Column(Integer, primary_key=True, index=True)
    json_content = Column(Text, nullable=False, index=False)
    video_url = Column(String(255), index=True, unique=True, nullable=False)

    # 关系：一个 annotation 有一个 download 记录
    download_info = relationship(
        "SubtaskAnnotationVideoDownloadDB",
        uselist=False,
        back_populates="annotation",
    )


class DownloadStatus(str, PyEnum):
    PENDING = "PENDING"
    DOWNLOADING = "DOWNLOADING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class SubtaskAnnotationVideoDownloadDB(Base):
    __tablename__ = "subtask_annotation_video_download"

    id = Column(Integer, primary_key=True, index=True)
    annotation_id = Column(
        Integer, ForeignKey("subtask_annotation_json.id"), nullable=False, index=True
    )
    video_download_path = Column(String(255), index=True, nullable=True)
    download_status = Column(
        Enum(DownloadStatus), default=DownloadStatus.PENDING, nullable=False, index=True
    )
    frame_num = Column(Integer, nullable=True, index=True)
    video_matched_status = Column(Boolean, default=False, nullable=False, index=True)

    # 关系：一个 download 有一个 file_hash
    file_hash = relationship(
        "SubtaskAnnotationVideoFileHashDB",
        uselist=False,
        back_populates="download",
        cascade="all, delete-orphan",  # 删除 download 时自动删除 hash
    )
    # 反向关系字段
    annotation = relationship("SubtaskAnnotationJsonDB", back_populates="download_info")
    image_hash = relationship(
        "SubtaskAnnotationVideoImageHashDB",
        uselist=False,
        back_populates="download",
        cascade="all, delete-orphan",
    )


class FileHashStatus(str, PyEnum):
    PENDING = "PENGDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PROCESSING = "PROCESSING"


class SubtaskAnnotationVideoFileHashDB(Base):
    __tablename__ = "subtask_annotation_video_file_hash"

    id = Column(Integer, primary_key=True, index=True)
    download_id = Column(
        Integer, ForeignKey("subtask_annotation_video_download.id"), nullable=False, index=True
    )
    sha256 = Column(String(64), index=True, nullable=True)
    hash_status = Column(
        Enum(FileHashStatus), default=FileHashStatus.PENDING, nullable=False, index=True
    )

    # 反向关系
    download = relationship(
        "SubtaskAnnotationVideoDownloadDB",  # 引用 download 表类名
        back_populates="file_hash",
    )


class ImageHashStatus(str, PyEnum):
    PENDING = "PENDING"
    PROCESSING = "PROGRESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class SubtaskAnnotationVideoImageHashDB(Base):
    __tablename__ = "subtask_annotation_video_image_hashes"

    id = Column(Integer, primary_key=True, index=True)

    # 外键：关联到下载表，表示这个 image hash 属于哪个下载的视频
    download_id = Column(
        Integer, ForeignKey("subtask_annotation_video_download.id"), nullable=False, index=True
    )

    # 常见的感知哈希类型（以 LargeBinary 存储）
    image_hashes = Column(LargeBinary, index=False, nullable=True)  # perceptual hash
    image_hash_status = Column(
        Enum(ImageHashStatus), default=ImageHashStatus.PENDING, nullable=False, index=True
    )

    # 关系：反向关联到 download 表
    download = relationship(
        "SubtaskAnnotationVideoDownloadDB",
        back_populates="image_hash",  # 对应 download 表中的字段名
    )


class DatasetAnnotationCorrespondingDB(Base):
    __tablename__ = "dataset_annotation_corresponding"
    id = Column(Integer, primary_key=True, index=True)
    dataset_uuid = Column(String, index=True, unique=True, nullable=False)
    error_msg= Column(Text, nullable=True)
    corresponding_status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.FAILED)


class EpisodeSubtaskAnnotationCorrespondingDB(Base):
    __tablename__ = "episode_subtask_annotation_corresponding"

    id = Column(Integer, primary_key=True, index=True)

    dataset_uuid = Column(String(255), index=True, nullable=False)
    episode_idx = Column(Integer, index=False, nullable=False)
    annotation_json_id = Column(
        Integer, ForeignKey("subtask_annotation_json.id"), nullable=True, index=True
    )
    __table_args__ = (UniqueConstraint("dataset_uuid", "episode_idx", name="uix_dataset_episode"),)


class EpisodeSubtaskAnnotationContentDB(Base):
    __tablename__ = "episode_subtask_annotation_content"

    id = Column(Integer, primary_key=True, index=True)

    json_id = Column(
        Integer,
        ForeignKey("episode_subtask_annotation_corresponding.id"),
        nullable=False,
        index=True,
    )
    annotation_content = Column(Text, nullable=False)


class EpisodeRangeSubtaskAnnotationDB(Base):
    __tablename__ = "episode_range_subtask_annotation"

    id = Column(Integer, primary_key=True, index=True)

    episode_id = Column(
        Integer, ForeignKey("episode_subtask_annotation_content.id"), index=True, nullable=False
    )

    range_from_frame_idx = Column(Integer, nullable=False)
    range_to_frame_idx = Column(Integer, nullable=False)

    subtask_annotation = Column(String)
