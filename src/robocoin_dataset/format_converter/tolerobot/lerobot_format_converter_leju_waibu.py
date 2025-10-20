"""LeRobot format converter for Leju Waibu dataset format.

Dataset structure:
    data/leju_waibu/
    ├── local_task_info.yaml
    ├── local_dataset_info.yaml
    └── <episode_id>/
        ├── metadata.json
        ├── camera/video/
        │   ├── head_cam_h.mp4
        │   ├── wrist_cam_l.mp4
        │   └── wrist_cam_r.mp4
        └── proprio_stats/
            └── proprio_stats.hdf5
"""

import json
import logging
from pathlib import Path
from typing import Any

import cv2
import h5py
import numpy as np

from robocoin_dataset.format_converter.tolerobot.constant import (
    ARGS_KEY,
    CAM_NAME_KEY,
)
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import (
    LerobotFormatConverter,
)


class LerobotFormatConverterLejuWaibu(LerobotFormatConverter):
    """Converter for Leju Waibu format: metadata.json + H5 + MP4 videos."""

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

    def _get_dataset_task_paths(self) -> dict[Path, str]:
        """Find all episode directories containing metadata.json and proprio_stats.hdf5.
        
        Leju dataset structure:
        dataset_path/ (e.g., Scan_code_for_weighing/)
          ├── local_dataset_info.yaml
          └── subtask/ (e.g., more_scan_code_for_weighing/)
              ├── local_task_info.yaml  ← Task info at subtask level
              └── episode_uuid/
                  ├── metadata.json
                  └── proprio_stats/proprio_stats.hdf5
        
        Returns:
            dict mapping episode directory paths to task names
        """
        import yaml
        
        task_paths_dict = {}
        
        # Look for subtask directories (one level down from dataset_path)
        # Each subtask directory should contain local_task_info.yaml
        subtask_dirs = [d for d in self.dataset_path.iterdir() if d.is_dir()]
        
        if not subtask_dirs:
            root_files = [f.name for f in self.dataset_path.iterdir() if f.is_file()]
            raise FileNotFoundError(
                f"❌ No subtask directories found.\n"
                f"    Dataset path: {self.dataset_path}\n"
                f"   📋 Files in root: {root_files}\n"
                f"   💡 Expected structure: dataset_path/subtask/episodes/\n"
                f"   💡 Check if dataset has been extracted correctly"
            )
        
        # Process each subtask directory
        for subtask_dir in subtask_dirs:
            local_task_info_path = subtask_dir / "local_task_info.yaml"
            
            if not local_task_info_path.exists():
                self.logger.warning(f"⚠️  Skipping {subtask_dir.name}: no local_task_info.yaml found")
                continue
            
            # Read task info from subtask directory
            try:
                with open(local_task_info_path) as f:
                    task_info_dict = yaml.safe_load(f)
                    task_index = task_info_dict["task_index"]
                    task = self.tasks[task_index]
            except KeyError as e:
                self.logger.warning(
                    f"⚠️  Skipping {subtask_dir.name}: Invalid task info format.\n"
                    f"   📄 File: {local_task_info_path}\n"
                    f"   ❌ Missing key: {e!s}"
                )
                continue
            except Exception as e:
                self.logger.warning(
                    f"⚠️  Skipping {subtask_dir.name}: Failed to read task info.\n"
                    f"   📄 File: {local_task_info_path}\n"
                    f"   ❌ Error: {e!s}"
                )
                continue
            
            # Scan for episode directories in this subtask
            episode_count = 0
            for episode_dir in subtask_dir.iterdir():
                if episode_dir.is_dir():
                    metadata_file = episode_dir / "metadata.json"
                    h5_file = episode_dir / "proprio_stats" / "proprio_stats.hdf5"
                    
                    if metadata_file.exists() and h5_file.exists():
                        task_paths_dict[episode_dir] = task
                        episode_count += 1
            
            self.logger.info(f"✅ Subtask '{subtask_dir.name}': Found {episode_count} episodes for task '{task}'")
        
        if not task_paths_dict:
            # List all subtask directories to help diagnose
            all_subtasks = [d.name for d in subtask_dirs]
            raise FileNotFoundError(
                f"❌ No valid episode directories found in any subtask.\n"
                f"   📂 Dataset path: {self.dataset_path}\n"
                f"   📋 Subtasks found: {all_subtasks}\n"
                f"   💡 Valid episode must have:\n"
                f"      - metadata.json\n"
                f"      - proprio_stats/proprio_stats.hdf5\n"
                f"   💡 Check if:\n"
                f"      1. Episodes have been recorded\n"
                f"      2. Required files exist in episode directories\n"
                f"      3. Dataset extraction was complete"
            )
        
        return task_paths_dict

    def _prevalidate_files(self) -> None:
        """Validate that required files exist for each episode."""
        # 🆕 增加：验证所有episode_path存在性
        for episode_path in self.path_task_dict.keys():
            if not episode_path.exists():
                # 显示父目录内容
                parent_dir = episode_path.parent
                siblings = []
                if parent_dir.exists():
                    siblings = [d.name for d in parent_dir.iterdir() if d.is_dir()]
                    if len(siblings) > 15:
                        siblings = siblings[:15] + [f"... ({len(siblings) - 15} more)"]
                
                raise FileNotFoundError(
                    f"❌ Episode path does not exist\n"
                    f"   📂 Episode path: {episode_path}\n"
                    f"   📂 Parent directory: {parent_dir}\n"
                    f"   📋 Available directories in parent:\n"
                    f"      {', '.join(siblings) if siblings else 'Parent directory not found'}\n"
                    f"   💡 Please check:\n"
                    f"      1. Path is correct in configuration\n"
                    f"      2. Dataset has been downloaded/extracted\n"
                    f"      3. No typos in directory names"
                )
            
            if not episode_path.is_dir():
                raise NotADirectoryError(
                    f"❌ Episode path exists but is not a directory\n"
                    f"   📂 Path: {episode_path}\n"
                    f"   📋 Type: {('file' if episode_path.is_file() else 'unknown')}\n"
                    f"   💡 Episode path must be a directory containing metadata, proprio_stats, etc."
                )
        
        for episode_path in self.path_task_dict.keys():
            # Check metadata
            metadata_file = episode_path / "metadata.json"
            if not metadata_file.exists():
                episode_files = [f.name for f in episode_path.iterdir() if f.is_file()]
                raise FileNotFoundError(
                    f"❌ Metadata file not found.\n"
                    f"   📄 Expected file: metadata.json\n"
                    f"   📂 Episode path: {episode_path}\n"
                    f"   📋 Files in episode: {episode_files}\n"
                    f"   💡 Check if:\n"
                    f"      1. Episode was recorded completely\n"
                    f"      2. metadata.json exists in episode root\n"
                    f"      3. File name is exactly 'metadata.json'"
                )
            
            # 🆕 增加：验证metadata.json内容
            try:
                import json
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    if not isinstance(metadata, dict):
                        self.logger.warning(
                            f"⚠️ Metadata不是字典格式\n"
                            f"📄 文件：{metadata_file}\n"
                            f"📋 类型：{type(metadata).__name__}\n"
                            "💡 期望JSON对象（字典）"
                        )
                    else:
                        self.logger.info(
                            f"✅ Metadata验证通过：{metadata_file.name}\n"
                            f"   - 键数量：{len(metadata)}\n"
                            f"   - 主要键：{list(metadata.keys())[:5]}"
                        )
            except json.JSONDecodeError as e:
                self.logger.warning(
                    f"⚠️ Metadata JSON解析失败\n"
                    f"📄 文件：{metadata_file}\n"
                    f"⚠️ 错误：第{e.lineno}行，第{e.colno}列\n"
                    f"   {str(e)}\n"
                    "💡 请检查JSON文件格式是否正确"
                )
            except Exception as e:
                self.logger.warning(f"⚠️ 无法读取metadata文件：{e}")
            
            # Check H5 file
            h5_file = episode_path / "proprio_stats" / "proprio_stats.hdf5"
            if not h5_file.exists():
                proprio_dir = episode_path / "proprio_stats"
                proprio_files = []
                if proprio_dir.exists():
                    proprio_files = [f.name for f in proprio_dir.iterdir() if f.is_file()]
                
                raise FileNotFoundError(
                    f"❌ Proprio stats H5 file not found.\n"
                    f"   📄 Expected file: proprio_stats.hdf5\n"
                    f"   📂 Expected path: {h5_file}\n"
                    f"   📂 Episode path: {episode_path}\n"
                    f"   📋 Files in proprio_stats/: {proprio_files if proprio_dir.exists() else 'Directory not found'}\n"
                    f"   💡 Check if:\n"
                    f"      1. proprio_stats directory exists\n"
                    f"      2. proprio_stats.hdf5 file exists\n"
                    f"      3. Episode recording was complete"
                )
            
            # 🆕 增加：验证H5文件内容
            try:
                import h5py
                with h5py.File(h5_file, 'r') as f:
                    datasets = list(f.keys())
                    if not datasets:
                        self.logger.warning(
                            f"⚠️ H5文件为空\n"
                            f"📄 文件：{h5_file}\n"
                            "💡 这可能导致后续转换失败"
                        )
                    else:
                        self.logger.info(
                            f"✅ H5文件验证通过：{h5_file.name}\n"
                            f"   - 数据集数量：{len(datasets)}\n"
                            f"   - 数据集列表：{datasets[:5]}"
                        )
            except Exception as e:
                self.logger.warning(
                    f"⚠️ 无法读取H5文件\n"
                    f"📄 文件：{h5_file}\n"
                    f"⚠️ 错误：{str(e)}\n"
                    "💡 请检查H5文件是否损坏"
                )
            
            # Check video files
            video_dir = episode_path / "camera" / "video"
            if not video_dir.exists():
                self.logger.warning(f"Video directory not found: {video_dir}")

    def _get_task_episodes_num(self, task_path: Path) -> int:
        """Each episode directory is one episode."""
        return 1

    def _get_episode_entry(self, task_path: Path, ep_idx: int) -> dict:
        """Get episode metadata from metadata.json.
        
        Args:
            task_path: Path to episode directory
            ep_idx: Episode index (always 0 for this format)
            
        Returns:
            dict with episode metadata
        """
        metadata_file = task_path / "metadata.json"
        with open(metadata_file) as f:
            metadata = json.load(f)
        
        return {
            "episode_id": metadata.get("episode_id", task_path.name),
            "task_name": metadata.get("task_name", ""),
            "english_task_name": metadata.get("english_task_name", ""),
            "scene_name": metadata.get("scene_name", ""),
            "file_duration": metadata.get("file_duration", 0),
        }

    def _get_episode_frames_num(self, task_path: Path, ep_idx: int) -> int:
        """Get number of frames from H5 file.
        
        Args:
            task_path: Path to episode directory
            ep_idx: Episode index
            
        Returns:
            Number of frames in the episode
        """
        h5_file = task_path / "proprio_stats" / "proprio_stats.hdf5"
        with h5py.File(h5_file, "r") as f:
            # Use timestamps array to get frame count
            return len(f["timestamps"])

    def _get_h5_file_path(self, task_path: Path, ep_idx: int) -> Path:
        """Get path to H5 file for an episode.
        
        Args:
            task_path: Path to episode directory
            ep_idx: Episode index
            
        Returns:
            Path to H5 file
        """
        return task_path / "proprio_stats" / "proprio_stats.hdf5"

    def _get_video_file_path(self, task_path: Path, ep_idx: int, cam_name: str) -> Path:
        """Get path to video file for a camera.
        
        Args:
            task_path: Path to episode directory
            ep_idx: Episode index
            cam_name: Camera name
            
        Returns:
            Path to video file
        """
        video_path = task_path / "camera" / "video" / f"{cam_name}.mp4"
        if not video_path.exists():
            video_dir = task_path / "camera" / "video"
            available_videos = []
            if video_dir.exists():
                available_videos = [f.name for f in video_dir.glob("*.mp4")]
            
            raise FileNotFoundError(
                f"❌ Video file not found.\n"
                f"   📹 Camera: {cam_name}\n"
                f"   📄 Expected file: {video_path.name}\n"
                f"   📂 Video directory: {video_dir}\n"
                f"   📂 Episode path: {task_path}\n"
                f"   📋 Available videos: {available_videos if available_videos else 'None'}\n"
                f"   💡 Check if:\n"
                f"      1. Camera name matches video file name\n"
                f"      2. Video file exists in camera/video/\n"
                f"      3. Video recording was successful"
            )
        return video_path

    def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int) -> Any:
        """Prepare image buffer by loading all video frames.
        
        Args:
            task_path: Path to episode directory
            ep_idx: Episode index
            
        Returns:
            dict mapping camera names to arrays of frames
        """
        images_buffer = {}
        
        for image_config in self.converter_config["features"]["observation"]["images"]:
            cam_name = image_config[CAM_NAME_KEY]
            video_path = self._get_video_file_path(task_path, ep_idx, cam_name)
            
            # Load all frames from video
            frames = []
            cap = cv2.VideoCapture(str(video_path))
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                # Convert BGR to RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frames.append(frame_rgb)
            cap.release()
            
            images_buffer[cam_name] = np.array(frames)
            self.logger.info(f"Loaded {len(frames)} frames from {cam_name}")
        
        return images_buffer

    def _prepare_episode_states_buffer(self, task_path: Path, ep_idx: int) -> Any:
        """Load state data from H5 file.
        
        Args:
            task_path: Path to episode directory
            ep_idx: Episode index
            
        Returns:
            dict mapping h5_path to data arrays
        """
        h5_file = self._get_h5_file_path(task_path, ep_idx)
        states_buffer = {}
        
        with h5py.File(h5_file, "r") as f:
            for sub_state in self.converter_config["features"]["observation"]["state"]["sub_state"]:
                h5_path = sub_state[ARGS_KEY]["h5_path"]
                if h5_path not in states_buffer:
                    try:
                        states_buffer[h5_path] = np.array(f[h5_path])
                    except KeyError:
                        # H5路径不存在，收集可用路径信息
                        available_paths = []
                        
                        def collect_paths(name, obj):
                            if isinstance(obj, h5py.Dataset):
                                available_paths.append(name)
                        
                        f.visititems(collect_paths)
                        
                        error_msg = (
                            f"❌ H5 路径不存在\n"
                            f"   📁 H5 文件: {h5_file.name}\n"
                            f"   🔍 期望路径: {h5_path}\n"
                            f"   📊 文件中实际存在的数据集路径:\n"
                        )
                        for path in sorted(available_paths[:20]):  # 只显示前20个
                            error_msg += f"      - {path}\n"
                        if len(available_paths) > 20:
                            error_msg += f"      ... 还有 {len(available_paths) - 20} 个路径\n"
                        
                        error_msg += (
                            f"   💡 可能原因:\n"
                            f"      1. 配置文件中的 h5_path 拼写错误\n"
                            f"      2. H5 文件结构与配置不匹配\n"
                            f"      3. 数据采集时未记录该数据项\n"
                            f"   🔧 解决方法:\n"
                            f"      1. 检查配置文件 converter_config_leju_waibu.yaml\n"
                            f"      2. 使用 h5dump 或 HDFView 查看 H5 文件结构\n"
                            f"      3. 更新配置使用实际存在的路径\n"
                        )
                        
                        if self.logger:
                            self.logger.error(error_msg)
                        
                        raise KeyError(error_msg)
        
        return states_buffer

    def _prepare_episode_actions_buffer(self, task_path: Path, ep_idx: int) -> Any:
        """Load action data from H5 file.
        
        Args:
            task_path: Path to episode directory
            ep_idx: Episode index
            
        Returns:
            dict mapping h5_path to data arrays
        """
        h5_file = self._get_h5_file_path(task_path, ep_idx)
        actions_buffer = {}
        
        with h5py.File(h5_file, "r") as f:
            for sub_action in self.converter_config["features"]["action"]["sub_action"]:
                h5_path = sub_action[ARGS_KEY]["h5_path"]
                if h5_path not in actions_buffer:
                    try:
                        # Special handling for joint velocity in actions (use state velocity)
                        if h5_path == "state/joint/velocity":
                            actions_buffer[h5_path] = np.array(f[h5_path])
                        else:
                            actions_buffer[h5_path] = np.array(f[h5_path])
                    except KeyError:
                        # H5路径不存在，收集可用路径信息
                        available_paths = []
                        
                        def collect_paths(name, obj):
                            if isinstance(obj, h5py.Dataset):
                                available_paths.append(name)
                        
                        f.visititems(collect_paths)
                        
                        error_msg = (
                            f"❌ H5 路径不存在 (action)\n"
                            f"   📁 H5 文件: {h5_file.name}\n"
                            f"   🔍 期望路径: {h5_path}\n"
                            f"   📊 文件中实际存在的数据集路径:\n"
                        )
                        for path in sorted(available_paths[:20]):  # 只显示前20个
                            error_msg += f"      - {path}\n"
                        if len(available_paths) > 20:
                            error_msg += f"      ... 还有 {len(available_paths) - 20} 个路径\n"
                        
                        error_msg += (
                            "   💡 可能原因:\n"
                            "      1. 配置文件中的 h5_path 拼写错误\n"
                            "      2. H5 文件结构与配置不匹配\n"
                            "      3. 数据采集时未记录该数据项\n"
                            "   🔧 解决方法:\n"
                            "      1. 检查配置文件 converter_config_leju_waibu.yaml\n"
                            "      2. 使用 h5dump 或 HDFView 查看 H5 文件结构\n"
                            "      3. 更新配置使用实际存在的路径\n"
                        )
                        
                        if self.logger:
                            self.logger.error(error_msg)
                        
                        raise KeyError(error_msg)
        
        return actions_buffer

    def _get_frame_image(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        images_buffer: Any = None,
    ) -> np.ndarray:
        """Get image for a specific frame.
        
        Args:
            task_path: Path to episode directory
            ep_idx: Episode index
            frame_idx: Frame index
            args_dict: Arguments dict with cam_name
            images_buffer: Pre-loaded images buffer
            
        Returns:
            Image array (H, W, C)
        """
        cam_name = args_dict[CAM_NAME_KEY]
        
        if images_buffer is not None and cam_name in images_buffer:
            return images_buffer[cam_name][frame_idx]
        
        # Fallback: load from video
        video_path = self._get_video_file_path(task_path, ep_idx, cam_name)
        cap = cv2.VideoCapture(str(video_path))
        
        if not cap.isOpened():
            raise OSError(
                f"❌ Cannot open video file.\n"
                f"   📹 Camera: {cam_name}\n"
                f"   📄 Video file: {video_path}\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                f"   💡 Check if:\n"
                f"      1. Video file is not corrupted\n"
                f"      2. Video codec is supported by OpenCV\n"
                f"      3. File permissions are correct"
            )
        
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            raise ValueError(
                f"❌ Failed to read frame from video.\n"
                f"   🎯 Requested frame: {frame_idx}\n"
                f"   📹 Camera: {cam_name}\n"
                f"   📄 Video file: {video_path}\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}\n"
                f"   📐 Total frames in video: {total_frames}\n"
                f"   💡 Check if:\n"
                f"      1. Frame index is within valid range (0 to {total_frames-1})\n"
                f"      2. Video file is not corrupted\n"
                f"      3. Video was recorded completely"
            )
        
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    def _get_frame_sub_states(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        sub_states_buffer: Any = None,
    ) -> np.ndarray:
        """Get state data for a specific frame.
        
        Args:
            task_path: Path to episode directory
            ep_idx: Episode index
            frame_idx: Frame index
            args_dict: Arguments dict with h5_path and range info
            sub_states_buffer: Pre-loaded states buffer
            
        Returns:
            State array
        """
        h5_path = args_dict["h5_path"]
        range_from = args_dict["range_from"]
        range_to = args_dict["range_to"]
        
        if sub_states_buffer is not None and h5_path in sub_states_buffer:
            data = sub_states_buffer[h5_path][frame_idx]
        else:
            h5_file = self._get_h5_file_path(task_path, ep_idx)
            with h5py.File(h5_file, "r") as f:
                data = f[h5_path][frame_idx]
        
        return np.array(data[range_from:range_to], dtype=np.float32)

    def _get_frame_sub_actions(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        sub_actions_buffer: Any = None,
    ) -> np.ndarray:
        """Get action data for a specific frame.
        
        Args:
            task_path: Path to episode directory
            ep_idx: Episode index
            frame_idx: Frame index
            args_dict: Arguments dict with h5_path and range info
            sub_actions_buffer: Pre-loaded actions buffer
            
        Returns:
            Action array
        """
        h5_path = args_dict["h5_path"]
        range_from = args_dict["range_from"]
        range_to = args_dict["range_to"]
        
        if sub_actions_buffer is not None and h5_path in sub_actions_buffer:
            data = sub_actions_buffer[h5_path][frame_idx]
        else:
            h5_file = self._get_h5_file_path(task_path, ep_idx)
            with h5py.File(h5_file, "r") as f:
                data = f[h5_path][frame_idx]
        
        return np.array(data[range_from:range_to], dtype=np.float32)
