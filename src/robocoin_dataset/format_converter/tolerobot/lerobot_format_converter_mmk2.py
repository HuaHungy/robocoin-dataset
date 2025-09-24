import logging
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from natsort import natsorted
from PIL import Image

from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import (
    LerobotFormatConverter,
)


@dataclass
class Mmk2Buffer:
    """MMK2数据缓冲区"""

    main_bson_data: dict[str, list[dict]] = None
    hand_bson_data: list[dict] = None
    camera_groups: dict[str, list[Path]] = None
    task_path: Path = None
    ep_idx: int = None


def parse_bson_document(data: bytes, offset: int = 0) -> tuple[dict, int]:
    """解析单个BSON文档"""
    if offset + 4 > len(data):
        return None, offset

    # 读取文档大小
    doc_size = struct.unpack("<I", data[offset : offset + 4])[0]
    if offset + doc_size > len(data):
        return None, offset

    doc_data = data[offset : offset + doc_size]
    result = {}

    pos = 4  # 跳过文档大小

    while pos < len(doc_data) - 1:  # 最后一个字节是结束符0x00
        if pos >= len(doc_data):
            break

        # 读取字段类型
        field_type = doc_data[pos]
        pos += 1

        # 读取字段名
        name_end = doc_data.find(b"\x00", pos)
        if name_end == -1:
            break
        field_name = doc_data[pos:name_end].decode("utf-8", errors="ignore")
        pos = name_end + 1

        # 根据类型解析值
        if field_type == 0x01:  # double
            if pos + 8 <= len(doc_data):
                value = struct.unpack("<d", doc_data[pos : pos + 8])[0]
                pos += 8
                result[field_name] = value
        elif field_type == 0x02:  # string
            if pos + 4 <= len(doc_data):
                str_len = struct.unpack("<I", doc_data[pos : pos + 4])[0]
                pos += 4
                if pos + str_len <= len(doc_data):
                    value = doc_data[pos : pos + str_len - 1].decode("utf-8", errors="ignore")
                    pos += str_len
                    result[field_name] = value
        elif field_type == 0x03:  # document
            if pos + 4 <= len(doc_data):
                subdoc_size = struct.unpack("<I", doc_data[pos : pos + 4])[0]
                if pos + subdoc_size <= len(doc_data):
                    subdoc, _ = parse_bson_document(doc_data, pos)
                    if subdoc is not None:
                        result[field_name] = subdoc
                    pos += subdoc_size
        elif field_type == 0x04:  # array
            if pos + 4 <= len(doc_data):
                array_size = struct.unpack("<I", doc_data[pos : pos + 4])[0]
                if pos + array_size <= len(doc_data):
                    array_doc, _ = parse_bson_document(doc_data, pos)
                    if array_doc is not None:
                        # 将字典转换为列表（BSON数组以索引为键）
                        array_list = []
                        for i in range(len(array_doc)):
                            if str(i) in array_doc:
                                array_list.append(array_doc[str(i)])  # noqa: PERF401
                        result[field_name] = array_list
                    pos += array_size
        elif field_type == 0x08:  # boolean
            if pos + 1 <= len(doc_data):
                value = doc_data[pos] != 0
                pos += 1
                result[field_name] = value
        elif field_type == 0x10:  # int32
            if pos + 4 <= len(doc_data):
                value = struct.unpack("<i", doc_data[pos : pos + 4])[0]
                pos += 4
                result[field_name] = value
        elif field_type == 0x12:  # int64
            if pos + 8 <= len(doc_data):
                value = struct.unpack("<q", doc_data[pos : pos + 8])[0]
                pos += 8
                result[field_name] = value
        else:
            # 未知类型，跳过
            break

    return result, offset + doc_size


