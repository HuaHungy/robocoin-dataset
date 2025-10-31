import logging
import traceback
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import tqdm
from sqlalchemy import and_, or_

from robocoin_dataset.data_post_process import DataPostProcessorBase
from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DatasetDB,
    TaskStatus,
    VideoHashDB,
)


def scene_annotations_to_frame_array(
    scene_annotations: list[dict],
    max_objects_num: int = 10,
    episode_frame_nums: dict[int, int] = None,
) -> list[np.ndarray]:
    """
    将场景标注转换为帧级别的数组
    
    Args:
        scene_annotations: 场景标注列表，每个元素包含episode_idx, objects等信息
        max_objects_num: 每帧最大对象数量
        episode_frame_nums: 每个episode的帧数
    
    Returns:
        每个episode的场景标注数组列表
    """
    episodes = defaultdict(list)
    
    # 按episode分组
    for annotation in scene_annotations:
        ep_idx = annotation.get('episode_idx', 0)
        objects = annotation.get('objects', [])
        scene_type = annotation.get('scene_type', 'unknown')
        
        # 将对象信息编码为整数
        object_ids = []
        for obj in objects[:max_objects_num]:
            # 简单的对象ID编码，可以根据需要扩展
            if isinstance(obj, dict):
                obj_name = obj.get('name', 'unknown')
                obj_id = hash(obj_name) % 1000  # 简单的哈希编码
            else:
                obj_id = hash(str(obj)) % 1000
            object_ids.append(obj_id)
        
        episodes[ep_idx].append({
            'objects': object_ids,
            'scene_type': scene_type,
        })

    result = []
    episode_indices = sorted(episodes.keys())

    for ep_idx in episode_indices:
        annotations = episodes[ep_idx]

        if episode_frame_nums and ep_idx in episode_frame_nums:
            max_frame = episode_frame_nums[ep_idx]
        else:
            max_frame = 100  # 默认帧数

        # 创建场景标注数组：[frame_num, max_objects_num + 1]
        # 最后一列存储场景类型ID
        frame_array = np.full(
            (max_frame, max_objects_num + 1),
            -1,
            dtype=np.int32,
        )

        # 如果有标注数据，应用到所有帧
        if annotations:
            # 使用第一个标注作为整个episode的标注
            annotation = annotations[0]
            objects = annotation['objects']
            scene_type = annotation['scene_type']
            
            # 场景类型编码
            scene_type_id = hash(scene_type) % 100 if scene_type != 'unknown' else -1
            
            for frame_idx in range(max_frame):
                # 填充对象信息
                for i, obj_id in enumerate(objects[:max_objects_num]):
                    frame_array[frame_idx, i] = obj_id
                
                # 填充场景类型
                frame_array[frame_idx, max_objects_num] = scene_type_id

        result.append(frame_array)

    return result


