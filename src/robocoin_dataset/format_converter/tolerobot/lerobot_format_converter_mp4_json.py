"""
LeRobot格式转换器 - MP4+JSON格式
处理MP4视频文件配合JSON数据文件的数据集
"""

import json
import logging
from pathlib import Path

import cv2
import numpy as np

from robocoin_dataset.format_converter.tolerobot.constant import (
    CAM_NAME_KEY,
)
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import (
    LerobotFormatConverter,
)


class LerobotFormatConverterMp4Json(LerobotFormatConverter):
    """MP4+JSON格式转换器 - 用于yinhe等数据集"""
    
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
        self._json_data_cache = {}  # 缓存JSON数据

    def _prevalidate_files(self) -> None:
        """验证数据集文件完整性"""
        for task_path in self.path_task_dict.keys():
            episodes = list(task_path.glob("*"))
            episodes = [ep for ep in episodes if ep.is_dir()]
            
            if not episodes:
                raise FileNotFoundError(f"No episode directories found in {task_path}")
            
            for ep_dir in episodes:
                json_files = list(ep_dir.glob("data.json"))
                if not json_files:
                    raise FileNotFoundError(f"No data.json file found in {ep_dir}")
                
                # 检查是否有对应的MP4文件
                mp4_files = list(ep_dir.glob("*.mp4"))
                if not mp4_files:
                    raise FileNotFoundError(f"No MP4 files found in {ep_dir}")

    def _load_json_data(self, task_path: Path, ep_idx: int) -> dict:
        """加载JSON数据（带缓存）"""
        episodes = sorted([ep for ep in task_path.glob("*") if ep.is_dir()])
        if ep_idx >= len(episodes):
            raise IndexError(f"Episode index {ep_idx} out of range")
        
        ep_dir = episodes[ep_idx]
        json_file = ep_dir / "data.json"
        
        cache_key = str(json_file)
        if cache_key not in self._json_data_cache:
            with open(json_file) as f:
                data = json.load(f)
            self._json_data_cache[cache_key] = data
        
        return self._json_data_cache[cache_key]

    def _get_episode_frames_num(self, task_path: Path, ep_idx: int) -> int:
        """获取episode的帧数"""
        json_data = self._load_json_data(task_path, ep_idx)
        if 'data' in json_data:
            # 从第一个相机获取帧数
            for key, value in json_data['data'].items():
                if 'camera' in key and isinstance(value, list):
                    return len(value)
        
        raise ValueError("Cannot determine frame count from JSON data")

    def _get_task_episodes_num(self, task_path: Path) -> int:
        """获取任务的episode数量"""
        episodes = [ep for ep in task_path.glob("*") if ep.is_dir()]
        return len(episodes)

    def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int) -> dict[str, list[np.ndarray]]:
        """准备episode的图像缓冲区"""
        episodes = sorted([ep for ep in task_path.glob("*") if ep.is_dir()])
        ep_dir = episodes[ep_idx]
        
        # 获取所有MP4文件
        mp4_files = sorted(ep_dir.glob("*.mp4"))
        
        images = {}
        for mp4_file in mp4_files:
            # 从文件名推断相机名称
            cam_name = self._infer_camera_name(mp4_file.stem)
            if cam_name:
                cap = cv2.VideoCapture(str(mp4_file))
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
        
        return images

    def _infer_camera_name(self, filename: str) -> str | None:
        """从文件名推断相机名称"""
        mappings = {
            'front_head': 'camera_front_head_rgb',
            'left_wrist': 'camera_left_wrist',
            'right_wrist': 'camera_right_wrist',
            'camera_front_head_rgb': 'camera_front_head_rgb',
            'camera_left_wrist': 'camera_left_wrist',
            'camera_right_wrist': 'camera_right_wrist',
        }
        
        filename_lower = filename.lower()
        for key, value in mappings.items():
            if key in filename_lower:
                return value
        
        return None

    def _prepare_episode_states_buffer(self, task_path: Path, ep_idx: int) -> list[dict]:
        """准备episode的状态缓冲区"""
        json_data = self._load_json_data(task_path, ep_idx)
        
        if 'data' not in json_data:
            raise ValueError("No 'data' key in JSON file")
        
        return json_data['data']

    def _prepare_episode_actions_buffer(self, task_path: Path, ep_idx: int) -> list[dict]:
        """准备episode的动作缓冲区"""
        # 对于yinhe数据集，action和state使用相同的数据
        return self._prepare_episode_states_buffer(task_path, ep_idx)

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
            available_cameras = list(images_buffer.keys())
            raise KeyError(
                f"Camera '{cam_name}' not found in episode {ep_idx} at task_path={task_path}. "
                f"Available cameras: {available_cameras}"
            )
        
        if frame_idx >= len(images_buffer[cam_name]):
            raise IndexError(
                f"Frame index {frame_idx} out of range for camera '{cam_name}' "
                f"in episode {ep_idx} at task_path={task_path}. "
                f"Camera has {len(images_buffer[cam_name])} frames."
            )
        
        return images_buffer[cam_name][frame_idx]

    def _get_frame_sub_states(
        self, 
        task_path: Path, 
        ep_idx: int, 
        frame_idx: int, 
        args_dict: dict,
        sub_states_buffer: list[dict] | None = None
    ) -> np.ndarray:
        """获取指定帧的子状态"""
        if sub_states_buffer is None:
            sub_states_buffer = self._prepare_episode_states_buffer(task_path, ep_idx)
        
        json_path = args_dict.get('json_path', '')
        
        # 从JSON数据中提取指定路径的值
        frame_data = sub_states_buffer
        if isinstance(frame_data, dict):
            # 处理嵌套字典
            for key in json_path.split('/'):
                if key:
                    frame_data = frame_data.get(key, {})
        
        if isinstance(frame_data, list) and frame_idx < len(frame_data):
            value = frame_data[frame_idx]
            if isinstance(value, (list, tuple)):
                return np.array(value, dtype=np.float32)
            return np.array([value], dtype=np.float32)
        
        # 如果找不到数据，返回0
        range_from = args_dict.get('range_from', 0)
        range_to = args_dict.get('range_to', 1)
        return np.zeros(range_to - range_from, dtype=np.float32)

    def _get_frame_sub_actions(
        self, 
        task_path: Path, 
        ep_idx: int, 
        frame_idx: int, 
        args_dict: dict,
        sub_actions_buffer: list[dict] | None = None
    ) -> np.ndarray:
        """获取指定帧的子动作"""
        # 使用与状态相同的逻辑
        return self._get_frame_sub_states(task_path, ep_idx, frame_idx, args_dict, sub_actions_buffer)
