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
        
        Returns:
            dict mapping episode directory paths to task names
        """
        import yaml
        
        task_paths_dict = {}
        
        # Read task info from dataset root
        local_task_info_path = self.dataset_path / "local_task_info.yaml"
        if not local_task_info_path.exists():
            raise FileNotFoundError(f"local_task_info.yaml not found in {self.dataset_path}")
        
        with open(local_task_info_path) as f:
            task_info_dict = yaml.safe_load(f)
            task_index = task_info_dict["task_index"]
            task = self.tasks[task_index]
        
        # Scan for episode directories
        for subdir in self.dataset_path.iterdir():
            if subdir.is_dir():
                metadata_file = subdir / "metadata.json"
                h5_file = subdir / "proprio_stats" / "proprio_stats.hdf5"
                
                if metadata_file.exists() and h5_file.exists():
                    task_paths_dict[subdir] = task
                    self.logger.info(f"Found episode: {subdir.name}")
        
        if not task_paths_dict:
            raise FileNotFoundError(
                f"No valid episode directories found in {self.dataset_path}"
            )
        
        return task_paths_dict

    def _prevalidate_files(self) -> None:
        """Validate that required files exist for each episode."""
        for episode_path in self.path_task_dict.keys():
            # Check metadata
            metadata_file = episode_path / "metadata.json"
            if not metadata_file.exists():
                raise FileNotFoundError(f"metadata.json not found in {episode_path}")
            
            # Check H5 file
            h5_file = episode_path / "proprio_stats" / "proprio_stats.hdf5"
            if not h5_file.exists():
                raise FileNotFoundError(f"proprio_stats.hdf5 not found in {episode_path}")
            
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
            raise FileNotFoundError(f"Video file not found: {video_path}")
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
                    states_buffer[h5_path] = np.array(f[h5_path])
        
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
                    # Special handling for joint velocity in actions (use state velocity)
                    if h5_path == "state/joint/velocity":
                        actions_buffer[h5_path] = np.array(f[h5_path])
                    else:
                        actions_buffer[h5_path] = np.array(f[h5_path])
        
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
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            raise ValueError(f"Failed to read frame {frame_idx} from {video_path}")
        
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