class LerobotFormatConverterMmk2(LerobotFormatConverter):
    """MMK2机器人转换器 - JPG+BSON格式"""

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
        self.mmk2_buffer: Mmk2Buffer = Mmk2Buffer()
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

    def _get_structure_summary(self, data: any, max_depth: int = 2, current_depth: int = 0) -> any:
        """获取数据结构的简要总结，用于调试"""
        if current_depth >= max_depth:
            return f"... (max depth {max_depth} reached)"
        
        if isinstance(data, dict):
            if not data:
                return "{}"
            keys = list(data.keys())[:5]  # 只显示前5个键
            summary = {key: self._get_structure_summary(data[key], max_depth, current_depth + 1) for key in keys}
            if len(data) > 5:
                summary["..."] = f"({len(data) - 5} more keys)"
            return summary
        
        if isinstance(data, list):
            if not data:
                return "[]"
            length = len(data)
            if length > 0:
                sample = self._get_structure_summary(data[0], max_depth, current_depth + 1)
                return f"[{sample}, ...] (length: {length})"
            return "[]"
        
        return f"{type(data).__name__}"

    def _prevalidate_files(self) -> None:
        """Validate MMK2 dataset files and structure."""
        for task_path in self.path_task_dict.keys():
            if not task_path.exists():
                raise FileNotFoundError(f"Task path does not exist: {task_path}")
            if not task_path.is_dir():
                raise ValueError(f"Task path is not a directory: {task_path}")
            
            # Check for required episode directories
            episode_dirs = [d for d in task_path.iterdir() if d.is_dir() and d.name.startswith('episode_')]
            if not episode_dirs:
                self.logger.warning(f"No episode directories found in {task_path}")
            else:
                # Enhanced validation: validate each episode's internal structure
                for i, episode_dir in enumerate(episode_dirs):
                    self._validate_mmk2_episode_structure(episode_dir, i)
            
            # Validate each episode directory structure
            for episode_dir in episode_dirs:
                # Check for required subdirectories (observations, actions, etc.)
                required_subdirs = ['observations']
                for subdir in required_subdirs:
                    subdir_path = episode_dir / subdir
                    if not subdir_path.exists():
                        self.logger.warning(f"Missing required subdirectory: {subdir_path}")
                
                # Check for image files in observations
                obs_dir = episode_dir / 'observations'
                if obs_dir.exists():
                    image_files = list(obs_dir.glob("*.jpg")) + list(obs_dir.glob("*.png")) + list(obs_dir.glob("*.jpeg"))
                    if not image_files:
                        self.logger.warning(f"No image files found in {obs_dir}")

    def _validate_mmk2_episode_structure(self, episode_dir: Path, ep_idx: int) -> None:
        """Validate internal MMK2 episode structure against configuration"""
        try:
            if self.logger:
                self.logger.info(f"Validating MMK2 episode structure: {episode_dir}")
            
            # Validate BSON files structure
            main_bson_file = episode_dir / "episode_0.bson"
            hand_bson_file = episode_dir / "xhand_control_data.bson"

            # Check required BSON files exist
            if not main_bson_file.exists():
                if self.logger:
                    self.logger.warning(f"Missing main BSON file: {main_bson_file}")
                return
            
            if not hand_bson_file.exists():
                if self.logger:
                    self.logger.warning(f"Missing hand BSON file: {hand_bson_file}")
            
            # Validate main BSON structure
            self._validate_main_bson_structure(main_bson_file)
            
            # Validate hand BSON structure
            if hand_bson_file.exists():
                self._validate_hand_bson_structure(hand_bson_file)
            
            # Validate camera directories
            self._validate_camera_structure(episode_dir)
            
            if self.logger:
                self.logger.info(f"MMK2 episode structure validation completed for {episode_dir}")
        
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error validating MMK2 episode structure: {e}")
    
    def _validate_main_bson_structure(self, bson_file: Path) -> None:
        """Validate main BSON file structure against configuration"""
        try:
            with open(bson_file, "rb") as f:
                content = f.read()
            
            doc, _ = parse_bson_document(content, 0)
            if not doc or "data" not in doc:
                if self.logger:
                    self.logger.warning(f"Invalid main BSON structure in {bson_file}")
                return
            
            available_paths = set(doc["data"].keys())
            if self.logger:
                self.logger.info(f"Available main BSON paths: {sorted(available_paths)}")
            
            # Get expected paths from configuration
            expected_paths = set()
            if hasattr(self, 'converter_config') and self.converter_config:
                # Check state configuration
                state_config = self.converter_config.get('features', {}).get('observation', {}).get('state', {})
                if 'sub_state' in state_config:
                    for sub_state in state_config['sub_state']:
                        if 'args' in sub_state and sub_state['args'].get('bson_file') == 'episode_0.bson':
                            data_path = sub_state['args'].get('data_path', '').lstrip('/')
                            expected_paths.add(data_path)
                
                # Check action configuration
                action_config = self.converter_config.get('features', {}).get('action', {})
                if 'sub_action' in action_config:
                    for sub_action in action_config['sub_action']:
                        if 'args' in sub_action and sub_action['args'].get('bson_file') == 'episode_0.bson':
                            data_path = sub_action['args'].get('data_path', '').lstrip('/')
                            expected_paths.add(data_path)
            
            # Validate expected paths exist
            missing_paths = expected_paths - available_paths
            if missing_paths:
                if self.logger:
                    self.logger.warning(f"Missing main BSON paths: {sorted(missing_paths)}")
            
            found_paths = expected_paths & available_paths
            if self.logger:
                self.logger.info(f"Validated main BSON paths ({len(found_paths)}): {sorted(found_paths)}")
        
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error validating main BSON structure: {e}")
    
    def _validate_hand_bson_structure(self, bson_file: Path) -> None:
        """Validate hand BSON file structure against configuration"""
        try:
            with open(bson_file, "rb") as f:
                content = f.read()
            
            doc, _ = parse_bson_document(content, 0)
            if not doc or "frames" not in doc:
                if self.logger:
                    self.logger.warning(f"Invalid hand BSON structure in {bson_file}")
                return
            
            frames = doc["frames"]
            if not frames:
                if self.logger:
                    self.logger.warning(f"No frames found in hand BSON: {bson_file}")
                return
            
            # Check first frame structure
            first_frame = frames[0]
            available_paths = set()
            
            # Extract available observation paths
            if "observation" in first_frame:
                obs_data = first_frame["observation"]
                if "left_hand" in obs_data:
                    available_paths.add("observation.left_hand")
                if "right_hand" in obs_data:
                    available_paths.add("observation.right_hand")
            
            if self.logger:
                self.logger.info(f"Available hand BSON paths: {sorted(available_paths)}")
            
            # Get expected paths from configuration
            expected_paths = set()
            if hasattr(self, 'converter_config') and self.converter_config:
                # Check state configuration for hand data
                state_config = self.converter_config.get('features', {}).get('observation', {}).get('state', {})
                if 'sub_state' in state_config:
                    for sub_state in state_config['sub_state']:
                        if 'args' in sub_state and sub_state['args'].get('bson_file') == 'xhand_control_data.bson':
                            data_path = sub_state['args'].get('data_path', '')
                            expected_paths.add(data_path)
                
                # Check action configuration for hand data
                action_config = self.converter_config.get('features', {}).get('action', {})
                if 'sub_action' in action_config:
                    for sub_action in action_config['sub_action']:
                        if 'args' in sub_action and sub_action['args'].get('bson_file') == 'xhand_control_data.bson':
                            data_path = sub_action['args'].get('data_path', '')
                            expected_paths.add(data_path)
            
            # Validate expected paths exist
            missing_paths = expected_paths - available_paths
            if missing_paths:
                if self.logger:
                    self.logger.warning(f"Missing hand BSON paths: {sorted(missing_paths)}")
            
            found_paths = expected_paths & available_paths
            if self.logger:
                self.logger.info(f"Validated hand BSON paths ({len(found_paths)}): {sorted(found_paths)}")
                self.logger.info(f"Hand BSON contains {len(frames)} frames")
        
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error validating hand BSON structure: {e}")
    
    def _validate_camera_structure(self, episode_dir: Path) -> None:
        """Validate camera directory structure against configuration"""
        try:
            # Get expected cameras from configuration
            expected_cameras = set()
            if hasattr(self, 'converter_config') and self.converter_config:
                images_config = self.converter_config.get('features', {}).get('observation', {}).get('images', [])
                for image_config in images_config:
                    if 'args' in image_config and 'camera_dir' in image_config['args']:
                        camera_dir = image_config['args']['camera_dir']
                        expected_cameras.add(camera_dir)
            
            # Check available cameras - 动态发现所有camera目录
            available_cameras = set()
            for camera_path in episode_dir.iterdir():
                if camera_path.is_dir() and camera_path.name.startswith("camera"):
                    available_cameras.add(camera_path.name)
                    # Count images
                    jpg_files = list(camera_path.glob("*.jpg"))
                    if self.logger:
                        self.logger.info(f"Camera {camera_path.name}: {len(jpg_files)} images")
            
            if self.logger:
                self.logger.info(f"Available cameras: {sorted(available_cameras)}")
            
            # Validate expected cameras exist
            missing_cameras = expected_cameras - available_cameras
            if missing_cameras:
                if self.logger:
                    self.logger.warning(f"Missing camera directories: {sorted(missing_cameras)}")
            
            found_cameras = expected_cameras & available_cameras
            if self.logger:
                self.logger.info(f"Validated cameras ({len(found_cameras)}): {sorted(found_cameras)}")
        
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error validating camera structure: {e}")

    # @override
    def _get_frame_image(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        images_buffer: any = None,
    ) -> np.ndarray:
        if not images_buffer:
            images_buffer = self._prepare_episode_images_buffer(task_path, ep_idx)

        camera_dir = args_dict["camera_dir"]

        if "camera_groups" not in images_buffer:
            raise ValueError("camera_groups not found in images_buffer")

        # Add available_cameras info to buffer if not present
        if "available_cameras" not in images_buffer:
            images_buffer["available_cameras"] = set(images_buffer["camera_groups"].keys())

        available_cameras = images_buffer["available_cameras"]
        if camera_dir not in available_cameras:
            error_msg = f"Camera {camera_dir} not found. Available cameras: {sorted(available_cameras)}"
            
            if self.logger:
                self.logger.error(error_msg)
                self.logger.info("Please check your configuration file to ensure camera_dir matches available cameras")
                self.logger.info("Or consider using a different camera configuration version")
                
                # 针对常见的相机配置提供建议
                if available_cameras == {"camera_0", "camera_2"}:
                    self.logger.info("Detected camera_0 and camera_2 only. Consider using 'twocam_version' configuration.")
                elif len(available_cameras) == 4:
                    self.logger.info(f"Detected 4 cameras: {sorted(available_cameras)}. Consider creating a custom configuration for this setup.")
                elif "camera_head" in available_cameras:
                    self.logger.info("Detected named cameras (e.g., camera_head). Consider using apple_storage configuration.")
            
            # 提供更详细的错误信息以便调试
            raise ValueError(
                f"{error_msg}. "
                f"This usually indicates a mismatch between the configuration file and actual dataset structure. "
                f"Please update the converter configuration to use available cameras: {sorted(available_cameras)}"
            )

        camera_files = images_buffer["camera_groups"][camera_dir]

        # 处理稀疏图像：如果请求的帧索引超出范围，使用最后一个可用的图像
        if frame_idx >= len(camera_files):
            if len(camera_files) == 0:
                raise ValueError(f"No images available for camera {camera_dir}")

            # 使用最后一个可用的图像
            self.logger.warning(
                f"Frame index {frame_idx} out of range for camera {camera_dir}. Available frames: {len(camera_files)}. Using last available frame."
            )
            image_path = camera_files[-1]
        else:
            image_path = camera_files[frame_idx]

        if not image_path.exists():
            raise ValueError(f"Image file not found: {image_path}")

        # 读取并返回图像
        img = Image.open(image_path)
        return np.array(img)

    # @override
    def _get_frame_sub_states(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        sub_states_buffer: any = None,
    ) -> np.ndarray:
        if not sub_states_buffer:
            sub_states_buffer = self._prepare_episode_states_buffer(task_path, ep_idx)

        bson_file = args_dict["bson_file"]
        data_path = args_dict["data_path"]
        range_from = args_dict["range_from"]
        range_to = args_dict["range_to"]

        # 根据不同的BSON文件处理数据
        if bson_file == "episode_0.bson":
            # 主要关节数据
            field = args_dict.get("field", "pos")  # 默认使用pos字段

            # 规范化路径格式 - 确保路径以 / 开头
            normalized_data_path = data_path if data_path.startswith('/') else f'/{data_path}'

            # 检查路径是否为可选路径（如末端执行器数据可能不存在）
            is_optional_path = any(optional in data_path.lower() for optional in ['_eef', 'end_effector'])

            if self.logger:
                self.logger.debug(f"Checking path: '{data_path}', normalized: '{normalized_data_path}', is_optional: {is_optional_path}")

            if normalized_data_path not in sub_states_buffer["main_data"]:
                available_paths = list(sub_states_buffer["main_data"].keys())
                # 尝试找到相似的路径
                similar_paths = [
                    path for path in available_paths
                    if any(part.lower() in path.lower() for part in data_path.split("/"))
                ]
                
                error_msg = (
                    f"Data path '{data_path}' (normalized: '{normalized_data_path}') not found in main BSON data for frame {frame_idx}. "
                    f"Available paths: {available_paths}. "
                )
                
                if similar_paths:
                    error_msg += f"Similar paths found: {similar_paths}. "

                # 对于可选路径，返回零值而不是抛出错误
                if is_optional_path:
                    if self.logger:
                        self.logger.warning(
                            f"Optional path '{data_path}' not found. Using zero values. "
                            f"Available paths: {available_paths}"
                        )
                    # 返回指定范围大小的零数组
                    return np.zeros(range_to - range_from, dtype=np.float32)
                
                if self.logger:
                    self.logger.error(error_msg)
                
                raise ValueError(error_msg)

            data_list = sub_states_buffer["main_data"][normalized_data_path]

            if frame_idx >= len(data_list):
                raise ValueError(
                    f"Frame index {frame_idx} out of range for path '{normalized_data_path}'. "
                    f"Available frames: {len(data_list)}, BSON file: '{bson_file}'"
                )

            frame_data = data_list[frame_idx]
            if "data" not in frame_data or field not in frame_data["data"]:
                available_data_keys = list(frame_data.keys()) if isinstance(frame_data, dict) else "Not a dict"
                available_field_keys = list(frame_data.get("data", {}).keys()) if isinstance(frame_data.get("data"), dict) else "No data field or not a dict"
                
                error_msg = (
                    f"Field '{field}' not found in frame {frame_idx} for path '{data_path}'. "
                    f"Available top-level keys: {available_data_keys}. "
                    f"Available field keys in 'data': {available_field_keys}. "
                    f"BSON file: '{bson_file}'"
                )
                
                if self.logger:
                    self.logger.error(error_msg)
                
                raise ValueError(error_msg)

            values = frame_data["data"][field]
            if range_to > len(values):
                if self.logger:
                    self.logger.warning(
                        f"Requested range [{range_from}:{range_to}] exceeds data length {len(values)} "
                        f"for path '{data_path}', field '{field}' in frame {frame_idx}"
                    )
            return np.array(values[range_from:range_to], dtype=np.float32)

        if bson_file == "xhand_control_data.bson":
            # 手部数据
            hand_data = sub_states_buffer["hand_data"]

            if frame_idx >= len(hand_data):
                raise ValueError(
                    f"Frame index {frame_idx} out of range for hand data. Available: {len(hand_data)}"
                )

            frame_data = hand_data[frame_idx]

            # 解析data_path，例如: "observation.left_hand"
            path_parts = data_path.split(".")
            data = frame_data
            current_path = ""
            for i, part in enumerate(path_parts):
                current_path = ".".join(path_parts[:i+1])
                if isinstance(data, dict) and part in data:
                    data = data[part]
                else:
                    # 提供详细的调试信息
                    available_keys = list(data.keys()) if isinstance(data, dict) else f"Not a dict, type: {type(data)}"
                    
                    # 尝试找到相似的键
                    similar_keys = []
                    if isinstance(data, dict):
                        similar_keys = [
                            key for key in data.keys()
                            if part.lower() in key.lower() or key.lower() in part.lower()
                        ]
                    
                    error_msg = (
                        f"Path '{data_path}' not found in hand data at step '{current_path}' "
                        f"for BSON file '{bson_file}', frame {frame_idx}. "
                        f"Available keys at current level: {available_keys}. "
                        f"Target path part: '{part}'. "
                    )
                    
                    if similar_keys:
                        error_msg += f"Similar keys found: {similar_keys}. "
                    
                    # 记录第一个可用帧的结构作为参考
                    if frame_idx > 0 and frame_idx < len(hand_data):
                        try:
                            first_frame = hand_data[0]
                            error_msg += f"Structure of frame 0 for reference: {self._get_structure_summary(first_frame)}. "
                        except Exception:
                            pass
                    
                    if self.logger:
                        self.logger.error(error_msg)
                    
                    raise ValueError(error_msg)

            if isinstance(data, list):
                if range_to > len(data):
                    if self.logger:
                        self.logger.warning(
                            f"Requested range [{range_from}:{range_to}] exceeds data length {len(data)} "
                            f"for path '{data_path}' in frame {frame_idx}, BSON file '{bson_file}'"
                        )
                return np.array(data[range_from:range_to], dtype=np.float32)
            
            raise ValueError(
                f"Expected list data for path '{data_path}', got {type(data)} with value: {data} "
                f"in frame {frame_idx}, BSON file '{bson_file}'"
            )

        raise ValueError(f"Unknown BSON file: {bson_file}")

    # @override
    def _get_frame_sub_actions(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        sub_actions_buffer: any = None,
    ) -> np.ndarray:
        if not sub_actions_buffer:
            sub_actions_buffer = self._prepare_episode_actions_buffer(task_path, ep_idx)

        # 动作数据处理逻辑与状态数据类似
        return self._get_frame_sub_states(
            task_path, ep_idx, frame_idx, args_dict, sub_actions_buffer
        )

    # @override
    def _get_episode_frames_num(self, task_path: Path, ep_idx: int) -> int:
        """获取episode的帧数 - 使用主BSON文件的帧数"""
        episode_dir = self._get_episode_directory(task_path, ep_idx)
        main_bson_file = episode_dir / "episode_0.bson"

        if not main_bson_file.exists():
            raise ValueError(f"Main BSON file not found: {main_bson_file}")

        try:
            with open(main_bson_file, "rb") as f:
                content = f.read()

            doc, _ = parse_bson_document(content, 0)
            if doc and "data" in doc:
                # 获取任一数据路径的长度作为帧数
                for value in doc["data"].values():
                    if isinstance(value, list):
                        return len(value)

            return 0
        except Exception as e:
            raise ValueError(f"Error reading main BSON file: {e}")

    # @override
    def _get_task_episodes_num(self, task_path: Path) -> int:
        """获取任务的episode数量"""
        episode_dirs = [
            d for d in task_path.iterdir() if d.is_dir() and d.name.startswith("episode")
        ]
        return len(episode_dirs)

    # @override
    def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int) -> any:
        """准备图像缓冲区"""
        episode_dir = self._get_episode_directory(task_path, ep_idx)

        camera_groups = {}
        # 动态发现所有相机目录
        for camera_path in episode_dir.iterdir():
            if camera_path.is_dir() and camera_path.name.startswith("camera"):
                jpg_files = natsorted(list(camera_path.glob("*.jpg")))
                if jpg_files:  # 只添加有图像文件的相机目录
                    camera_groups[camera_path.name] = jpg_files

        # Add available cameras metadata for validation
        available_cameras = set(camera_groups.keys())
        
        return {
            "camera_groups": camera_groups,
            "available_cameras": available_cameras
        }

    # @override
    def _prepare_episode_states_buffer(self, task_path: Path, ep_idx: int) -> any:
        """准备状态数据缓冲区"""
        episode_dir = self._get_episode_directory(task_path, ep_idx)

        # 读取主BSON文件
        main_bson_file = episode_dir / "episode_0.bson"
        main_data = {}
        if main_bson_file.exists():
            with open(main_bson_file, "rb") as f:
                content = f.read()
            doc, _ = parse_bson_document(content, 0)
            if doc and "data" in doc:
                main_data = doc["data"]

        # 读取手部BSON文件
        hand_bson_file = episode_dir / "xhand_control_data.bson"
        hand_data = []
        if hand_bson_file.exists():
            with open(hand_bson_file, "rb") as f:
                content = f.read()
            doc, _ = parse_bson_document(content, 0)
            if doc and "frames" in doc:
                hand_data = doc["frames"]

        return {"main_data": main_data, "hand_data": hand_data}

    # @override
    def _prepare_episode_actions_buffer(self, task_path: Path, ep_idx: int) -> any:
        """准备动作数据缓冲区 - 与状态数据共用"""
        return self._prepare_episode_states_buffer(task_path, ep_idx)

    def _get_episode_directory(self, task_path: Path, ep_idx: int) -> Path:
        """获取episode目录"""
        episode_dirs = sorted(
            [d for d in task_path.iterdir() if d.is_dir() and d.name.startswith("episode")]
        )
        if ep_idx >= len(episode_dirs):
            raise ValueError(f"Episode index {ep_idx} out of range. Available: {len(episode_dirs)}")
        return episode_dirs[ep_idx]
