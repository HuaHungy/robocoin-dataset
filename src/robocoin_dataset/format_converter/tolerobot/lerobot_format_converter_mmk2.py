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


class BsonFileCache:
    """BSON文件缓存器 - 避免重复解析同一文件
    
    性能优化：类似H5FileCache，复用已解析的BSON数据
    - 避免重复读取文件
    - 避免重复解析BSON
    - 显著提升速度（特别是在多次访问同一episode时）
    """
    
    def __init__(self, max_cache_size: int = 10):
        """初始化BSON缓存
        
        Args:
            max_cache_size: 最大缓存文件数（默认10个episode）
        """
        self._cache = {}  # {file_path: parsed_data}
        self._max_size = max_cache_size
        self._access_order = []  # LRU tracking
    
    def get(self, bson_file: Path) -> dict:
        """获取BSON文件的解析数据（带缓存）
        
        Args:
            bson_file: BSON文件路径
            
        Returns:
            解析后的BSON数据字典
        """
        cache_key = str(bson_file)
        
        # 缓存命中
        if cache_key in self._cache:
            # 更新访问顺序（LRU）
            self._access_order.remove(cache_key)
            self._access_order.append(cache_key)
            return self._cache[cache_key]
        
        # 缓存未命中 - 读取并解析
        with open(bson_file, "rb") as f:
            content = f.read()
        
        parsed_data, _ = parse_bson_document(content, 0)
        
        # 添加到缓存
        self._cache[cache_key] = parsed_data
        self._access_order.append(cache_key)
        
        # 检查缓存大小，移除最旧的
        if len(self._cache) > self._max_size:
            oldest_key = self._access_order.pop(0)
            del self._cache[oldest_key]
        
        return parsed_data
    
    def clear(self):
        """清空缓存"""
        self._cache.clear()
        self._access_order.clear()


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
        
        # 🚀 性能优化：初始化BSON文件缓存
        self._bson_cache = BsonFileCache(max_cache_size=10)
        
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
                parent_dir = task_path.parent
                sibling_dirs = [d.name for d in parent_dir.iterdir() if d.is_dir()] if parent_dir.exists() else []
                raise FileNotFoundError(
                    f"❌ MMK2任务路径不存在\n"
                    f"📁 请求的路径：{task_path}\n"
                    f"📂 父目录：{parent_dir}\n"
                    f"🗂️ 父目录中的子目录：\n" +
                    "\n".join(f"   - {d}" for d in sorted(sibling_dirs)[:10]) +
                    (f"\n   ... 还有 {len(sibling_dirs) - 10} 个目录" if len(sibling_dirs) > 10 else "") +
                    "\n💡 请检查：\n"
                    "   1. 路径是否拼写正确\n"
                    "   2. 目录是否已被移动或删除\n"
                    "   3. 挂载点是否正常"
                )
            if not task_path.is_dir():
                raise ValueError(
                    f"❌ MMK2任务路径不是目录\n"
                    f"📄 路径：{task_path}\n"
                    f"🔍 实际类型：{'文件' if task_path.is_file() else '符号链接' if task_path.is_symlink() else '未知'}\n"
                    "💡 MMK2格式要求任务路径必须是包含episode子目录的目录"
                )
            
            # 🆕 升级：将episode检查从warning升级为error（支持扁平结构）
            episode_dirs = [d for d in task_path.iterdir() if d.is_dir() and d.name.startswith('episode')]
            
            # 🆕 扁平结构检查：task_path本身就是episode
            is_flat_structure = False
            if not episode_dirs and task_path.name.startswith('episode'):
                # 检查是否有camera目录
                camera_dirs = [d for d in task_path.iterdir() if d.is_dir() and d.name.startswith('camera')]
                if camera_dirs:
                    is_flat_structure = True
                    if self.logger:
                        self.logger.info(f"✅ MMK2扁平结构验证通过: task_path本身就是episode ({task_path.name})")
            
            if not episode_dirs and not is_flat_structure:
                # 显示目录内容帮助诊断
                all_dirs = [d.name for d in task_path.iterdir() if d.is_dir()]
                all_files = [f.name for f in task_path.iterdir() if f.is_file()]
                raise FileNotFoundError(
                    f"❌ No episode directories found\n"
                    f"   📂 Task path: {task_path}\n"
                    f"   📋 Directories found: {all_dirs[:10] if all_dirs else 'None'}\n"
                    f"   📋 Files found: {all_files[:10] if all_files else 'None'}\n"
                    f"   💡 Expected directory pattern: episode_0000, episode_0001, ... or flat structure\n"
                    f"   💡 Check if:\n"
                    f"      1. Dataset has been extracted correctly\n"
                    f"      2. Episode directories are named with 'episode' prefix\n"
                    f"      3. Task path points to correct location\n"
                    f"      4. Or task_path itself is an episode (flat structure)"
                )
            
            # Enhanced validation: validate each episode's internal structure
            for i, episode_dir in enumerate(episode_dirs):
                self._validate_mmk2_episode_structure(episode_dir, i)
            
            # 🆕 升级：将subdirectory和image检查从warning升级为error
            for episode_dir in episode_dirs:
                # Check for required subdirectories (observations, actions, etc.)
                required_subdirs = ['observations']
                for subdir in required_subdirs:
                    subdir_path = episode_dir / subdir
                    if not subdir_path.exists():
                        # 显示episode目录结构
                        episode_subdirs = [d.name for d in episode_dir.iterdir() if d.is_dir()]
                        raise FileNotFoundError(
                            f"❌ Missing required subdirectory\n"
                            f"   📂 Episode: {episode_dir.name}\n"
                            f"   📂 Missing: {subdir}\n"
                            f"   📋 Existing subdirectories: {episode_subdirs if episode_subdirs else 'None'}\n"
                            f"   💡 MMK2 format requires '{subdir}' subdirectory in each episode"
                        )
                
                # Check for image files in observations
                obs_dir = episode_dir / 'observations'
                if obs_dir.exists():
                    image_files = list(obs_dir.glob("*.jpg")) + list(obs_dir.glob("*.png")) + list(obs_dir.glob("*.jpeg"))
                    if not image_files:
                        # 显示observations目录内容
                        obs_contents = [f.name for f in obs_dir.iterdir()]
                        raise FileNotFoundError(
                            f"❌ No image files found in observations\n"
                            f"   📂 Episode: {episode_dir.name}\n"
                            f"   📂 Observations dir: {obs_dir}\n"
                            f"   📋 Contents: {obs_contents[:10] if obs_contents else 'Empty directory'}\n"
                            f"   💡 Expected image formats: .jpg, .png, .jpeg\n"
                            f"   💡 Check if:\n"
                            f"      1. Images were recorded properly\n"
                            f"      2. File extensions are correct\n"
                            f"      3. Files are in the correct subdirectory"
                        )

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
            buffer_keys = sorted(images_buffer.keys())
            raise ValueError(
                f"❌ MMK2图像缓冲区结构错误\n"
                f"📁 任务路径：{task_path}\n"
                f"🔢 Episode索引：{ep_idx}\n"
                f"❌ 缺失键：camera_groups\n"
                f"📊 缓冲区现有键：{buffer_keys}\n"
                "💡 这通常表示：\n"
                "   1. 图像缓冲区初始化失败\n"
                "   2. Episode目录结构不符合MMK2格式\n"
                "   3. 相机目录未正确加载\n"
                "📋 请检查episode目录是否包含正确的相机子目录"
            )

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
                raise ValueError(
                    f"❌ MMK2相机目录为空\n"
                    f"📹 相机目录：{camera_dir}\n"
                    f"📁 任务路径：{task_path}\n"
                    f"🔢 Episode索引：{ep_idx}\n"
                    f"🔍 请求帧：{frame_idx}\n"
                    "💡 该相机目录中没有任何图像文件\n"
                    "📋 请检查：\n"
                    "   1. 相机是否正确录制数据\n"
                    "   2. 图像文件是否被移动或删除\n"
                    "   3. 目录权限是否正确"
                )

            # 使用最后一个可用的图像
            self.logger.warning(
                f"Frame index {frame_idx} out of range for camera {camera_dir}. Available frames: {len(camera_files)}. Using last available frame."
            )
            image_path = camera_files[-1]
        else:
            image_path = camera_files[frame_idx]

        if not image_path.exists():
            raise ValueError(
                f"❌ MMK2图像文件不存在\n"
                f"🖼️ 图像路径：{image_path}\n"
                f"📹 相机目录：{camera_dir}\n"
                f"📁 任务路径：{task_path}\n"
                f"🔢 Episode索引：{ep_idx}\n"
                f"🔢 帧索引：{frame_idx}\n"
                f"📊 该相机总帧数：{len(camera_files)}\n"
                "💡 文件在索引时存在，但读取时不存在\n"
                "📋 可能原因：\n"
                "   1. 文件在处理过程中被删除\n"
                "   2. 文件系统问题（磁盘错误、网络问题）\n"
                "   3. 并发访问冲突"
            )

        # 读取并返回图像
        try:
            img = Image.open(image_path)
            return np.array(img)
        except OSError as e:
            if "truncated" in str(e):
                file_size = image_path.stat().st_size if image_path.exists() else -1
                raise ValueError(
                    f"❌ MMK2图像文件损坏或截断\n"
                    f"🖼️ 图像路径：{image_path}\n"
                    f"📹 相机：{camera_dir}\n"
                    f"📁 任务：{task_path.name}\n"
                    f"🔢 Episode：{ep_idx} | 帧：{frame_idx}\n"
                    f"📊 文件大小：{file_size} bytes\n"
                    f"⚠️ 原始错误：{str(e)}\n"
                    "💡 可能原因：\n"
                    "   1. 录制过程中断（磁盘满、程序崩溃）\n"
                    "   2. 文件传输不完整\n"
                    "   3. 存储介质损坏\n"
                    "🔧 建议：\n"
                    "   1. 重新录制该episode\n"
                    "   2. 检查磁盘健康状态\n"
                    "   3. 使用校验和验证文件完整性"
                ) from e
            raise ValueError(
                f"❌ MMK2图像读取失败\n"
                f"🖼️ 图像路径：{image_path}\n"
                f"📹 相机：{camera_dir}\n"
                f"📁 任务：{task_path.name}\n"
                f"🔢 Episode：{ep_idx} | 帧：{frame_idx}\n"
                f"⚠️ 原始错误：{str(e)}\n"
                "💡 可能原因：\n"
                "   1. 文件格式不支持\n"
                "   2. 文件权限问题\n"
                "   3. 系统资源不足\n"
                "📋 请检查文件格式和权限"
            ) from e
        except Exception as e:
            raise ValueError(
                f"❌ MMK2图像处理意外错误\n"
                f"🖼️ 图像路径：{image_path}\n"
                f"📹 相机：{camera_dir}\n"
                f"📁 任务：{task_path.name}\n"
                f"🔢 Episode：{ep_idx} | 帧：{frame_idx}\n"
                f"⚠️ 错误类型：{type(e).__name__}\n"
                f"⚠️ 错误详情：{str(e)}\n"
                "💡 请联系开发者，提供此错误信息"
            ) from e

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
        """获取episode的帧数 - 使用主BSON文件的帧数
        
        🚀 性能优化：使用BsonFileCache缓存解析结果
        """
        episode_dir = self._get_episode_directory(task_path, ep_idx)
        main_bson_file = episode_dir / "episode_0.bson"

        if not main_bson_file.exists():
            # 列出episode目录中的所有文件
            episode_files = list(episode_dir.glob("*")) if episode_dir.exists() else []
            bson_files = [f for f in episode_files if f.suffix == ".bson"]
            
            raise ValueError(
                f"❌ MMK2主BSON文件缺失\n"
                f"📄 期望文件：{main_bson_file}\n"
                f"📁 Episode目录：{episode_dir}\n"
                f"🔢 Episode索引：{ep_idx}\n"
                f"📊 目录统计：\n"
                f"   - 总文件数：{len(episode_files)}\n"
                f"   - BSON文件数：{len(bson_files)}\n" +
                ("   - BSON文件列表：\n" + "\n".join(f"      * {f.name}" for f in bson_files[:5]) if bson_files else "") +
                "\n💡 MMK2格式要求：\n"
                "   - 每个episode目录必须包含episode_0.bson\n"
                "   - 该文件包含episode的元数据和帧数信息\n"
                "📋 请检查：\n"
                "   1. Episode是否完整录制\n"
                "   2. 文件是否被重命名或移动\n"
                "   3. 数据集是否按MMK2格式正确生成"
            )

        try:
            # 🚀 使用缓存获取BSON数据
            doc = self._bson_cache.get(main_bson_file)
            
            if doc and "data" in doc:
                # 获取任一数据路径的长度作为帧数
                for value in doc["data"].values():
                    if isinstance(value, list):
                        return len(value)

            return 0
        except Exception as e:
            file_size = main_bson_file.stat().st_size if main_bson_file.exists() else -1
            raise ValueError(
                f"❌ MMK2 BSON文件读取失败\n"
                f"📄 文件路径：{main_bson_file}\n"
                f"📁 Episode目录：{episode_dir}\n"
                f"🔢 Episode索引：{ep_idx}\n"
                f"📊 文件大小：{file_size} bytes\n"
                f"⚠️ 错误类型：{type(e).__name__}\n"
                f"⚠️ 错误详情：{str(e)}\n"
                "💡 可能原因：\n"
                "   1. BSON文件格式损坏\n"
                "   2. 文件不完整或截断\n"
                "   3. BSON解析器版本不兼容\n"
                "📋 建议：\n"
                "   1. 验证文件完整性\n"
                "   2. 检查BSON文件格式是否正确\n"
                "   3. 重新生成该episode数据"
            )

    # @override
    def _get_task_episodes_num(self, task_path: Path) -> int:
        """获取任务的episode数量
        
        支持两种结构：
        1. 嵌套结构：task_path/episode_0, episode_1, ...
        2. 扁平结构：task_path本身就是episode（当task_path名字以episode开头时）
        """
        try:
            episode_dirs = [
                d for d in task_path.iterdir() if d.is_dir() and d.name.startswith("episode")
            ]
            episode_count = len(episode_dirs)
            
            # 🆕 检查扁平结构：如果没有找到子episode目录，检查task_path本身是否是episode
            if episode_count == 0:
                # 如果task_path本身以episode开头，且包含camera目录，说明是扁平结构
                if task_path.name.startswith("episode"):
                    # 检查是否有camera目录（MMK2格式的特征）
                    camera_dirs = [d for d in task_path.iterdir() if d.is_dir() and d.name.startswith("camera")]
                    if camera_dirs:
                        # 扁平结构：task_path本身就是episode
                        if self.logger:
                            self.logger.info(f"✅ MMK2扁平结构: task_path本身就是episode ({task_path.name})")
                        return 1
                
                # 如果不是扁平结构，提供警告
                all_dirs = [d.name for d in task_path.iterdir() if d.is_dir()]
                
                warning_msg = (
                    f"MMK2 Episode Count Warning: No episode directories found in task '{task_path}'. "
                    f"All directories found: {all_dirs}. "
                    f"Expected directories starting with 'episode'. "
                    f"Task path exists: {task_path.exists()}. "
                    f"This will likely cause conversion failures."
                )
                
                if self.logger:
                    self.logger.warning(f"MMK2 Episode Count Warning: {warning_msg}")
            
            return episode_count
            
        except Exception as e:
            error_msg = (
                f"MMK2 Episode Count Error: Failed to count episodes in task '{task_path}'. "
                f"Original error: {type(e).__name__}: {e}. "
                f"Task path exists: {task_path.exists()}."
            )
            
            if self.logger:
                self.logger.error(f"MMK2 Episode Count Error: {error_msg}")
            
            raise ValueError(error_msg) from e

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
        """准备状态数据缓冲区
        
        🚀 性能优化：使用BsonFileCache避免重复解析
        """
        episode_dir = self._get_episode_directory(task_path, ep_idx)

        # 读取主BSON文件 - 使用缓存
        main_bson_file = episode_dir / "episode_0.bson"
        main_data = {}
        if main_bson_file.exists():
            doc = self._bson_cache.get(main_bson_file)
            if doc and "data" in doc:
                main_data = doc["data"]

        # 读取手部BSON文件 - 使用缓存
        hand_bson_file = episode_dir / "xhand_control_data.bson"
        hand_data = []
        if hand_bson_file.exists():
            doc = self._bson_cache.get(hand_bson_file)
            if doc and "frames" in doc:
                hand_data = doc["frames"]

        return {"main_data": main_data, "hand_data": hand_data}

    # @override
    def _prepare_episode_actions_buffer(self, task_path: Path, ep_idx: int) -> any:
        """准备动作数据缓冲区 - 与状态数据共用"""
        return self._prepare_episode_states_buffer(task_path, ep_idx)

    def _get_episode_directory(self, task_path: Path, ep_idx: int) -> Path:
        """获取episode目录
        
        支持两种结构：
        1. 嵌套结构：task_path/episode_0, episode_1, ...
        2. 扁平结构：task_path本身就是episode
        """
        episode_dirs = sorted(
            [d for d in task_path.iterdir() if d.is_dir() and d.name.startswith("episode")]
        )
        
        # 🆕 扁平结构处理
        if len(episode_dirs) == 0 and task_path.name.startswith("episode"):
            # 检查是否有camera目录
            camera_dirs = [d for d in task_path.iterdir() if d.is_dir() and d.name.startswith("camera")]
            if camera_dirs and ep_idx == 0:
                # 扁平结构：task_path本身就是episode
                return task_path
        
        if ep_idx >= len(episode_dirs):
            # 提供详细的MMK2 Episode目录错误诊断信息
            all_dirs = [d.name for d in task_path.iterdir() if d.is_dir()]
            episode_dir_names = [d.name for d in episode_dirs]
            
            error_msg = (
                f"MMK2 Episode Directory Error: Episode index {ep_idx} out of range in task '{task_path}'. "
                f"Found {len(episode_dirs)} episode directories. "
                f"Episode directories found: {episode_dir_names if episode_dir_names else 'None'}. "
                f"All directories in task: {all_dirs}. "
                f"Task path exists: {task_path.exists()}. "
                f"This might indicate missing episode data or incorrect task path."
            )
            
            if self.logger:
                self.logger.error(f"MMK2 Episode Directory Error: {error_msg}")
                self.logger.error("WARNING: Check if the task directory contains properly named episode_* folders!")
            
            raise ValueError(error_msg)
        return episode_dirs[ep_idx]
    
    def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
        """获取 MMK2 episode 的源文件信息"""
        try:
            episode_dir = self._get_episode_directory(task_path, ep_idx)
            return {
                "format": "MMK2",
                "episode_directory": str(episode_dir.relative_to(self.dataset_path)),
                "absolute_path": str(episode_dir.absolute()),
            }
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to get source files for episode {ep_idx}: {e}")
        return {}

