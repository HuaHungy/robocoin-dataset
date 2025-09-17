import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import (
    LerobotFormatConverter,
)


class LerobotFormatConverterLerobot(LerobotFormatConverter):
    """
    Converter for LeRobot format datasets to our standard format.
    Handles:
    1. Reading parquet data from LeRobot datasets
    2. Extracting and converting various data types (states, actions, images)
    3. Restructuring data according to our configuration mapping
    """

    def __init__(
        self,
        dataset_path: str,
        output_path: str,
        converter_config: dict,
        repo_id: str,
        device_model: str | None = None,
        logger: logging.Logger | None = None,
        video_backend: str = "pyav",
        image_writer_processes: int = 4,
        image_writer_threads: int = 4,
    ) -> None:
        # Store dataset-specific paths BEFORE calling parent constructor
        self.lerobot_data_path = Path(dataset_path)
        self.parquet_files = list((self.lerobot_data_path / "data" / "chunk-000").glob("*.parquet"))
        self.videos_path = self.lerobot_data_path / "videos"
        
        # Load dataset metadata
        self._load_metadata()
        
        # Call parent constructor
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
        
        # Log metadata info now that logger is available
        if self.logger:
            self.logger.info(f"Loaded {len(self.episodes)} episodes and {len(self.tasks_metadata)} tasks from LeRobot dataset")

    def _prevalidate_files(self) -> None:
        """Validate that the LeRobot dataset has required structure and files"""
        dataset_path = Path(self.dataset_path)
        
        # Check if dataset directory exists
        if not dataset_path.exists():
            raise FileNotFoundError(f"Dataset path {dataset_path} does not exist")
        
        # Check for required directories
        required_dirs = ["data", "meta", "videos"]
        missing_dirs = []
        for dir_name in required_dirs:
            dir_path = dataset_path / dir_name
            if not dir_path.exists():
                missing_dirs.append(str(dir_path))
        
        if missing_dirs:
            if self.logger:
                self.logger.warning(f"Missing directories in LeRobot dataset: {missing_dirs}")
        
        # Check for data files
        data_dir = dataset_path / "data" / "chunk-000"
        if data_dir.exists():
            parquet_files = list(data_dir.glob("*.parquet"))
            if not parquet_files:
                if self.logger:
                    self.logger.warning(f"No parquet files found in {data_dir}")
            else:
                # Enhanced validation: check parquet structure against configuration
                self._validate_lerobot_structure(parquet_files[0])
        else:
            if self.logger:
                self.logger.warning(f"Data directory {data_dir} does not exist")
        
        # Check for metadata files
        meta_dir = dataset_path / "meta"
        if meta_dir.exists():
            required_meta_files = ["episodes.jsonl", "tasks.jsonl"]
            for meta_file in required_meta_files:
                meta_file_path = meta_dir / meta_file
                if not meta_file_path.exists():
                    if self.logger:
                        self.logger.warning(f"Missing metadata file: {meta_file_path}")
        
        # Check for videos directory
        videos_dir = dataset_path / "videos"
        if videos_dir.exists() and self.logger:
            video_chunks = list(videos_dir.glob("chunk-*"))
            self.logger.info(f"Found {len(video_chunks)} video chunks in {videos_dir}")

    def _validate_lerobot_structure(self, parquet_file: Path) -> None:
        """Validate internal LeRobot parquet structure against configuration"""
        try:
            import pandas as pd
            
            if self.logger:
                self.logger.info(f"Validating LeRobot parquet structure: {parquet_file}")
            
            # Read a small sample to check column structure
            df = pd.read_parquet(parquet_file, engine='pyarrow')
            available_columns = set(df.columns)
            
            if self.logger:
                self.logger.info(f"Available parquet columns: {sorted(available_columns)}")
            
            # Get expected fields from configuration
            expected_state_fields = set()
            expected_action_fields = set()
            expected_image_fields = set()
            
            # Extract expected state fields from configuration
            if hasattr(self, 'converter_config') and self.converter_config:
                state_config = self.converter_config.get('state', {})
                if 'sub_state' in state_config:
                    for sub_state in state_config['sub_state']:
                        if 'names' in sub_state:
                            expected_state_fields.update(sub_state['names'])
                
                # Extract expected action fields from configuration
                action_config = self.converter_config.get('action', {})
                if 'sub_action' in action_config:
                    for sub_action in action_config['sub_action']:
                        if 'names' in sub_action:
                            expected_action_fields.update(sub_action['names'])
                
                # Extract expected image fields from configuration
                image_config = self.converter_config.get('image', {})
                if 'sub_image' in image_config:
                    for sub_image in image_config['sub_image']:
                        if 'names' in sub_image:
                            expected_image_fields.update(sub_image['names'])
            
            # Validate state fields
            missing_state_fields = expected_state_fields - available_columns
            if missing_state_fields:
                if self.logger:
                    self.logger.warning(f"Missing state fields in parquet: {sorted(missing_state_fields)}")
            
            # Validate action fields
            missing_action_fields = expected_action_fields - available_columns
            if missing_action_fields:
                if self.logger:
                    self.logger.warning(f"Missing action fields in parquet: {sorted(missing_action_fields)}")
            
            # Validate image fields (these may be stored differently)
            missing_image_fields = expected_image_fields - available_columns
            if missing_image_fields:
                if self.logger:
                    self.logger.info(f"Image fields not found in parquet (may be in video files): {sorted(missing_image_fields)}")
            
            # Check for common LeRobot standard columns
            standard_columns = {'timestamp', 'episode_index', 'frame_index'}
            missing_standard = standard_columns - available_columns
            if missing_standard:
                if self.logger:
                    self.logger.warning(f"Missing standard LeRobot columns: {sorted(missing_standard)}")
            
            # Log successful validation
            if self.logger:
                found_state_fields = expected_state_fields & available_columns
                found_action_fields = expected_action_fields & available_columns
                self.logger.info(f"Validated state fields ({len(found_state_fields)}): {sorted(found_state_fields)}")
                self.logger.info(f"Validated action fields ({len(found_action_fields)}): {sorted(found_action_fields)}")
                self.logger.info(f"LeRobot structure validation completed for {parquet_file}")
        
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error validating LeRobot structure: {e}")
            # Don't raise exception to avoid breaking conversion, just log the issue

    def _load_metadata(self) -> None:
        """Load LeRobot dataset metadata"""
        
        # Load episodes info
        episodes_file = self.lerobot_data_path / "meta" / "episodes.jsonl"
        self.episodes = []
        if episodes_file.exists():
            with open(episodes_file) as f:
                for line in f:
                    self.episodes.append(json.loads(line.strip()))
        
        # Load tasks info
        tasks_file = self.lerobot_data_path / "meta" / "tasks.jsonl"
        self.tasks_metadata = []
        if tasks_file.exists():
            with open(tasks_file) as f:
                for line in f:
                    self.tasks_metadata.append(json.loads(line.strip()))
        
        # Log after parent constructor is called (when logger is available)
        # This will be called again after super().__init__ if needed

    def _get_tasks(self) -> list[str]:
        """Override to provide generic task structure for LeRobot datasets"""
        # For generic LeRobot datasets, we can derive task names from metadata
        # or default to a single manipulation task
        if self.tasks_metadata:
            return [task.get("task_name", "manipulation_task") for task in self.tasks_metadata]
        return ["manipulation_task"]

    def _get_dataset_task_paths(self) -> dict[Path, str]:
        """Override to provide generic task path mapping for LeRobot datasets"""
        tasks = self._get_tasks()
        # For LeRobot format, all data is typically in one location
        return {self.lerobot_data_path: tasks[0]}

    def _get_task_episodes_num(self, task_path: Path) -> int:
        """Override to provide episode count from parquet files"""
        return len(self.parquet_files)









    def _move_videos_to_standard_structure(self) -> None:
        """Copy video files to output/videos/{cam_name}/ according to config.
        
        For G1 LeRobot datasets, videos are organized in folders containing 'left' and 'right' in names,
        with mp4 files inside these folders.
        """
        import glob
        import os
        import shutil
        
        # 1. 获取 config 里的 cam_name 列表
        cam_configs = self.converter_config.get('features', {}).get('observation', {}).get('images', [])
        cam_names = [c.get('cam_name') for c in cam_configs if 'cam_name' in c]
        
        # 2. 源视频目录
        src_videos_path = self.lerobot_data_path / "videos"
        if not src_videos_path.exists():
            if self.logger:
                self.logger.warning(f"No videos directory found at {src_videos_path}")
            return
        
        # 3. 目标根目录
        target_videos_path = Path(self.output_path) / "videos"
        target_videos_path.mkdir(parents=True, exist_ok=True)
        
        # 4. 遍历每个相机，查找并复制视频文件
        for cam_name in cam_names:
            # 创建目标文件夹
            target_cam_dir = target_videos_path / cam_name
            target_cam_dir.mkdir(parents=True, exist_ok=True)
            
            # 查找包含left或right的文件夹，适配G1 LeRobot数据集结构
            found_videos = False
            
            # 遍历所有chunk文件夹和子文件夹
            for chunk_dir in src_videos_path.glob("*"):
                if chunk_dir.is_dir():
                    # 在chunk目录下查找包含left/right的子目录
                    for sub_dir in chunk_dir.iterdir():
                        if sub_dir.is_dir():
                            dir_name = sub_dir.name.lower()
                            
                            # 根据cam_name匹配对应的目录
                            if (("left" in cam_name.lower() and "left" in dir_name) or 
                                ("right" in cam_name.lower() and "right" in dir_name)):
                                
                                # 在匹配的目录中查找mp4文件
                                for video_file in sub_dir.glob("*.mp4"):
                                    video_file_name = video_file.name
                                    target_file = target_cam_dir / video_file_name
                                    shutil.copy2(video_file, target_file)
                                    if self.logger:
                                        self.logger.info(f"Copied video: {video_file} -> {target_file}")
                                    found_videos = True
                                
                                # 也检查其他常见视频格式
                                for ext in ["*.avi", "*.mov", "*.mkv"]:
                                    for video_file in sub_dir.glob(ext):
                                        video_file_name = video_file.name
                                        target_file = target_cam_dir / video_file_name
                                        shutil.copy2(video_file, target_file)
                                        if self.logger:
                                            self.logger.info(f"Copied video: {video_file} -> {target_file}")
                                        found_videos = True
            
            # 如果没有找到left/right文件夹，尝试直接查找
            if not found_videos:
                # 支持多种视频格式的直接匹配
                video_patterns = [
                    str(src_videos_path / f"**/{cam_name}*.mp4"),
                    str(src_videos_path / f"**/{cam_name}*.avi"),
                    str(src_videos_path / f"**/{cam_name}*.mov"),
                    str(src_videos_path / f"**/{cam_name}*.mkv"),
                ]
                video_files = []
                for pattern in video_patterns:
                    video_files.extend(glob.glob(pattern, recursive=True))
                
                for video_file in video_files:
                    video_file_name = os.path.basename(video_file)
                    target_file = target_cam_dir / video_file_name
                    shutil.copy2(video_file, target_file)
                    if self.logger:
                        self.logger.info(f"Copied video: {video_file} -> {target_file}")
                    found_videos = True
            
            if not found_videos and self.logger:
                self.logger.warning(f"No videos found for camera {cam_name}")
        
        if self.logger:
            self.logger.info(f"All videos copied to {target_videos_path} by cam_name from config.")

    def _convert_units(self, data: np.ndarray, data_type: str, unit_config: dict = None) -> np.ndarray:
        """
        Convert data units to our standard if needed:
        - All angles in radians
        - All distances in meters
        """
        converted_data = data.copy().astype(np.float32)
        
        # If unit_config is provided, use it for conversion
        if unit_config and 'source_units' in unit_config and 'target_units' in unit_config:
            source_units = unit_config['source_units']
            target_units = unit_config['target_units']
            
            if len(source_units) != len(converted_data) or len(target_units) != len(converted_data):
                if self.logger:
                    self.logger.warning(f"Unit config length mismatch: data={len(converted_data)}, source={len(source_units)}, target={len(target_units)}")
                return converted_data
            
            # Apply unit conversions element by element
            for i, (src_unit, tgt_unit) in enumerate(zip(source_units, target_units)):
                converted_data[i] = self._convert_single_unit(converted_data[i], src_unit, tgt_unit)
                
            if self.logger:
                self.logger.debug(f"Applied unit conversion for {data_type}: {source_units} -> {target_units}")
            
            return converted_data
        
        # Generic unit conversion logic (fallback)
        # Specific conversions can be added based on data_type
        if data_type in ["joint_position", "joint_effort", "joint_velocity"]:
            # Assume joint data is already in standard units (radians, etc.)
            pass
        elif data_type in ["end_position", "translation"]:
            # Assume position data is already in meters
            pass
        elif data_type == "orientation":
            # Assume quaternions are already normalized
            pass
        
        return converted_data
    
    def _convert_single_unit(self, value: float, source_unit: str, target_unit: str) -> float:
        """Convert a single value from source unit to target unit"""
        if source_unit == target_unit:
            return value
        
        # Distance conversions
        if source_unit == "mm" and target_unit == "m":
            return value / 1000.0
        
        if source_unit == "cm" and target_unit == "m":
            return value / 100.0
        
        if source_unit == "m" and target_unit == "mm":
            return value * 1000.0
        
        if source_unit == "m" and target_unit == "cm":
            return value * 100.0
        
        # Angle conversions
        if source_unit == "deg" and target_unit == "rad":
            return np.deg2rad(value)
        
        if source_unit == "rad" and target_unit == "deg":
            return np.rad2deg(value)
        
        # Velocity conversions
        if source_unit == "mm/s" and target_unit == "m/s":
            return value / 1000.0
        
        if source_unit == "m/s" and target_unit == "mm/s":
            return value * 1000.0
        
        # Force conversions
        if source_unit == "N" and target_unit == "N":
            return value
        
        if source_unit == "kN" and target_unit == "N":
            return value * 1000.0
        
        if source_unit == "N" and target_unit == "kN":
            return value / 1000.0
        
        # If no conversion is found, log warning and return original value
        if self.logger:
            self.logger.warning(f"Unknown unit conversion: {source_unit} -> {target_unit}, returning original value")
        
        return value

    def _get_unit_config_for_current_sub_state(self, args_dict: dict, data_type: str) -> dict:
        """Get unit config for current sub_state from converter config"""
        try:
            # Find the matching sub_state config based on args_dict
            sub_state_configs = self.converter_config.get('features', {}).get('observation', {}).get('state', {}).get('sub_state', [])
            
            for sub_state_config in sub_state_configs:
                config_args = sub_state_config.get('args', {})
                # Match based on json_path or other identifying fields
                if self._args_match(args_dict, config_args):
                    return sub_state_config.get('unit_config', {})
            
            return {}
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to get unit config for {data_type}: {e}")
            return {}

    def _get_unit_config_for_current_sub_action(self, args_dict: dict, data_type: str) -> dict:
        """Get unit config for current sub_action from converter config"""
        try:
            # Find the matching sub_action config based on args_dict
            sub_action_configs = self.converter_config.get('features', {}).get('action', {}).get('sub_action', [])
            
            for sub_action_config in sub_action_configs:
                config_args = sub_action_config.get('args', {})
                # Match based on json_path or other identifying fields
                if self._args_match(args_dict, config_args):
                    return sub_action_config.get('unit_config', {})
            
            return {}
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to get unit config for {data_type}: {e}")
            return {}

    def _args_match(self, args_dict1: dict, args_dict2: dict) -> bool:
        """Check if two args dictionaries match for the purpose of finding unit config"""
        # Match based on json_path as primary identifier
        if 'json_path' in args_dict1 and 'json_path' in args_dict2:
            return args_dict1['json_path'] == args_dict2['json_path']
        
        # If no json_path, check if they have the same keys and values
        return args_dict1 == args_dict2

    def _load_episode_data(self, ep_idx: int) -> pd.DataFrame:
        """Load parquet data for a specific episode"""
        if ep_idx >= len(self.parquet_files):
            raise ValueError(f"Episode {ep_idx} not found. Available: {len(self.parquet_files)}")
        
        parquet_file = self.parquet_files[ep_idx]
        df = pd.read_parquet(parquet_file)
        
        if self.logger:
            self.logger.debug(f"Loaded episode {ep_idx} with {len(df)} frames from {parquet_file}")
        
        return df

    # Abstract method implementations for base class compatibility
    def _get_frame_image(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        images_buffer: any = None,
    ) -> np.ndarray:
        """
        For LeRobot format conversion, we typically don't process individual frame images
        since videos are handled by moving files
        """
        # Return dummy image data - this won't be used in our conversion process
        return np.zeros((480, 848, 3), dtype=np.uint8)

    def _get_frame_sub_states(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        sub_states_buffer: any = None,
    ) -> np.ndarray:
        """Extract state data for a specific frame"""
        df = sub_states_buffer if sub_states_buffer is not None else self._load_episode_data(ep_idx)
        
        if frame_idx >= len(df):
            raise ValueError(f"Frame {frame_idx} not found in episode {ep_idx}")
        
        # Extract the requested state data based on args_dict
        field_name = args_dict.get("field_name", "observation.state")
        
        if field_name not in df.columns:
            raise ValueError(f"Field {field_name} not found in data")
        
        frame_data = df.iloc[frame_idx][field_name]
        
        # Convert to numpy array and apply unit conversion
        data = np.array(frame_data, dtype=np.float32)
        
        # Get unit config from parent state config if available
        unit_config = self._get_unit_config_for_current_sub_state(args_dict, "state")
        
        return self._convert_units(data, "state", unit_config)

    def _get_frame_sub_actions(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        sub_actions_buffer: any = None,
    ) -> np.ndarray:
        """Extract action data for a specific frame"""
        df = sub_actions_buffer if sub_actions_buffer is not None else self._load_episode_data(ep_idx)
        
        if frame_idx >= len(df):
            raise ValueError(f"Frame {frame_idx} not found in episode {ep_idx}")
        
        # Extract the requested action data based on args_dict
        field_name = args_dict.get("field_name", "action")
        
        if field_name not in df.columns:
            raise ValueError(f"Field {field_name} not found in data")
        
        frame_data = df.iloc[frame_idx][field_name]
        
        # Convert to numpy array and apply unit conversion
        data = np.array(frame_data, dtype=np.float32)
        
        # Get unit config from parent action config if available
        unit_config = self._get_unit_config_for_current_sub_action(args_dict, "action")
        
        return self._convert_units(data, "action", unit_config)

    def _get_episode_frames_num(self, task_path: Path, ep_idx: int) -> int:
        """Get number of frames in an episode"""
        df = self._load_episode_data(ep_idx)
        return len(df)

    def _get_task_episodes_num(self, task_path: Path) -> int:
        """Get number of episodes in a task"""
        return len(self.parquet_files)

    def _prepare_episode_states_buffer(self, task_path: Path, ep_idx: int) -> pd.DataFrame:
        """Prepare states buffer by loading the episode data"""
        return self._load_episode_data(ep_idx)

    def _prepare_episode_actions_buffer(self, task_path: Path, ep_idx: int) -> pd.DataFrame:
        """Prepare actions buffer by loading the episode data"""
        return self._load_episode_data(ep_idx)



    def _get_episode_task(self, ep_idx: int) -> str:
        """Get task name for an episode"""
        if ep_idx < len(self.episodes):
            # Try to get task from episode metadata
            episode_info = self.episodes[ep_idx]
            return episode_info.get("task", f"episode_{ep_idx:06d}")
        
        return f"episode_{ep_idx:06d}"

