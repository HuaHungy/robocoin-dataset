"""
LeRobot格式转换器 - H5+MP4格式
处理HDF5数据文件配合MP4视频文件的数据集
"""

import logging
from pathlib import Path

import av
import cv2
import h5py
import numpy as np

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
from robocoin_dataset.format_converter.tolerobot.video_frame_validator import (
    validate_video_frame_count,
)


class LerobotFormatConverterH5Mp4(LerobotFormatConverter):
    """H5+MP4格式转换器 - 用于alohanew等数据集"""
    
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
        self._video_readers = {}  # 缓存视频读取器

    def _prevalidate_files(self) -> None:
        """验证数据集文件完整性"""
        for task_path in self.path_task_dict.keys():
            # 使用新的递归查找方法
            try:
                episodes = self._get_all_episode_dirs(task_path)
            except FileNotFoundError as e:
                raise FileNotFoundError(
                    f"❌ H5+MP4 format validation failed\n"
                    f"📁 Task path: {task_path}\n"
                    f"⚠️ {str(e)}\n"
                    f"💡 Hint: Episode directories should contain .hdf5 or .h5 files.\n"
                    f"         The converter supports nested directory structures."
                ) from e
            
            # 🆕 增加：只验证第一个episode的帧数（作为抽样检查）
            first_episode_validated = False
            
            for ep_dir in episodes:
                h5_files = list(ep_dir.glob("*.hdf5")) + list(ep_dir.glob("*.h5"))
                if not h5_files:
                    raise FileNotFoundError(f"No HDF5 file found in {ep_dir}")
                
                # 检查是否有对应的MP4文件
                mp4_files = list(ep_dir.glob("*.mp4"))
                if not mp4_files:
                    self.logger.warning(f"No MP4 files found in {ep_dir}")
                    continue
                
                # 🆕 增加：对第一个episode验证视频帧数与H5数据帧数是否匹配
                if not first_episode_validated and mp4_files:
                    h5_file = h5_files[0]
                    try:
                        # 从H5文件获取预期帧数
                        expected_frame_count = None
                        with h5py.File(h5_file, 'r') as f:
                            if 'action' in f:
                                expected_frame_count = f['action'].shape[0]
                            elif 'qpos' in f:
                                expected_frame_count = f['qpos'].shape[0]
                        
                        if expected_frame_count is not None:
                            if self.logger:
                                self.logger.info(
                                    f"🔍 Validating video frame counts for episode: {ep_dir.name}\n"
                                    f"   📊 H5 data frames: {expected_frame_count}"
                                )
                            
                            # 验证每个MP4文件的帧数
                            for mp4_file in mp4_files:
                                try:
                                    validate_video_frame_count(
                                        video_path=mp4_file,
                                        expected_frame_count=expected_frame_count,
                                        data_source="H5 file",
                                        logger=self.logger,
                                        tolerance=1  # 允许±1帧误差
                                    )
                                except ValueError as e:  # noqa: PERF203
                                    self.logger.warning(
                                        f"⚠️ 视频帧数不匹配\n"
                                        f"📂 Episode: {ep_dir.name}\n"
                                        f"📄 Video: {mp4_file.name}\n"
                                        f"{str(e)}"
                                    )
                                except RuntimeError as e:
                                    self.logger.warning(
                                        f"⚠️ 无法验证视频帧数\n"
                                        f"📄 Video: {mp4_file.name}\n"
                                        f"⚠️ 原因: {str(e)}"
                                    )
                            
                            first_episode_validated = True
                    except Exception as e:
                        if self.logger:
                            self.logger.warning(f"⚠️ H5文件帧数读取失败: {e}")

    def _get_episode_h5_file(self, task_path: Path, ep_idx: int) -> Path:
        """获取episode的HDF5文件路径"""
        episodes = self._get_all_episode_dirs(task_path)
        if ep_idx >= len(episodes):
            raise IndexError(f"Episode index {ep_idx} out of range (0-{len(episodes)-1})")
        
        ep_dir = episodes[ep_idx]
        h5_files = list(ep_dir.glob("*.hdf5")) + list(ep_dir.glob("*.h5"))
        if not h5_files:
            raise FileNotFoundError(f"No HDF5 file in {ep_dir}")
        
        return h5_files[0]

    def _get_video_reader(self, video_path: Path) -> cv2.VideoCapture:
        """获取或创建视频读取器（带缓存）"""
        video_key = str(video_path)
        if video_key not in self._video_readers:
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                raise OSError(f"Cannot open video file: {video_path}")
            self._video_readers[video_key] = cap
        return self._video_readers[video_key]

    def _get_episode_frames_num(self, task_path: Path, ep_idx: int) -> int:
        """获取episode的帧数
        
        策略：取所有数据源（H5数据 + 所有视频）的最小帧数
        这样可以避免视频帧数不足导致的索引越界错误
        """
        episodes = self._get_all_episode_dirs(task_path)
        if ep_idx >= len(episodes):
            raise IndexError(f"Episode index {ep_idx} out of range (0-{len(episodes)-1})")
        
        ep_dir = episodes[ep_idx]
        h5_file = self._get_episode_h5_file(task_path, ep_idx)
        
        frame_counts = []
        
        # 1. 获取 H5 数据帧数
        with h5py.File(h5_file, 'r') as f:
            if 'action' in f:
                h5_frames = f['action'].shape[0]
            elif 'observations/qpos' in f:
                h5_frames = f['observations/qpos'].shape[0]
            elif 'qpos' in f:
                h5_frames = f['qpos'].shape[0]
            else:
                raise ValueError(f"Cannot determine frame count from {h5_file}")
            
            frame_counts.append(('H5 data', h5_frames))
        
        # 2. 获取所有视频的帧数
        mp4_files = list(ep_dir.glob("*.mp4"))
        for mp4_file in mp4_files:
            try:
                cap = cv2.VideoCapture(str(mp4_file))
                if cap.isOpened():
                    video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    frame_counts.append((mp4_file.name, video_frames))
                    cap.release()
                else:
                    if self.logger:
                        self.logger.warning(f"⚠️ Cannot open video: {mp4_file.name}")
            except Exception as e:  # noqa: PERF203
                if self.logger:
                    self.logger.warning(f"⚠️ Error reading video frames from {mp4_file.name}: {e}")
        
        if not frame_counts:
            raise ValueError(f"No valid data sources found in episode {ep_dir}")
        
        # 3. 取最小值（确保所有数据源都有对应的帧）
        min_frames = min(count for _, count in frame_counts)
        
        # 4. 记录帧数差异（用于调试）
        if self.logger and len(frame_counts) > 1:
            max_frames = max(count for _, count in frame_counts)
            if max_frames - min_frames > 1:  # 差异超过1帧时记录（降低阈值以便及时发现问题）
                diff_info = "\n".join([f"      - {name}: {count} frames" for name, count in frame_counts])
                self.logger.warning(
                    f"⚠️ Frame count mismatch in episode {ep_dir.name}:\n"
                    f"{diff_info}\n"
                    f"   ✅ Using minimum: {min_frames} frames to avoid index errors"
                )
        
        if self.logger:
            self.logger.debug(
                f"📊 Episode {ep_idx} ({ep_dir.name}): {min_frames} frames "
                f"(from {len(frame_counts)} data sources)"
            )
        
        return min_frames

    def _get_all_episode_dirs(self, task_path: Path) -> list[Path]:
        """获取所有episode目录（支持嵌套结构）
        
        该方法支持多种结构：
        1. 扁平结构：task_path/episode_0/*.hdf5
        2. 2层嵌套：task_path/color/episode_0/*.hdf5
        3. 3层嵌套：task_path/color/batch/episode_0/*.hdf5
        4. 4层嵌套：task_path/task_variant/color/batch/episode_0/*.hdf5
        
        判断标准：包含.hdf5或.h5文件的目录即为episode目录
        """
        def find_episode_dirs(path: Path, max_depth: int = 5, current_depth: int = 0) -> list[Path]:
            """递归查找episode目录（最多支持5层嵌套）"""
            if current_depth > max_depth:
                return []
            
            episode_dirs = []
            
            # 检查当前目录是否是episode目录（包含HDF5文件）
            h5_files = list(path.glob("*.hdf5")) + list(path.glob("*.h5"))
            if h5_files:
                episode_dirs.append(path)
                return episode_dirs  # 找到episode目录后不再向下搜索
            
            # 否则继续向下搜索子目录
            try:
                for sub_dir in path.iterdir():
                    # 跳过隐藏目录和特殊目录（以 . 或 @ 开头）
                    if sub_dir.is_dir() and not sub_dir.name.startswith('.') and not sub_dir.name.startswith('@'):
                        episode_dirs.extend(find_episode_dirs(sub_dir, max_depth, current_depth + 1))
            except PermissionError:
                if self.logger:
                    self.logger.warning(f"Permission denied when accessing {path}")
            
            return episode_dirs
        
        episodes = find_episode_dirs(task_path)
        
        if not episodes:
            raise FileNotFoundError(
                f"No episode directories found in {task_path}. "
                f"An episode directory should contain at least one .hdf5 or .h5 file."
            )
        
        return sorted(episodes)
    
    def _get_task_episodes_num(self, task_path: Path) -> int:
        """获取任务的episode数量"""
        return len(self._get_all_episode_dirs(task_path))

    def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int) -> dict[str, list[np.ndarray]]:
        """准备episode的图像缓冲区"""
        episodes = self._get_all_episode_dirs(task_path)
        ep_dir = episodes[ep_idx]
        
        images = {}
        # 遍历配置中的所有相机
        image_configs = self.converter_config[FEATURES_KEY][OBSERVATION_KEY][IMAGE_KEY]
        for image_config in image_configs:
            # 使用 args 中的 cam_name，这样与 _get_frame_image 中的键一致
            args = image_config.get(ARGS_KEY, {})
            cam_name = args.get(CAM_NAME_KEY)
            video_pattern = args.get('video_file_pattern', '*')
            
            if not cam_name:
                self.logger.warning(f"No cam_name specified in args for camera config: {image_config}")
                continue
            
            # 查找匹配的视频文件
            mp4_files = list(ep_dir.glob(video_pattern))
            if not mp4_files:
                self.logger.warning(f"No video file matching pattern '{video_pattern}' for camera '{cam_name}' in {ep_dir}")
                continue
            
            mp4_file = mp4_files[0]  # 使用第一个匹配的文件
            
            # 使用 PyAV 读取视频（支持 AV1 等更多编码格式）
            try:
                container = av.open(str(mp4_file))
                frames = []
                
                for frame in container.decode(video=0):
                    # PyAV 直接转换为 RGB 格式的 numpy array
                    img = frame.to_ndarray(format='rgb24')
                    frames.append(img)
                
                container.close()
                images[cam_name] = frames
                
                self.logger.info(f"Loaded {len(frames)} frames from {mp4_file.name} using PyAV")
                
            except Exception as e:
                raise OSError(f"Cannot open or decode video file {mp4_file}: {e}")
        
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
        h5_file = self._get_episode_h5_file(task_path, ep_idx)
        with h5py.File(h5_file, 'r') as f:
            if 'qpos' in f:
                return np.array(f['qpos'])
            raise ValueError(f"No qpos data in {h5_file}")

    def _prepare_episode_actions_buffer(self, task_path: Path, ep_idx: int) -> np.ndarray:
        """准备episode的动作缓冲区"""
        h5_file = self._get_episode_h5_file(task_path, ep_idx)
        with h5py.File(h5_file, 'r') as f:
            if 'action' in f:
                return np.array(f['action'])
            raise ValueError(f"No action data in {h5_file}")

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
            available_cams = list(images_buffer.keys())
            raise KeyError(
                f"❌ Camera not found in images buffer.\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}\n"
                f"   🎥 Requested camera: {cam_name}\n"
                f"   📋 Available cameras: {available_cams}\n"
                f"   💡 Check if camera name in config matches video files"
            )
        
        if frame_idx >= len(images_buffer[cam_name]):
            # 获取所有相机的帧数用于诊断
            frame_counts = {cam: len(frames) for cam, frames in images_buffer.items()}
            raise IndexError(
                f"❌ Frame index out of range for camera video.\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}\n"
                f"   🎥 Camera: {cam_name}\n"
                f"   🎯 Requested frame: {frame_idx}\n"
                f"   📐 Available frames: 0 to {len(images_buffer[cam_name])-1} ({len(images_buffer[cam_name])} total)\n"
                f"   📊 All camera frame counts: {frame_counts}\n"
                f"   💡 Possible causes:\n"
                f"      1. Video file is corrupted or incomplete\n"
                f"      2. Different cameras have different frame counts (inconsistent videos)\n"
                f"      3. timeline_offset in action requires accessing frame beyond video length"
            )
        
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

    def __del__(self) -> None:
        """清理视频读取器"""
        for cap in self._video_readers.values():
            if cap.isOpened():
                cap.release()