class SceneAnnotationDataPostProcessor(DataPostProcessorBase):
    """场景标注数据后处理器"""
    
    def __init__(
        self,
        convert_path: str | Path,
        scene_annotations: list[str],
        episode_scene_indices: list[np.ndarray],
    ) -> None:
        self.feature_key = "scene_annotation"
        super().__init__(
            convert_path=convert_path,
            data_post_process_type=self.feature_key,
            data_feature_keys=[self.feature_key],
        )

        self.scene_annotations = scene_annotations
        self.episode_scene_indices = episode_scene_indices

    def prepare_processing(self) -> None:
        """准备处理，写入场景标注JSONL文件"""
        self.write_scene_jsonl_file()

    def process_episode_data(self, ori_data: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """处理episode数据"""
        ep_idx = self.episode_idx

        if ep_idx >= len(self.episode_scene_indices):
            raise ValueError(
                f"ep_idx: {ep_idx} >= len(self.episode_scene_indices): {len(self.episode_scene_indices)}"
            )

        return {self.feature_key: self.episode_scene_indices[ep_idx]}

    def get_modified_feature_names(self) -> dict[str, list[str]]:
        """返回修改后的特征名称"""
        return {self.feature_key: None}

    def write_scene_jsonl_file(self) -> None:
        """写入场景标注JSONL文件"""
        scene_jsonl_file_path = self.convert_path / "annotations/scene_annotations.jsonl"
        scene_jsonl_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(scene_jsonl_file_path, "w") as f:
            for i, annotation in enumerate(self.scene_annotations):
                f.write(f'{{"scene_index": {i}, "scene": "{annotation}"}}\n')


class DatasetSceneAnnotationEmbedding:
    """数据集场景标注嵌入处理类"""
    
    def __init__(
        self,
        db_file_path: str | Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)

    def sync_dataset_scene_annotation_embedding_status(self) -> None:
        """同步数据集场景标注嵌入状态"""
        with self.db.with_session() as session:
            try:
                query = session.query(DatasetDB).filter(
                    and_(
                        # 必要前提：场景标注必须成功
                        DatasetDB.scene_annotation_status == TaskStatus.COMPLETED,
                        # 两个触发分支
                        or_(
                            # 分支1: 正在排队
                            DatasetDB.video_embed_subtask_annotation_status == TaskStatus.PENDING,
                            # 分支2: 已完成但版本过期
                            and_(
                                DatasetDB.video_embed_subtask_annotation_status == TaskStatus.COMPLETED,
                                DatasetDB.video_embed_subtask_annotation_version_ps
                                < DatasetDB.scene_annotation_version,
                            ),
                        ),
                    )
                )

                for item in query.all():
                    item.video_embed_subtask_annotation_status = TaskStatus.PENDING
                    item.video_embed_subtask_annotation_version = (
                        item.video_embed_subtask_annotation_version + 1
                    )
                    item.video_embed_subtask_annotation_version_ps = (
                        item.scene_annotation_version
                    )
                session.commit()
            except Exception as e:
                self.logger.warning(f"场景标注嵌入状态字段不存在，跳过状态同步: {e}")

    def gen_one_dataset_scene_annotation_embedding_task(self) -> tuple[str, str]:
        """生成一个数据集场景标注嵌入任务"""
        with self.db.with_session() as session:
            try:
                query = session.query(DatasetDB).filter(
                    and_(
                        DatasetDB.scene_annotation_status == TaskStatus.COMPLETED,
                        DatasetDB.video_embed_subtask_annotation_status == TaskStatus.PENDING,
                    )
                )
                item = query.first()
                if not item:
                    return None, None

                item.video_embed_subtask_annotation_status = TaskStatus.PROCESSING
                session.commit()
                return item.dataset_uuid, item.convert_path
            except Exception as e:
                self.logger.warning(f"场景标注嵌入状态字段不存在，使用简化逻辑: {e}")
                return None, None

    def _embed_scene_annotation(self, dataset_uuid: str, repo_path: str | Path) -> None:
        """嵌入场景标注数据"""
        repo_path = Path(repo_path).expanduser().absolute()
        
        # 查找场景标注文件
        scene_annotation_files = []
        annotations_dir = repo_path.parent / "scene_annotations"
        
        if annotations_dir.exists():
            # 查找JSONL文件
            jsonl_files = list(annotations_dir.glob(f"{dataset_uuid}_scene_annotations.jsonl"))
            if jsonl_files:
                scene_annotation_files.extend(jsonl_files)
            
            # 查找JSON文件
            json_files = list(annotations_dir.glob("*.json"))
            scene_annotation_files.extend(json_files)
        
        if not scene_annotation_files:
            self.logger.warning(f"No scene annotation files found for dataset {dataset_uuid}")
            return

        # 读取场景标注数据
        scene_annotations_list = []
        scene_annotations_data = []
        
        for file_path in scene_annotation_files:
            try:
                if file_path.suffix == '.jsonl':
                    with open(file_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.strip():
                                annotation = json.loads(line)
                                scene_annotations_data.append(annotation)
                                if 'scene' in annotation:
                                    scene_annotations_list.append(annotation['scene'])
                elif file_path.suffix == '.json':
                    with open(file_path, 'r', encoding='utf-8') as f:
                        annotation = json.load(f)
                        scene_annotations_data.append(annotation)
                        if 'scene_description' in annotation:
                            scene_annotations_list.append(annotation['scene_description'])
            except Exception as e:
                self.logger.error(f"Error reading scene annotation file {file_path}: {e}")

        if not scene_annotations_data:
            self.logger.warning(f"No valid scene annotation data found for dataset {dataset_uuid}")
            return

        # 获取episode帧数信息
        with self.db.with_session() as session:
            ep_items = (
                session.query(VideoHashDB).filter(VideoHashDB.dataset_uuid == dataset_uuid).all()
            )
            episode_frame_nums = {}
            for ep_item in ep_items:
                episode_frame_nums[ep_item.ep_idx] = ep_item.frame_num

        try:
            # 转换场景标注数据为帧数组
            annotation_datas = scene_annotations_to_frame_array(
                scene_annotations=scene_annotations_data,
                max_objects_num=10,
                episode_frame_nums=episode_frame_nums
            )

            # 创建处理器并处理数据
            processor = SceneAnnotationDataPostProcessor(
                convert_path=repo_path,
                scene_annotations=scene_annotations_list,
                episode_scene_indices=annotation_datas,
            )
            processor.process()
            
            # 更新数据库状态
            with self.db.with_session() as session:
                session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).update(
                    {
                        DatasetDB.video_embed_subtask_annotation_status: TaskStatus.COMPLETED,
                    }
                )
                session.commit()
                
        except Exception:
            self.logger.error(
                f"Error when embedding scene annotation for dataset {dataset_uuid}: {traceback.format_exc()}"
            )
            with self.db.with_session() as session:
                session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).update(
                    {
                        DatasetDB.video_embed_subtask_annotation_status: TaskStatus.FAILED,
                        DatasetDB.video_embed_subtask_annotation_err_msg: traceback.format_exc(),
                    }
                )
                session.commit()

    def embed_scene_annotation(self) -> None:
        """嵌入场景标注数据"""
        self.sync_dataset_scene_annotation_embedding_status()
        
        with self.db.with_session() as session:
            try:
                task_num = (
                    session.query(DatasetDB)
                    .filter(
                        and_(
                            DatasetDB.scene_annotation_status == TaskStatus.COMPLETED,
                            DatasetDB.video_embed_subtask_annotation_status == TaskStatus.PENDING,
                        )
                    )
                    .count()
                )
            except Exception:
                # 如果字段不存在，设置为0
                task_num = 0
                
        pbar = tqdm.tqdm(
            total=task_num, desc="Embed scene annotation for datasets", unit="dataset"
        )
        
        while True:
            dataset_uuid, repo_path = self.gen_one_dataset_scene_annotation_embedding_task()
            if dataset_uuid is None:
                break
            self._embed_scene_annotation(dataset_uuid=dataset_uuid, repo_path=repo_path)
            pbar.update(1)

        pbar.close()