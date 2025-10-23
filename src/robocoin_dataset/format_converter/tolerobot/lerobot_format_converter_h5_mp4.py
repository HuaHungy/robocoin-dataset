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
from robocoin_dataset.format_converter.utils.h5_file_cache import (
    H5FileCache,
)
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import (
    LerobotFormatConverter,
)
from robocoin_dataset.format_converter.tolerobot.lazy_video_reader import (
    LazyVideoReader,
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
        # 🔧 在super().__init__之前初始化这些属性，防止父类初始化失败时__del__报错
        self._video_readers = {}  # 缓存视频读取器
        self._is_test_mode = False  # Test模式标志（限制加载帧数）
        self._h5_files_cache = {}  # 缓存H5文件列表（episode定位优化）
        self._h5_file_cache = H5FileCache(max_cache_size=100, logger=logger)  # 🚀 H5文件句柄缓存

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

    def convert(self, is_test: bool = False) -> None:
        """重写父类方法以设置test模式标志
        
        Args:
            is_test: 是否为测试模式。测试模式只处理少量帧以快速验证
        """
        self._is_test_mode = is_test
        if is_test and self.logger:
            self.logger.info("🧪 H5Mp4 Converter running in TEST mode - will only load first 11 frames per video")
        
        # 调用父类的转换逻辑
        super().convert(is_test=is_test)

    def _prevalidate_files(self) -> None:
        """验证数据集文件完整性"""
        for task_path in self.path_task_dict.keys():
            # 使用优化的H5文件查找方法
            try:
                h5_files = self._get_all_episode_h5_files(task_path)
            except FileNotFoundError as e:
                raise FileNotFoundError(
                    f"❌ H5+MP4 format validation failed\n"
                    f"📁 Task path: {task_path}\n"
                    f"⚠️ {str(e)}\n"
                    f"💡 Hint: Task path should contain .hdf5 or .h5 files.\n"
                    f"         The converter supports nested directory structures."
                ) from e
            
            # 🆕 增加：只验证第一个episode的帧数（作为抽样检查）
            first_episode_validated = False
            
            for h5_file in h5_files:
                ep_dir = h5_file.parent  # 从H5文件获取所在目录
                
                # 检查是否有对应的MP4文件
                mp4_files = list(ep_dir.glob("*.mp4"))
                if not mp4_files:
                    self.logger.warning(f"No MP4 files found in {ep_dir}")
                    continue
                
                # 🆕 增加：对第一个episode验证视频帧数与H5数据帧数是否匹配
                if not first_episode_validated and mp4_files:
                    try:
                        # 🚀 使用H5FileCache获取预期帧数
                        expected_frame_count = None
                        with self._h5_file_cache.open(h5_file) as f:
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
        """获取episode的HDF5文件路径（优化：直接从缓存列表获取）"""
        h5_files = self._get_all_episode_h5_files(task_path)
        if ep_idx >= len(h5_files):
            raise IndexError(f"Episode index {ep_idx} out of range (0-{len(h5_files)-1})")
        return h5_files[ep_idx]

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
        h5_file = self._get_episode_h5_file(task_path, ep_idx)
        ep_dir = h5_file.parent  # 从H5文件获取目录
        
        frame_counts = []
        
        # 1. 获取 H5 数据帧数（🚀 使用H5FileCache）
        with self._h5_file_cache.open(h5_file) as f:
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
        
        # 🧪 Test模式：只返回10帧
        if self._is_test_mode:
            min_frames = min(10, min_frames)
            if self.logger:
                self.logger.debug(f"🧪 Test mode: limiting episode {ep_idx} to {min_frames} frames")
        
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

    def _get_all_episode_h5_files(self, task_path: Path) -> list[Path]:
        """获取所有episode的H5文件路径（优化：直接定位文件而不是目录）
        
        性能优化策略：
        1. 缓存结果（避免重复扫描）
        2. 先尝试扁平结构（最快）
        3. 再尝试1层嵌套
        4. 最后才使用递归（最慢）
        
        支持的结构：
        - 扁平：task_path/*.hdf5
        - 1层嵌套：task_path/episode_dir/*.hdf5
        - 深层嵌套：task_path/**/episode_dir/*.hdf5
        
        Returns:
            排序后的H5文件路径列表
        """
        # 缓存检查
        cache_key = str(task_path)
        if cache_key in self._h5_files_cache:
            return self._h5_files_cache[cache_key]
        
        h5_files = []
        
        # 策略1: 扁平结构（最快，直接在task_path下）
        h5_files = list(task_path.glob("*.hdf5")) + list(task_path.glob("*.h5"))
        
        if not h5_files:
            # 策略2: 1层嵌套（常见情况）
            for subdir in task_path.iterdir():
                if subdir.is_dir() and not subdir.name.startswith('.') and not subdir.name.startswith('@'):
                    h5_files.extend(subdir.glob("*.hdf5"))
                    h5_files.extend(subdir.glob("*.h5"))
        
        if not h5_files:
            # 策略3: 递归查找（最慢，但最灵活）
            h5_files = list(task_path.glob("**/*.hdf5")) + list(task_path.glob("**/*.h5"))
            # 过滤隐藏目录
            h5_files = [f for f in h5_files if not any(part.startswith('.') or part.startswith('@') for part in f.parts)]
        
        if not h5_files:
            raise FileNotFoundError(
                f"No .h5 or .hdf5 files found in {task_path}. "
                f"Please check if the dataset path is correct."
            )
        
        # 排序并缓存
        h5_files = sorted(h5_files)
        self._h5_files_cache[cache_key] = h5_files
        
        return h5_files
    
    def _get_task_episodes_num(self, task_path: Path) -> int:
        """获取任务的episode数量"""
        return len(self._get_all_episode_h5_files(task_path))

    def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int, is_test: bool = False) -> dict[str, LazyVideoReader | list[np.ndarray]]:
        """准备episode的图像缓冲区
        
        🚀 性能优化：使用LazyVideoReader延迟加载，大幅降低内存占用
        - 原方案：一次性加载所有帧到内存（500MB+）
        - 新方案：按需读取帧（<20MB）
        
        Args:
            task_path: 任务路径
            ep_idx: Episode索引
            is_test: 是否为测试模式。测试模式加载前11帧用于验证
        
        Returns:
            字典，键为相机名称，值为LazyVideoReader（正式模式）或帧列表（测试模式）
        """
        h5_file = self._get_episode_h5_file(task_path, ep_idx)
        ep_dir = h5_file.parent  # 从H5文件获取目录
        
        # 🧪 Test模式：仍然加载少量帧到内存（用于快速验证）
        if is_test or self._is_test_mode:
            max_frames = 11
            if self.logger:
                self.logger.info(f"🧪 Test mode: loading max {max_frames} frames into memory for episode {ep_idx}")
            
            return self._load_frames_to_memory(ep_dir, max_frames)
        
        # 🚀 正式模式：使用LazyVideoReader（按需加载，节省内存）
        images = {}
        image_configs = self.converter_config[FEATURES_KEY][OBSERVATION_KEY][IMAGE_KEY]
        
        for image_config in image_configs:
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
            
            mp4_file = mp4_files[0]
            
            # 🚀 创建LazyVideoReader（延迟加载）
            try:
                lazy_reader = LazyVideoReader(
                    video_path=mp4_file,
                    logger=self.logger,
                    convert_to_rgb=True
                )
                images[cam_name] = lazy_reader
                
                if self.logger:
                    self.logger.info(
                        f"🚀 Created LazyVideoReader for {mp4_file.name} "
                        f"({lazy_reader.num_frames} frames, will load on-demand)"
                    )
                
            except Exception as e:
                raise OSError(f"Cannot create LazyVideoReader for {mp4_file}: {e}")
        
        return images
    
    def _load_frames_to_memory(self, ep_dir: Path, max_frames: int | None = None) -> dict[str, list[np.ndarray]]:
        """辅助方法：将视频帧加载到内存（用于测试模式）
        
        Args:
            ep_dir: Episode目录
            max_frames: 最大加载帧数（None表示全部）
        
        Returns:
            字典，键为相机名称，值为帧列表
        """
        images = {}
        image_configs = self.converter_config[FEATURES_KEY][OBSERVATION_KEY][IMAGE_KEY]
        
        for image_config in image_configs:
            args = image_config.get(ARGS_KEY, {})
            cam_name = args.get(CAM_NAME_KEY)
            video_pattern = args.get('video_file_pattern', '*')
            
            if not cam_name:
                continue
            
            mp4_files = list(ep_dir.glob(video_pattern))
            if not mp4_files:
                self.logger.warning(f"No video file matching pattern '{video_pattern}' for camera '{cam_name}' in {ep_dir}")
                continue
            
            mp4_file = mp4_files[0]
            
            # 使用 PyAV 读取视频到内存
            container = None
            try:
                container = av.open(str(mp4_file))
                frames = []
                
                for frame_idx, frame in enumerate(container.decode(video=0)):
                    if max_frames is not None and frame_idx >= max_frames:
                        break
                    
                    img = frame.to_ndarray(format='rgb24')
                    frames.append(img)
                
                images[cam_name] = frames
                
                if self.logger:
                    self.logger.info(f"Loaded {len(frames)} frames from {mp4_file.name} into memory")
                
            except Exception as e:
                raise OSError(f"Cannot open or decode video file {mp4_file}: {e}")
            finally:
                if container:
                    container.close()
        
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
        """准备episode的状态缓冲区
        
        🚀 性能优化：使用H5FileCache复用文件句柄，提高读取速度（10倍+）
        """
        h5_file = self._get_episode_h5_file(task_path, ep_idx)
        with self._h5_file_cache.open(h5_file) as f:
            if 'qpos' in f:
                return np.array(f['qpos'])
            raise ValueError(f"No qpos data in {h5_file}")

    def _prepare_episode_actions_buffer(self, task_path: Path, ep_idx: int) -> np.ndarray:
        """准备episode的动作缓冲区
        
        🚀 性能优化：使用H5FileCache复用文件句柄，提高读取速度（10倍+）
        """
        h5_file = self._get_episode_h5_file(task_path, ep_idx)
        with self._h5_file_cache.open(h5_file) as f:
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
    
    def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
        """获取 H5+MP4 episode 的源文件信息
        
        Args:
            task_path: 任务路径
            ep_idx: episode 索引
        
        Returns:
            dict: 包含源文件信息的字典，包括 h5_file, video_files 和 absolute_paths
        """
        try:
            h5_files = self._get_all_episode_h5_files(task_path)
            if ep_idx < len(h5_files):
                h5_file = h5_files[ep_idx]
                
                # 收集视频文件
                video_files = []
                for cam_config in self.image_configs:
                    video_path = cam_config.get("args", {}).get("video_path", "")
                    if video_path:
                        # 替换占位符
                        video_path = video_path.format(ep_idx=ep_idx)
                        full_video_path = task_path / video_path
                        if full_video_path.exists():
                            video_files.append({
                                "camera": cam_config["cam_name"],
                                "relative_path": str(full_video_path.relative_to(self.dataset_path)),
                                "absolute_path": str(full_video_path.absolute()),
                            })
                
                return {
                    "format": "H5+MP4",
                    "h5_file": str(h5_file.relative_to(self.dataset_path)),
                    "h5_absolute_path": str(h5_file.absolute()),
                    "video_files": video_files,
                }
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to get source files for episode {ep_idx}: {e}")
        
        return {}

    def __del__(self) -> None:
        """清理视频读取器"""
        for cap in self._video_readers.values():
            if cap.isOpened():
                cap.release()
