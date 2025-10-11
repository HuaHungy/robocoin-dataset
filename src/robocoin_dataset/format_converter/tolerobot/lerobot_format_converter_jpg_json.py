"""
LeRobot格式转换器 - JPG+JSON格式
处理多传感器文件夹结构的数据集（alohaold, pika, mayi）
"""

import json
import logging
from pathlib import Path

import numpy as np
from PIL import Image

from robocoin_dataset.format_converter.tolerobot.constant import (
    ARGS_KEY,
    CAM_NAME_KEY,
    FEATURES_KEY,
    IMAGE_KEY,
    OBSERVATION_KEY,
)
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import (
    LerobotFormatConverter,
)


class LerobotFormatConverterJpgJson(LerobotFormatConverter):
    """JPG+JSON格式转换器 - 用于多传感器文件夹结构的数据集"""
    
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
            episodes = list(task_path.glob("episode*"))
            episodes = [ep for ep in episodes if ep.is_dir()]
            
            if not episodes:
                raise FileNotFoundError(f"No episode directories found in {task_path}")
            
            for ep_dir in episodes:
                # 检查是否有嵌套的episode目录
                nested_ep = ep_dir / ep_dir.name
                if nested_ep.exists() and nested_ep.is_dir() and (nested_ep / "camera").exists():
                    ep_dir = nested_ep
                
                # 检查相机文件夹
                camera_dir = ep_dir / "camera" / "color"
                if not camera_dir.exists():
                    raise FileNotFoundError(f"No camera/color directory in {ep_dir}")

    def _get_episode_dir(self, task_path: Path, ep_idx: int) -> Path:
        """获取episode目录"""
        episodes = sorted([ep for ep in task_path.glob("episode*") if ep.is_dir()])
        if ep_idx >= len(episodes):
            raise IndexError(f"Episode index {ep_idx} out of range")
        
        ep_dir = episodes[ep_idx]
        
        # 检查是否有嵌套的episode目录（如pika数据集：episode0/episode0/...）
        nested_ep = ep_dir / ep_dir.name
        if nested_ep.exists() and nested_ep.is_dir():
            # 检查嵌套目录是否包含camera数据
            if (nested_ep / "camera").exists():
                return nested_ep
        
        return ep_dir

    def _get_camera_images(self, ep_dir: Path, camera_name: str) -> list[Path]:
        """获取指定相机的所有图像文件"""
        camera_dir = ep_dir / "camera" / "color" / camera_name
        if not camera_dir.exists():
            return []
        
        return sorted(camera_dir.glob("*.jpg")) + sorted(camera_dir.glob("*.png"))

    def _get_episode_frames_num(self, task_path: Path, ep_idx: int) -> int:
        """获取episode的帧数"""
        ep_dir = self._get_episode_dir(task_path, ep_idx)
        
        # 从第一个可用的相机获取帧数
        camera_dir = ep_dir / "camera" / "color"
        if not camera_dir.exists():
            raise FileNotFoundError(f"No camera directory in {ep_dir}")
        
        for cam_folder in camera_dir.iterdir():
            if cam_folder.is_dir():
                images = list(cam_folder.glob("*.jpg")) + list(cam_folder.glob("*.png"))
                if images:
                    return len(images)
        
        raise ValueError(f"No images found in {ep_dir}")

    def _get_task_episodes_num(self, task_path: Path) -> int:
        """获取任务的episode数量"""
        episodes = [ep for ep in task_path.glob("episode*") if ep.is_dir()]
        return len(episodes)

    def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int) -> dict[str, list[np.ndarray]]:
        """准备episode的图像缓冲区"""
        ep_dir = self._get_episode_dir(task_path, ep_idx)
        
        images = {}
        camera_dir = ep_dir / "camera" / "color"
        
        if camera_dir.exists():
            # 遍历配置中的所有相机
            image_configs = self.converter_config[FEATURES_KEY][OBSERVATION_KEY][IMAGE_KEY]
            for image_config in image_configs:
                cam_name = image_config.get(CAM_NAME_KEY)
                camera_folder = image_config.get(ARGS_KEY, {}).get('camera_folder')
                
                if not camera_folder:
                    # 如果没有指定camera_folder，尝试使用cam_name的前缀匹配
                    for cam_folder in camera_dir.iterdir():
                        if cam_folder.is_dir() and cam_name and (cam_name in cam_folder.name or cam_folder.name in cam_name):
                            camera_folder = cam_folder.name
                            break
                
                if camera_folder:
                    cam_folder_path = camera_dir / camera_folder
                    if cam_folder_path.exists():
                        image_files = sorted(cam_folder_path.glob("*.jpg")) + sorted(cam_folder_path.glob("*.png"))
                        
                        frames = []
                        for img_file in image_files:
                            img = Image.open(img_file)
                            img_rgb = np.array(img.convert("RGB"))
                            frames.append(img_rgb)
                        
                        if frames:
                            images[cam_name] = frames
        
        return images

    def _load_joint_state_data(self, ep_dir: Path, joint_type: str) -> list[dict]:
        """加载关节状态数据"""
        joint_dir = ep_dir / "arm" / "jointState" / joint_type
        if not joint_dir.exists():
            return []
        
        json_files = sorted(joint_dir.glob("*.json"))
        data = []
        for json_file in json_files:
            with open(json_file) as f:
                data.append(json.load(f))
        
        return data

    def _load_gripper_data(self, ep_dir: Path, gripper_side: str) -> list[dict]:
        """加载夹爪数据"""
        gripper_dir = ep_dir / "gripper" / "encoder" / gripper_side
        if not gripper_dir.exists():
            return []
        
        json_files = sorted(gripper_dir.glob("*.json"))
        data = []
        for json_file in json_files:
            with open(json_file) as f:
                data.append(json.load(f))
        
        return data

    def _prepare_episode_states_buffer(self, task_path: Path, ep_idx: int) -> dict:
        """准备episode的状态缓冲区"""
        ep_dir = self._get_episode_dir(task_path, ep_idx)
        
        # 加载各种关节数据
        return {
            'puppet_left': self._load_joint_state_data(ep_dir, 'puppetLeft'),
            'puppet_right': self._load_joint_state_data(ep_dir, 'puppetRight'),
            'master_left': self._load_joint_state_data(ep_dir, 'masterLeft'),
            'master_right': self._load_joint_state_data(ep_dir, 'masterRight'),
            'gripper_left': self._load_gripper_data(ep_dir, 'pika_l'),
            'gripper_right': self._load_gripper_data(ep_dir, 'pika_r'),
        }
        

    def _prepare_episode_actions_buffer(self, task_path: Path, ep_idx: int) -> dict:
        """准备episode的动作缓冲区"""
        # 对于这类数据集，action通常与observation相同
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
        
        # 尝试匹配相机名称
        matched_cam = None
        for key in images_buffer.keys():
            if cam_name in key or key in cam_name:
                matched_cam = key
                break
        
        if matched_cam is None:
            raise KeyError(f"Camera {cam_name} not found in episode {ep_idx}. Available: {list(images_buffer.keys())}")
        
        if frame_idx >= len(images_buffer[matched_cam]):
            raise IndexError(f"Frame index {frame_idx} out of range for camera {matched_cam}")
        
        return images_buffer[matched_cam][frame_idx]

    def _get_frame_sub_states(
        self, 
        task_path: Path, 
        ep_idx: int, 
        frame_idx: int, 
        args_dict: dict,
        sub_states_buffer: dict | None = None
    ) -> np.ndarray:
        """获取指定帧的子状态"""
        if sub_states_buffer is None:
            sub_states_buffer = self._prepare_episode_states_buffer(task_path, ep_idx)
        
        joint_type = args_dict.get('joint_type', 'puppet_left')
        field_name = args_dict.get('field_name', 'position')
        
        if joint_type not in sub_states_buffer:
            # 返回零值
            range_from = args_dict.get('range_from', 0)
            range_to = args_dict.get('range_to', 7)
            return np.zeros(range_to - range_from, dtype=np.float32)
        
        data = sub_states_buffer[joint_type]
        if frame_idx >= len(data):
            range_from = args_dict.get('range_from', 0)
            range_to = args_dict.get('range_to', 7)
            return np.zeros(range_to - range_from, dtype=np.float32)
        
        frame_data = data[frame_idx]
        if field_name in frame_data:
            values = frame_data[field_name]
            if isinstance(values, list):
                range_from = args_dict.get('range_from', 0)
                range_to = args_dict.get('range_to', len(values))
                return np.array(values[range_from:range_to], dtype=np.float32)
            return np.array([values], dtype=np.float32)
        
        # 默认返回零值
        range_from = args_dict.get('range_from', 0)
        range_to = args_dict.get('range_to', 7)
        return np.zeros(range_to - range_from, dtype=np.float32)

    def _get_frame_sub_actions(
        self, 
        task_path: Path, 
        ep_idx: int, 
        frame_idx: int, 
        args_dict: dict,
        sub_actions_buffer: dict | None = None
    ) -> np.ndarray:
        """获取指定帧的子动作"""
        # 使用master数据作为action
        if args_dict.get('joint_type', '').startswith('puppet'):
            args_dict = args_dict.copy()
            args_dict['joint_type'] = args_dict['joint_type'].replace('puppet', 'master')
        
        return self._get_frame_sub_states(task_path, ep_idx, frame_idx, args_dict, sub_actions_buffer)
