"""
LeRobot格式转换器 - Annotation+H5+MP4格式
通过annotation JSON文件检索H5数据文件和MP4视频文件的数据集
用于robobrain等使用标注文件管理数据的数据集
"""

import logging
from pathlib import Path
from typing import Any
import numpy as np
import h5py
import cv2
import json
import yaml

from robocoin_dataset.format_converter.tolerobot.constant import (
    FEATURES_KEY, OBSERVATION_KEY, IMAGE_KEY, STATE_KEY, SUB_STATE_KEY,
    ACTION_KEY, SUB_ACTION_KEY, ARGS_KEY, CAM_NAME_KEY,
)
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import LerobotFormatConverter


class LerobotFormatConverterAnnotationH5Mp4(LerobotFormatConverter):
    """
    处理通过annotation文件检索H5+MP4数据的转换器
    
    数据结构：
    - annotation/train.json: 标注文件，包含每个episode的元数据和文件路径
    - videos/train/{ep_id}/{ep_id}.hdf5: H5数据文件（qpos/action）
    - videos/train/{ep_id}/{ep_id}_cam_*.mp4: MP4视频文件
    """
    
    def __init__(
        self,
        dataset_path: str,
        output_path: str,
        converter_config: dict,
        repo_id: str,
        device_model: str,
        logger: logging.Logger | None = None,
        video_backend: str = "pyav",
        image_writer_processes: int = 4,
        image_writer_threads: int = 4,
    ) -> None:
        # 在调用super之前设置dataset_path和converter_config，以便_load_annotation可以使用它
        self.dataset_path = dataset_path
        self.converter_config = converter_config
        self._annotation_data = None
        self._video_readers = {}  # 缓存视频读取器
        
        super().__init__(
            dataset_path=dataset_path,
            output_path=output_path,
            converter_config=converter_config,
            repo_id=repo_id,
            device_model=device_model,
            logger=logger,
            video_backend=video_backend,
            image_writer_processes=image_writer_processes,
            image_writer_threads=image_writer_threads,
        )

    def _load_annotation(self) -> list[dict]:
        """加载annotation文件"""
        if self._annotation_data is None:
            annotation_file = Path(self.dataset_path) / "annotation" / "train.json"
            if not annotation_file.exists():
                raise FileNotFoundError(f"Annotation file not found: {annotation_file}")
            
            with open(annotation_file, 'r') as f:
                self._annotation_data = json.load(f)
        
        return self._annotation_data

    def _gen_task_paths_dict(self) -> dict[Path, str]:
        """生成任务路径字典"""
        annotation_data = self._load_annotation()
        
        # robobrain将所有episodes作为一个大任务处理
        task_path = Path(self.dataset_path) / "videos" / "train"
        
        # 尝试从local_task_info.yaml获取任务名称
        local_task_info = Path(self.dataset_path) / "local_task_info.yaml"
        if local_task_info.exists():
            with open(local_task_info, 'r') as f:
                task_info = yaml.safe_load(f)
                tasks = task_info.get('tasks', {})
                if tasks:
                    task_name = list(tasks.keys())[0]
                else:
                    task_name = "default_task"
        else:
            task_name = "default_task"
        
        return {task_path: task_name}

    def _get_episode_entry(self, task_path: Path, ep_idx: int) -> dict:
        """获取指定episode的annotation条目"""
        annotation_data = self._load_annotation()
        
        # robobrain将所有episodes作为一个大任务，直接按索引访问
        if ep_idx >= len(annotation_data):
            raise IndexError(f"Episode index {ep_idx} out of range (total: {len(annotation_data)})")
        
        return annotation_data[ep_idx]

    def _get_h5_file_path(self, entry: dict) -> Path:
        """从annotation条目获取H5文件路径"""
        state_path = entry['data'].get('state_path')
        if not state_path:
            raise ValueError("No state_path in annotation entry")
        
        return Path(self.dataset_path) / state_path

    def _get_video_file_path(self, entry: dict, cam_name: str) -> Path:
        """从annotation条目获取视频文件路径
        
        cam_name可能带有_rgb后缀（如cam_high_rgb），需要尝试多种映射
        """
        video_paths = entry['data'].get('video_paths', {})
        
        # 尝试直接匹配
        if cam_name in video_paths:
            return Path(self.dataset_path) / video_paths[cam_name]
        
        # 尝试去掉_rgb后缀
        cam_name_without_rgb = cam_name.replace('_rgb', '')
        if cam_name_without_rgb in video_paths:
            return Path(self.dataset_path) / video_paths[cam_name_without_rgb]
        
        raise ValueError(f"Camera {cam_name} (or {cam_name_without_rgb}) not found in annotation video_paths: {list(video_paths.keys())}")

    def _prevalidate_files(self) -> None:
        """验证数据集文件完整性"""
        # 加载annotation文件
        annotation_data = self._load_annotation()
        
        if not annotation_data:
            raise ValueError("Annotation data is empty")
        
        # 检查至少有一个episode的数据
        sample = annotation_data[0]
        if 'data' not in sample:
            raise ValueError("Invalid annotation format: missing 'data' field")
        
        # 注意：由于videos文件夹可能为空（数据太大），我们不验证实际文件存在性
        self.logger.info(f"Loaded {len(annotation_data)} episodes from annotation file")

    def _get_episode_frames_num(self, task_path: Path, ep_idx: int) -> int:
        """获取episode的帧数"""
        entry = self._get_episode_entry(task_path, ep_idx)
        
        # 从annotation中直接获取帧数
        if 'frame' in entry:
            return entry['frame']
        
        # 如果annotation中没有帧数，尝试从H5文件读取
        try:
            h5_path = self._get_h5_file_path(entry)
            if h5_path.exists():
                with h5py.File(h5_path, 'r') as f:
                    if 'qpos' in f:
                        return f['qpos'].shape[0]
                    if 'action' in f:
                        return f['action'].shape[0]
        except Exception as e:
            self.logger.warning(f"Cannot read H5 file for episode {ep_idx}: {e}")
        
        raise ValueError(f"Cannot determine frame count for episode {ep_idx}")

    def _get_task_episodes_num(self, task_path: Path) -> int:
        """获取任务的episode数量"""
        annotation_data = self._load_annotation()
        
        # robobrain将所有episodes作为一个大任务
        return len(annotation_data)

    def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int) -> dict[str, list[np.ndarray]]:
        """准备episode的图像缓冲区"""
        entry = self._get_episode_entry(task_path, ep_idx)
        
        images = {}
        image_configs = self.converter_config[FEATURES_KEY][OBSERVATION_KEY][IMAGE_KEY]
        
        for image_config in image_configs:
            cam_name = image_config.get(CAM_NAME_KEY)
            
            try:
                video_path = self._get_video_file_path(entry, cam_name)
                
                # 如果文件不存在，跳过（因为videos文件夹可能为空）
                if not video_path.exists():
                    self.logger.warning(f"Video file not found: {video_path}, skipping camera {cam_name}")
                    continue
                
                cap = cv2.VideoCapture(str(video_path))
                if not cap.isOpened():
                    raise OSError(f"Cannot open video file: {video_path}")
                
                frames = []
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    # OpenCV读取的是BGR，转换为RGB
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frames.append(frame_rgb)
                cap.release()
                
                images[cam_name] = frames
            except Exception as e:
                self.logger.warning(f"Error loading camera {cam_name}: {e}")
        
        return images

    def _infer_camera_name(self, filename: str) -> str | None:
        """从文件名推断相机名称"""
        # 定义常见的相机名称映射
        mappings = {
            'high': 'cam_high',
            'left_wrist': 'cam_left_wrist',
            'right_wrist': 'cam_right_wrist',
            'cam_high': 'cam_high',
            'cam_left_wrist': 'cam_left_wrist',
            'cam_right_wrist': 'cam_right_wrist',
        }
        
        filename_lower = filename.lower()
        for key, value in mappings.items():
            if key in filename_lower:
                return value
        
        return None

    def _prepare_episode_states_buffer(self, task_path: Path, ep_idx: int) -> np.ndarray:
        """准备episode的状态缓冲区"""
        entry = self._get_episode_entry(task_path, ep_idx)
        h5_path = self._get_h5_file_path(entry)
        
        if not h5_path.exists():
            self.logger.warning(f"H5 file not found: {h5_path}")
            # 返回一个空数组，形状根据配置推断
            frame_num = entry.get('frame', 0)
            state_dim = self._get_state_dimension()
            return np.zeros((frame_num, state_dim), dtype=np.float32)
        
        with h5py.File(h5_path, 'r') as f:
            if 'qpos' in f:
                return np.array(f['qpos'])
            raise ValueError(f"No qpos data in {h5_path}")

    def _prepare_episode_actions_buffer(self, task_path: Path, ep_idx: int) -> np.ndarray:
        """准备episode的动作缓冲区"""
        entry = self._get_episode_entry(task_path, ep_idx)
        h5_path = self._get_h5_file_path(entry)
        
        if not h5_path.exists():
            self.logger.warning(f"H5 file not found: {h5_path}")
            # 返回一个空数组
            frame_num = entry.get('frame', 0)
            action_dim = self._get_action_dimension()
            return np.zeros((frame_num, action_dim), dtype=np.float32)
        
        with h5py.File(h5_path, 'r') as f:
            if 'action' in f:
                return np.array(f['action'])
            raise ValueError(f"No action data in {h5_path}")

    def _get_state_dimension(self) -> int:
        """从配置中获取状态维度"""
        state_configs = self.converter_config[FEATURES_KEY][OBSERVATION_KEY].get(STATE_KEY, {}).get(SUB_STATE_KEY, [])
        total_dim = 0
        for state_config in state_configs:
            from_idx = state_config.get(ARGS_KEY, {}).get('range_from', 0)
            to_idx = state_config.get(ARGS_KEY, {}).get('range_to', 0)
            total_dim = max(total_dim, to_idx)
        return total_dim

    def _get_action_dimension(self) -> int:
        """从配置中获取动作维度"""
        action_configs = self.converter_config[FEATURES_KEY].get(ACTION_KEY, {}).get(SUB_ACTION_KEY, [])
        total_dim = 0
        for action_config in action_configs:
            from_idx = action_config.get(ARGS_KEY, {}).get('range_from', 0)
            to_idx = action_config.get(ARGS_KEY, {}).get('range_to', 0)
            total_dim = max(total_dim, to_idx)
        return total_dim

    def _get_frame_image(
        self, 
        task_path: Path, 
        ep_idx: int, 
        frame_idx: int, 
        args_dict: dict, 
        images_buffer: dict[str, list[np.ndarray]] | None = None
    ) -> np.ndarray:
        """获取指定帧的图像"""
        if images_buffer is None:
            images_buffer = self._prepare_episode_images_buffer(task_path, ep_idx)
        
        cam_name = args_dict.get(CAM_NAME_KEY)
        if cam_name not in images_buffer:
            raise KeyError(f"Camera {cam_name} not found in episode {ep_idx}")
        
        if frame_idx >= len(images_buffer[cam_name]):
            raise IndexError(f"Frame index {frame_idx} out of range for camera {cam_name}")
        
        return images_buffer[cam_name][frame_idx]

    def _get_frame_sub_states(
        self, 
        task_path: Path, 
        ep_idx: int, 
        frame_idx: int, 
        args_dict: dict,
        sub_states_buffer: np.ndarray | None = None
    ) -> np.ndarray:
        """获取指定帧的子状态"""
        if sub_states_buffer is None:
            sub_states_buffer = self._prepare_episode_states_buffer(task_path, ep_idx)
        
        from_idx = args_dict.get('range_from', 0)
        to_idx = args_dict.get('range_to', sub_states_buffer.shape[1])
        
        return sub_states_buffer[frame_idx, from_idx:to_idx].astype(np.float32)

    def _get_frame_sub_actions(
        self, 
        task_path: Path, 
        ep_idx: int, 
        frame_idx: int, 
        args_dict: dict,
        sub_actions_buffer: np.ndarray | None = None
    ) -> np.ndarray:
        """获取指定帧的子动作"""
        if sub_actions_buffer is None:
            sub_actions_buffer = self._prepare_episode_actions_buffer(task_path, ep_idx)
        
        from_idx = args_dict.get('range_from', 0)
        to_idx = args_dict.get('range_to', sub_actions_buffer.shape[1])
        
        return sub_actions_buffer[frame_idx, from_idx:to_idx].astype(np.float32)

    def __del__(self):
        """清理视频读取器"""
        for cap in self._video_readers.values():
            if cap.isOpened():
                cap.release()
