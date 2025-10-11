"""
LeRobot格式转换器 - H5+JPG格式
处理 aligned_joints.h5 (state/action) + camera/{frame_idx}/*.jpg (images) 的数据集
专门用于 Ruantong A2D 人形机器人数据集
"""

import json
import logging
from pathlib import Path

import h5py
import numpy as np
from PIL import Image

from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import (
    LerobotFormatConverter,
)


class LerobotFormatConverterH5Jpg(LerobotFormatConverter):
    """H5+JPG格式转换器
    
    数据结构：
    - episode_dir/aligned_joints.h5: 包含 state 和 action 数据
    - episode_dir/camera/{frame_idx}/{cam_name}.jpg: 图像文件
    - episode_dir/meta_info.json: 元数据信息
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
        self._h5_file_cache = {}  # 缓存打开的 H5 文件
        self._meta_info_cache = {}  # 缓存元数据

    def __del__(self) -> None:
        """关闭所有缓存的 H5 文件"""
        for h5_file in self._h5_file_cache.values():
            if h5_file is not None:
                h5_file.close()
        self._h5_file_cache.clear()

    def _prevalidate_files(self) -> None:
        """验证数据集文件完整性"""
        for task_path in self.path_task_dict.keys():
            # 查找所有 episode 目录（包含 aligned_joints.h5 的目录）
            episodes = [
                item for item in task_path.glob("*")
                if item.is_dir() and (item / "aligned_joints.h5").exists()
            ]
            
            if not episodes:
                raise FileNotFoundError(
                    f"No episode directories with aligned_joints.h5 found in {task_path}"
                )
            
            for ep_dir in episodes:
                h5_file = ep_dir / "aligned_joints.h5"
                camera_dir = ep_dir / "camera"
                meta_file = ep_dir / "meta_info.json"
                
                if not h5_file.exists():
                    raise FileNotFoundError(f"No aligned_joints.h5 in {ep_dir}")
                
                if not camera_dir.exists():
                    raise FileNotFoundError(f"No camera directory in {ep_dir}")
                
                if not meta_file.exists():
                    if self.logger:
                        self.logger.warning(f"No meta_info.json in {ep_dir}")

    def _get_task_episodes_num(self, task_path: Path) -> int:
        """获取任务的 episode 数量"""
        episodes = [
            item for item in task_path.glob("*")
            if item.is_dir() and (item / "aligned_joints.h5").exists()
        ]
        return len(episodes)

    def _get_all_episode_dirs(self, task_path: Path) -> list[Path]:
        """获取所有 episode 目录"""
        episodes = [
            item for item in task_path.glob("*")
            if item.is_dir() and (item / "aligned_joints.h5").exists()
        ]
        return sorted(episodes)

    def _get_episode_dir(self, task_path: Path, ep_idx: int) -> Path:
        """获取指定的 episode 目录"""
        episodes = self._get_all_episode_dirs(task_path)
        if ep_idx >= len(episodes):
            raise IndexError(
                f"Episode index {ep_idx} out of range for task_path={task_path}. "
                f"Found {len(episodes)} episodes."
            )
        return episodes[ep_idx]

    def _get_h5_file(self, task_path: Path, ep_idx: int) -> h5py.File:
        """获取 H5 文件（带缓存）"""
        ep_dir = self._get_episode_dir(task_path, ep_idx)
        h5_path = ep_dir / "aligned_joints.h5"
        
        cache_key = str(h5_path)
        if cache_key not in self._h5_file_cache:
            self._h5_file_cache[cache_key] = h5py.File(h5_path, 'r')
        
        return self._h5_file_cache[cache_key]

    def _get_meta_info(self, task_path: Path, ep_idx: int) -> dict:
        """获取元数据（带缓存）"""
        ep_dir = self._get_episode_dir(task_path, ep_idx)
        meta_file = ep_dir / "meta_info.json"
        
        cache_key = str(meta_file)
        if cache_key not in self._meta_info_cache:
            if meta_file.exists():
                with open(meta_file) as f:
                    self._meta_info_cache[cache_key] = json.load(f)
            else:
                self._meta_info_cache[cache_key] = {}
        
        return self._meta_info_cache[cache_key]

    def _get_episode_frames_num(self, task_path: Path, ep_idx: int) -> int:
        """获取 episode 的帧数
        
        注意：
        1. H5 文件中可能有 490 帧，但 camera 目录可能只有部分帧
        2. 帧编号可能不连续（例如：0, 1, 10, 11, 12...）
        需要使用实际存在的帧列表
        """
        h5_file = self._get_h5_file(task_path, ep_idx)
        
        # 从 timestamp 或任一 dataset 获取帧数
        if 'timestamp' in h5_file:
            h5_frames = len(h5_file['timestamp'])
        elif 'state/joint/position' in h5_file:
            h5_frames = h5_file['state/joint/position'].shape[0]
        else:
            raise ValueError("Cannot determine frame count from H5 file")
        
        # 获取 camera 目录中实际存在的帧
        ep_dir = self._get_episode_dir(task_path, ep_idx)
        camera_dir = ep_dir / "camera"
        frame_dirs = [d for d in camera_dir.glob("[0-9]*") if d.is_dir()]
        
        if not frame_dirs:
            raise FileNotFoundError(f"No frame directories found in {camera_dir}")
        
        # 获取帧编号列表并排序
        frame_indices = sorted([int(d.name) for d in frame_dirs])
        
        # 保存帧索引映射供后续使用
        cache_key = str(ep_dir)
        if not hasattr(self, '_frame_indices_cache'):
            self._frame_indices_cache = {}
        self._frame_indices_cache[cache_key] = frame_indices
        
        # 返回实际可用的帧数（取 H5 帧数和最大帧索引+1 的最小值）
        max_frame_idx = frame_indices[-1]
        return min(h5_frames, max_frame_idx + 1, len(frame_indices))

    def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int) -> dict:
        """准备 episode 的图像缓冲区
        
        返回包含 episode_dir 路径的字典，实际图像按需加载
        """
        ep_dir = self._get_episode_dir(task_path, ep_idx)
        return {"episode_dir": ep_dir}

    def _prepare_episode_states_buffer(self, task_path: Path, ep_idx: int) -> h5py.File:
        """准备 episode 的状态缓冲区"""
        return self._get_h5_file(task_path, ep_idx)

    def _prepare_episode_actions_buffer(self, task_path: Path, ep_idx: int) -> h5py.File:
        """准备 episode 的动作缓冲区"""
        return self._get_h5_file(task_path, ep_idx)

    def _get_frame_image(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        images_buffer: dict | None = None,
    ) -> np.ndarray:
        """获取指定帧的图像
        
        注意：帧编号可能不连续，需要使用映射表
        """
        if images_buffer is None:
            images_buffer = self._prepare_episode_images_buffer(task_path, ep_idx)
        
        ep_dir = images_buffer["episode_dir"]
        
        # 获取实际的帧索引（处理不连续的帧编号）
        cache_key = str(ep_dir)
        if hasattr(self, '_frame_indices_cache') and cache_key in self._frame_indices_cache:
            frame_indices = self._frame_indices_cache[cache_key]
            if frame_idx >= len(frame_indices):
                raise IndexError(
                    f"Frame index {frame_idx} out of range. "
                    f"Available frames: {len(frame_indices)}, "
                    f"task_path={task_path}, ep_idx={ep_idx}"
                )
            actual_frame_idx = frame_indices[frame_idx]
        else:
            # 如果没有缓存，直接使用 frame_idx
            actual_frame_idx = frame_idx
        
        # 从 args_dict 获取图像路径模板
        h5_path = args_dict.get("h5_path", "")
        
        # 替换 {frame_idx} 占位符为实际的帧索引
        image_path = h5_path.replace("{frame_idx}", str(actual_frame_idx))
        full_path = ep_dir / image_path
        
        if not full_path.exists():
            raise FileNotFoundError(
                f"Image file not found: {full_path} "
                f"(logical frame_idx={frame_idx}, actual_frame_idx={actual_frame_idx}) "
                f"for task_path={task_path}, ep_idx={ep_idx}"
            )
        
        # 读取图像
        img = Image.open(full_path)
        img_array = np.array(img)
        
        # 确保 RGB 格式
        if len(img_array.shape) == 2:
            # Grayscale image, add channel dimension
            img_array = np.expand_dims(img_array, axis=-1)
        elif img_array.shape[2] == 4:
            # RGBA image, convert to RGB
            img_array = img_array[:, :, :3]
        
        return img_array

    def _get_frame_sub_states(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        sub_states_buffer: h5py.File | None = None,
    ) -> np.ndarray:
        """获取指定帧的子状态数据"""
        if sub_states_buffer is None:
            sub_states_buffer = self._prepare_episode_states_buffer(task_path, ep_idx)
        
        h5_path = args_dict["h5_path"]
        from_idx = args_dict["range_from"]
        to_idx = args_dict["range_to"]
        
        # 检查路径是否存在
        if h5_path not in sub_states_buffer:
            available_paths = list(sub_states_buffer.keys())
            raise KeyError(
                f"State h5_path '{h5_path}' not found in episode {ep_idx} "
                f"at task_path={task_path}. Available paths: {available_paths}"
            )
        
        dataset = sub_states_buffer[h5_path]
        
        # 检查是否需要处理额外的数组索引（例如 end/position 是 (N, 2, 3)）
        array_index = args_dict.get("array_index")
        
        if array_index is not None:
            # 有额外的维度，需要先索引
            if frame_idx >= dataset.shape[0]:
                raise IndexError(
                    f"State frame index {frame_idx} out of range for h5_path '{h5_path}' "
                    f"in episode {ep_idx} at task_path={task_path}. "
                    f"Dataset has {dataset.shape[0]} frames."
                )
            return dataset[frame_idx, array_index, from_idx:to_idx]
        
        # 标准的 2D 数组
        if frame_idx >= dataset.shape[0]:
            raise IndexError(
                f"State frame index {frame_idx} out of range for h5_path '{h5_path}' "
                f"in episode {ep_idx} at task_path={task_path}. "
                f"Dataset has {dataset.shape[0]} frames."
            )
        return dataset[frame_idx, from_idx:to_idx]

    def _get_frame_sub_actions(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        sub_actions_buffer: h5py.File | None = None,
    ) -> np.ndarray:
        """获取指定帧的子动作数据"""
        if sub_actions_buffer is None:
            sub_actions_buffer = self._prepare_episode_actions_buffer(task_path, ep_idx)
        
        h5_path = args_dict["h5_path"]
        from_idx = args_dict["range_from"]
        to_idx = args_dict["range_to"]
        
        # 检查路径是否存在
        if h5_path not in sub_actions_buffer:
            available_paths = list(sub_actions_buffer.keys())
            raise KeyError(
                f"Action h5_path '{h5_path}' not found in episode {ep_idx} "
                f"at task_path={task_path}. Available paths: {available_paths}"
            )
        
        dataset = sub_actions_buffer[h5_path]
        
        # 检查是否需要处理额外的数组索引
        array_index = args_dict.get("array_index")
        
        if array_index is not None:
            if frame_idx >= dataset.shape[0]:
                raise IndexError(
                    f"Action frame index {frame_idx} out of range for h5_path '{h5_path}' "
                    f"in episode {ep_idx} at task_path={task_path}. "
                    f"Dataset has {dataset.shape[0]} frames."
                )
            return dataset[frame_idx, array_index, from_idx:to_idx]
        
        if frame_idx >= dataset.shape[0]:
            raise IndexError(
                f"Action frame index {frame_idx} out of range for h5_path '{h5_path}' "
                f"in episode {ep_idx} at task_path={task_path}. "
                f"Dataset has {dataset.shape[0]} frames."
            )
        return dataset[frame_idx, from_idx:to_idx]
