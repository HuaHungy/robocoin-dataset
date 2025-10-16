import io
import logging
import tempfile
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import cv2
import h5py
import numpy as np
from natsort import natsorted
from PIL import Image

from robocoin_dataset.format_converter.tolerobot.constant import (
    ARGS_KEY,
    DATASET_UUID_FILE,
    DESCRIBE_TXT_FILE,
    DESCRIPTION_TXT_FILE,
    DEVICE_MODEL_ANNOTATION_FILE,
    FEATURES_KEY,
    H5_SUFFIX,
    HDF5_SUFFIX,
    IMAGE_KEY,
    LOCAL_DATASET_INFO_FILE,
    LOCAL_TASK_INFO_FILE,
    OBSERVATION_KEY,
    STATE_KEY,
    SUB_STATE_KEY,
)
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import (
    LerobotFormatConverter,
)


@dataclass
class H5Buffer:
    h5_data: dict | None = None
    task_path: Path | None = None
    ep_idx: int | None = None


ALLOWED_RULES = {
    "exact_names": {
        LOCAL_TASK_INFO_FILE,
        LOCAL_DATASET_INFO_FILE,
        DATASET_UUID_FILE,
        DESCRIPTION_TXT_FILE,
        DESCRIBE_TXT_FILE,
        DEVICE_MODEL_ANNOTATION_FILE,
    },  # 允许的完整文件名
    "allowed_suffixes": {H5_SUFFIX, HDF5_SUFFIX},  # 允许的后缀
    "other_suffixes": {".yaml", ".txt", ".mp4", ".db", ".doc", ".docx", ".hdf5"},
}

# NAS_EADIR = "@eaDir"
NAS_SYSFILE_TAG = "@"


def is_allowed_file(file_path: Path) -> bool:
    filename = file_path.name
    suffix = file_path.suffix

    ret = (
        filename in ALLOWED_RULES["exact_names"]
        or suffix in ALLOWED_RULES["allowed_suffixes"]
        or NAS_SYSFILE_TAG in filename
        or suffix in ALLOWED_RULES["other_suffixes"]
    )
    if ret:
        if suffix in ALLOWED_RULES["allowed_suffixes"]:
            if file_path.stat().st_size < 1024:
                return False

    return ret


def find_unexpected_files(directory: Path, include_hidden: bool = False) -> list[str]:
    directory = Path(directory)

    if not directory.exists():
        parent_dir = directory.parent
        raise FileNotFoundError(
            f"❌ Directory does not exist.\n"
            f"   📂 Requested directory: {directory}\n"
            f"   📁 Parent directory: {parent_dir} {'(exists)' if parent_dir.exists() else '(NOT FOUND)'}\n"
            f"   💡 Check if path is correct and directory has been created"
        )
    if not directory.is_dir():
        raise NotADirectoryError(
            f"❌ Path is not a directory.\n"
            f"   📄 Path: {directory}\n"
            f"   💡 This path points to a file, not a directory"
        )

    unexpected_files: list[str] = []

    # 🔍 递归遍历所有文件
    for file_path in directory.rglob("*"):
        if file_path.is_file():
            # 跳过隐藏文件（可选）
            if not include_hidden and file_path.name.startswith("."):
                continue

            if not is_allowed_file(file_path):
                unexpected_files.append(str(file_path))

    return unexpected_files


def explore_hdf5_group(group, prefix="") -> None:  # noqa: ANN001
    for key in group.keys():
        item = group[key]
        if isinstance(item, h5py.Dataset):
            pass
        elif isinstance(item, h5py.Group):
            explore_hdf5_group(item, prefix + "  ")


def validate_h5file(h5_file_path: Path) -> list[Path]:
    if not h5_file_path.exists():
        parent_dir = h5_file_path.parent
        available_files = []
        if parent_dir.exists():
            available_files = [f.name for f in parent_dir.glob("*.h5") + parent_dir.glob("*.hdf5")]
        
        raise FileNotFoundError(
            f"❌ H5 file does not exist.\n"
            f"   🗂️  Expected file: {h5_file_path}\n"
            f"   📂 Parent directory: {parent_dir}\n"
            f"   📋 H5 files in directory: {available_files if available_files else 'None'}\n"
            f"   💡 Check if:\n"
            f"      1. File name is correct\n"
            f"      2. File has been created/recorded\n"
            f"      3. Path is correct"
        )

    if not h5_file_path.is_file():
        raise Exception(
            f"❌ Path is not a file.\n"
            f"   📂 Path: {h5_file_path}\n"
            f"   💡 This path points to a directory, not a file"
        )

    try:
        with h5py.File(h5_file_path, "r") as h5_file:
            explore_hdf5_group(h5_file)
    except Exception as e:
        raise Exception(
            f"❌ Error validating H5 file.\n"
            f"   🗂️  File: {h5_file_path}\n"
            f"   ❌ Error: {e!s}\n"
            f"   💡 H5 file may be corrupted or incompatible format"
        )


class LerobotFormatConverterHdf5(LerobotFormatConverter):
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
        self.h5_buffer: H5Buffer = H5Buffer()
        self._image_is_iobytes = True

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

    def _prevalidate_files(self) -> None:
        unexpected_files: list[Path] = []
        for path in self.path_task_dict.keys():
            if not path.exists():
                parent_dir = path.parent
                raise FileNotFoundError(
                    f"❌ Task path does not exist.\n"
                    f"   📁 Task path: {path}\n"
                    f"   📂 Parent directory: {parent_dir} {'(exists)' if parent_dir.exists() else '(NOT FOUND)'}\n"
                    f"   💡 Check if task directory has been created"
                )
            if path.is_file():
                raise ValueError(
                    f"❌ Task path is a file, not a directory.\n"
                    f"   📄 Path: {path}\n"
                    f"   💡 Task path should be a directory containing episodes"
                )

            unexpected_files.extend(find_unexpected_files(path))

        if unexpected_files:
            err_msg = (
                f"❌ Found unexpected files in dataset directory.\n"
                f"   📂 Task paths checked: {len(self.path_task_dict)} directories\n"
                f"   📋 Unexpected files ({len(unexpected_files)}):\n"
            )
            # 只显示前10个，避免输出过长
            for file_path in unexpected_files[:10]:
                err_msg += f"      - {file_path}\n"
            if len(unexpected_files) > 10:
                err_msg += f"      ... and {len(unexpected_files) - 10} more files\n"
            err_msg += "   💡 Remove unexpected files or update allowed file rules"
            raise Exception(err_msg)

        invalid_h5_files = []
        for path in self.task_episode_h5file_paths:
            for file in path.rglob("*.h5"):
                try:
                    validate_h5file(file)
                except Exception:  # noqa: PERF203
                    invalid_h5_files.append(file)

            for file in path.rglob("*.hdf5"):
                try:
                    validate_h5file(file)
                except Exception:  # noqa: PERF203
                    invalid_h5_files.append(file)

        if invalid_h5_files:
            err_msg = (
                f"❌ Found invalid H5 files.\n"
                f"   📊 Total invalid files: {len(invalid_h5_files)}\n"
                f"   🗂️  Complete list of invalid H5 files:\n"
            )
            # 列出所有的 invalid H5 文件
            for h5_file in invalid_h5_files:
                err_msg += f"      - {h5_file}\n"
            err_msg += "   💡 H5 files may be corrupted or have incompatible format"
            raise Exception(err_msg)

        # 验证HDF5文件内部结构
        self._validate_h5_structure()

    def _validate_h5_structure(self) -> None:
        """验证HDF5文件内部结构是否与配置的版本相符"""
        if self.logger:
            self.logger.info("Validating HDF5 internal structure...")

        # 收集所有需要验证的路径
        required_paths = set()

        # 从图像配置中收集路径
        for image_config in self.converter_config[FEATURES_KEY][OBSERVATION_KEY][IMAGE_KEY]:
            if ARGS_KEY in image_config and "h5_path" in image_config[ARGS_KEY]:
                required_paths.add(image_config[ARGS_KEY]["h5_path"])

        # 从状态配置中收集路径
        for state_config in self.converter_config[FEATURES_KEY][OBSERVATION_KEY][STATE_KEY][
            SUB_STATE_KEY
        ]:
            if ARGS_KEY in state_config and "h5_path" in state_config[ARGS_KEY]:
                required_paths.add(state_config[ARGS_KEY]["h5_path"])

        # 从动作配置中收集路径
        if "sub_actions" in self.converter_config[FEATURES_KEY]["action"]:
            for action_config in self.converter_config[FEATURES_KEY]["action"]["sub_actions"]:
                if ARGS_KEY in action_config and "h5_path" in action_config[ARGS_KEY]:
                    required_paths.add(action_config[ARGS_KEY]["h5_path"])

        if not required_paths:
            if self.logger:
                self.logger.warning(
                    "No h5_path found in configuration, skipping H5 structure validation"
                )
            return

        # 验证每个任务路径下的H5文件
        validation_errors = []
        for task_path in self.path_task_dict.keys():
            h5_files = self.task_episode_h5file_paths.get(task_path, [])

            if not h5_files:
                validation_errors.append(f"No H5 files found in task path: {task_path}")
                continue

            # 验证第一个H5文件作为样本（假设同一任务下的H5文件结构一致）
            sample_h5_file = h5_files[0]
            try:
                with h5py.File(sample_h5_file, "r") as h5_file:
                    missing_paths = []
                    invalid_paths = []

                    for required_path in required_paths:
                        if required_path not in h5_file:
                            missing_paths.append(required_path)
                        else:
                            # 检查是否为有效的数据集
                            try:
                                dataset = h5_file[required_path]
                                if not isinstance(dataset, h5py.Dataset):
                                    invalid_paths.append(f"{required_path} (not a dataset)")
                                elif len(dataset.shape) == 0:
                                    invalid_paths.append(f"{required_path} (empty dataset)")
                            except Exception as e:
                                invalid_paths.append(f"{required_path} (error: {e})")

                    if missing_paths:
                        validation_errors.append(
                            f"   🗂️  File: {sample_h5_file.name}\n"
                            f"      ❌ Missing paths: {missing_paths}"
                        )

                    if invalid_paths:
                        validation_errors.append(
                            f"   🗂️  File: {sample_h5_file.name}\n"
                            f"      ⚠️  Invalid datasets: {invalid_paths}"
                        )

                    if self.logger and not missing_paths and not invalid_paths:
                        self.logger.info(f"✓ H5 structure validation passed for task: {task_path.name}")

            except Exception as e:
                validation_errors.append(
                    f"   🗂️  File: {sample_h5_file.name}\n"
                    f"      ❌ Read error: {e!s}"
                )

        if validation_errors:
            error_msg = (
                f"❌ H5 structure validation failed.\n"
                f"   📊 Issues found in {len(validation_errors)} file(s)\n"
                f"   📋 Validation errors:\n"
            )
            error_msg += "\n".join(validation_errors)
            error_msg += (
                f"\n   💡 Check if:\n"
                f"      1. H5 files match expected structure\n"
                f"      2. Config h5_path values are correct\n"
                f"      3. All required datasets exist in H5 files"
            )
            raise ValueError(error_msg)

        if self.logger:
            self.logger.info("H5 structure validation completed successfully")

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

        try:
            h5_path = args_dict["h5_path"]
        except KeyError as e:
            available_keys = list(args_dict.keys())
            raise KeyError(
                f"❌ Missing required 'h5_path' in args_dict.\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                f"   📋 Available keys: {available_keys}\n"
                f"   💡 args_dict must contain 'h5_path' key specifying the H5 dataset path"
            ) from e

        # 根据配置检查是否使用压缩视频格式
        use_compressed_video = args_dict.get("use_compressed_video", False)
        
        if use_compressed_video:
            # 使用压缩视频格式
            video_path = h5_path.replace('/images', '/video')
            video_index_path = h5_path.replace('/images', '/video_index')
            
            if video_path not in images_buffer or video_index_path not in images_buffer:
                available_paths = list(images_buffer.keys())[:10]
                raise KeyError(
                    f"❌ Compressed video format configured but video data not found.\n"
                    f"   🔍 Expected video path: {video_path}\n"
                    f"   🔍 Expected index path: {video_index_path}\n"
                    f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                    f"   📋 Available paths (showing first 10): {available_paths}\n"
                    f"   💡 Set use_compressed_video: false in config if using normal image format"
                )
            
            return self._get_frame_from_compressed_video(
                task_path, ep_idx, frame_idx, 
                images_buffer[video_path],
                images_buffer[video_index_path],
                h5_path
            )

        try:
            image_data = images_buffer[h5_path][frame_idx]
        except KeyError as e:
            available_paths = list(images_buffer.keys())[:10]
            total_paths = len(images_buffer.keys())
            raise KeyError(
                f"❌ H5 path not found in images buffer.\n"
                f"   🔍 Requested path: {h5_path}\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                f"   📋 Available paths (showing first 10 of {total_paths}): {available_paths}\n"
                f"   💡 Check if h5_path is correct in your config"
            ) from e
        except IndexError as e:
            try:
                max_frames = len(images_buffer[h5_path])
            except Exception:
                max_frames = "unknown"
            raise IndexError(
                f"❌ Frame index out of range.\n"
                f"   🎯 Requested frame: {frame_idx}\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}\n"
                f"   🔍 H5 path: {h5_path}\n"
                f"   📐 Available frames: 0 to {max_frames-1 if isinstance(max_frames, int) else max_frames}\n"
                f"   💡 Check if frame index is within valid range"
            ) from e

        if self._image_is_iobytes:
            try:
                img = Image.open(io.BytesIO(image_data))
                return np.array(img)
            except Exception as e:
                self._image_is_iobytes = False
                # Log warning but continue with raw data
                if self.logger:
                    self.logger.warning(
                        f"⚠️ Failed to decode image as bytes, falling back to raw data.\n"
                        f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                        f"   🔍 H5 path: {h5_path}\n"
                        f"   Error: {e!s}"
                    )
        return image_data

    def _get_frame_from_compressed_video(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        video_data: np.ndarray,
        video_index: np.ndarray,
        h5_path: str,
    ) -> np.ndarray:
        """
        从压缩视频数据中提取指定帧
        
        Args:
            task_path: 任务路径
            ep_idx: episode 索引
            frame_idx: 帧索引
            video_data: 压缩的视频数据（void 类型的 numpy 数组）
            video_index: 视频索引数组，表示帧到字节的映射
            h5_path: H5 路径（用于日志）
        
        Returns:
            解码后的图像数组 (H, W, C)
        """
        try:
            # 将 void 类型转换为字节
            if isinstance(video_data, np.void) or (isinstance(video_data, np.ndarray) and video_data.dtype.kind == 'V'):
                video_bytes = np.array(video_data).tobytes()
            else:
                video_bytes = bytes(video_data)
            
            # 创建临时文件保存视频
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_file:
                tmp_path = tmp_file.name
                tmp_file.write(video_bytes)
            
            try:
                # 使用 OpenCV 读取视频
                cap = cv2.VideoCapture(tmp_path)
                if not cap.isOpened():
                    raise RuntimeError(f"Failed to open video file: {tmp_path}")
                
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                
                # 获取总的机械臂数据帧数（从第一个非空的 state 数据推断）
                # 假设所有 state 数据帧数相同
                # TODO: 可以从配置或 H5 文件的其他字段获取更准确的值
                total_arm_frames = 327  # 硬编码，后续可以改进
                
                # 计算视频帧索引（使用最近邻插值）
                # 将机械臂帧映射到视频帧
                if total_frames > 0:
                    video_frame_idx = min(int(frame_idx * total_frames / total_arm_frames), total_frames - 1)
                else:
                    video_frame_idx = 0
                
                # 跳转到指定帧
                cap.set(cv2.CAP_PROP_POS_FRAMES, video_frame_idx)
                ret, frame = cap.read()
                cap.release()
                
                if not ret:
                    raise RuntimeError(f"Failed to read frame {video_frame_idx} from video (total: {total_frames})")
                
                # OpenCV 读取的是 BGR 格式，转换为 RGB
                return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
            finally:
                # 清理临时文件
                import os
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                    
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"❌ Failed to decode compressed video frame.\n"
                    f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                    f"   🔍 H5 path: {h5_path}\n"
                    f"   Error: {e!s}"
                )
            raise

    # @override
    def _get_frame_sub_states(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        sub_states_buffer: any = None,
    ) -> np.ndarray:
        # Validate required keys
        required_keys = ["h5_path", "range_from", "range_to"]
        missing_keys = [key for key in required_keys if key not in args_dict]
        
        if missing_keys:
            available_keys = list(args_dict.keys())
            raise KeyError(
                f"❌ Missing required keys in args_dict for sub_states.\n"
                f"   ❌ Missing: {missing_keys}\n"
                f"   📋 Available: {available_keys}\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                f"   💡 args_dict must contain: h5_path, range_from, range_to\n"
                f"      Example: {{h5_path: '/observations/qpos', range_from: 0, range_to: 7}}"
            )

        h5_path = args_dict["h5_path"]
        from_idx = args_dict["range_from"]
        to_idx = args_dict["range_to"]

        try:
            frame_data = sub_states_buffer[h5_path][frame_idx]
        except KeyError as e:
            available_paths = list(sub_states_buffer.keys())[:10]
            total_paths = len(sub_states_buffer.keys())
            raise KeyError(
                f"❌ H5 path not found in sub_states buffer.\n"
                f"   🔍 Requested path: {h5_path}\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                f"   📋 Available paths (showing first 10 of {total_paths}): {available_paths}\n"
                f"   💡 Check if h5_path is correct in your config"
            ) from e
        except IndexError as e:
            try:
                max_frames = len(sub_states_buffer[h5_path])
            except Exception:
                max_frames = "unknown"
            raise IndexError(
                f"❌ Frame index out of range.\n"
                f"   🎯 Requested frame: {frame_idx}\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}\n"
                f"   🔍 H5 path: {h5_path}\n"
                f"   📐 Available frames: 0 to {max_frames-1 if isinstance(max_frames, int) else max_frames}\n"
                f"   💡 Check if frame index is within valid range"
            ) from e

        # Check if frame_data is a scalar (0-dimensional)
        if not isinstance(frame_data, np.ndarray):
            frame_data = np.array(frame_data)
        
        if frame_data.ndim == 0:
            # Scalar value - cannot slice
            if from_idx == 0 and to_idx == 1:
                # Special case: extracting a single scalar value
                return np.array([frame_data.item()])
            
            raise ValueError(
                f"❌ Cannot slice scalar data.\n"
                f"   🔢 Requested range: [{from_idx}:{to_idx}]\n"
                f"   📐 Data shape: {frame_data.shape} (scalar)\n"
                f"   📊 Data value: {frame_data}\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                f"   🔍 H5 path: {h5_path}\n"
                "   💡 Possible causes:\n"
                "      1. H5 data is stored as scalar instead of array\n"
                "      2. Wrong H5 path in config (pointing to wrong dataset)\n"
                "      3. Config expects array but data is single value\n"
                "   🔧 Solutions:\n"
                "      1. If data is single value, use range_from: 0, range_to: 1\n"
                "      2. Check H5 file structure to verify data dimensions\n"
                "      3. Update config to match actual H5 data structure"
            )
        
        # Validate slicing range for array data
        try:
            data_len = len(frame_data)
        except Exception:
            data_len = None

        if data_len is not None:
            if from_idx < 0 or to_idx > data_len or from_idx >= to_idx:
                raise ValueError(
                    f"❌ Invalid slicing range for sub_states.\n"
                    f"   🔢 Requested range: [{from_idx}:{to_idx}]\n"
                    f"   📐 Data length: {data_len}\n"
                    f"   📐 Data shape: {frame_data.shape}\n"
                    f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                    f"   🔍 H5 path: {h5_path}\n"
                    f"   💡 Valid range should be: 0 <= range_from < range_to <= {data_len}"
                )

        return frame_data[from_idx:to_idx]

    # @override
    def _get_frame_sub_actions(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        sub_actions_buffer: any = None,
    ) -> np.ndarray:
        # Validate required keys
        required_keys = ["h5_path", "range_from", "range_to"]
        missing_keys = [key for key in required_keys if key not in args_dict]
        
        if missing_keys:
            available_keys = list(args_dict.keys())
            raise KeyError(
                f"❌ Missing required keys in args_dict for sub_actions.\n"
                f"   ❌ Missing: {missing_keys}\n"
                f"   📋 Available: {available_keys}\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                f"   💡 args_dict must contain: h5_path, range_from, range_to\n"
                f"      Example: {{h5_path: '/action', range_from: 0, range_to: 7}}"
            )

        h5_path = args_dict["h5_path"]
        from_idx = args_dict["range_from"]
        to_idx = args_dict["range_to"]

        try:
            frame_data = sub_actions_buffer[h5_path][frame_idx]
        except KeyError as e:
            available_paths = list(sub_actions_buffer.keys())[:10]
            total_paths = len(sub_actions_buffer.keys())
            raise KeyError(
                f"❌ H5 path not found in sub_actions buffer.\n"
                f"   🔍 Requested path: {h5_path}\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                f"   📋 Available paths (showing first 10 of {total_paths}): {available_paths}\n"
                f"   💡 Check if h5_path is correct in your config"
            ) from e
        except IndexError as e:
            try:
                max_frames = len(sub_actions_buffer[h5_path])
            except Exception:
                max_frames = "unknown"
            raise IndexError(
                f"❌ Frame index out of range.\n"
                f"   🎯 Requested frame: {frame_idx}\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}\n"
                f"   🔍 H5 path: {h5_path}\n"
                f"   📐 Available frames: 0 to {max_frames-1 if isinstance(max_frames, int) else max_frames}\n"
                f"   💡 Check if frame index is within valid range"
            ) from e

        # Validate slicing range
        try:
            data_len = len(frame_data)
        except Exception:
            data_len = None

        if data_len is not None:
            if from_idx < 0 or to_idx > data_len or from_idx >= to_idx:
                raise ValueError(
                    f"❌ Invalid slicing range for sub_actions.\n"
                    f"   🔢 Requested range: [{from_idx}:{to_idx}]\n"
                    f"   📐 Data length: {data_len}\n"
                    f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                    f"   🔍 H5 path: {h5_path}\n"
                    f"   💡 Valid range should be: 0 <= range_from < range_to <= {data_len}"
                )

        return frame_data[from_idx:to_idx]

    # @override
    def _get_episode_frames_num(self, task_path: Path, ep_idx: int) -> int:
        args = self.converter_config[FEATURES_KEY][OBSERVATION_KEY][STATE_KEY][SUB_STATE_KEY][0][
            ARGS_KEY
        ]
        if "h5_path" not in args:
            available_keys = list(args.keys()) if args else []
            raise ValueError(
                f"❌ h5_path not specified in config.\n"
                f"   📁 Location: observation.state.sub_state[0].args\n"
                f"   📋 Available keys in args: {available_keys}\n"
                f"   💡 Config must specify h5_path to determine frame count\n"
                f"      Example: args: {{h5_path: '/observations/qpos', ...}}"
            )
        h5_path = args["h5_path"]

        h5_file_path = self.task_episode_h5file_paths[task_path][ep_idx]
        try:
            with h5py.File(h5_file_path, "r") as h5_file:
                return h5_file[h5_path].shape[0]
        except OSError as e:
            error_str = str(e)
            if "bad global heap collection signature" in error_str:
                raise ValueError(
                    f"❌ H5 file corruption detected.\n"
                    f"   🗂️  File: {h5_file_path.name}\n"
                    f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}\n"
                    f"   ❌ Error: Corrupted global heap collection signature\n"
                    f"   💡 This H5 file is corrupted and must be regenerated.\n"
                    f"      Original error: {error_str}"
                ) from e
            raise ValueError(
                f"❌ Cannot read H5 file (OSError).\n"
                f"   🗂️  File: {h5_file_path.name}\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}\n"
                f"   🔍 H5 path: {h5_path}\n"
                f"   ❌ Error: {error_str}\n"
                f"   💡 Check if:\n"
                f"      1. File is not corrupted\n"
                f"      2. File is not being written to\n"
                f"      3. File permissions are correct"
            ) from e
        except Exception as e:
            raise ValueError(
                f"❌ Error reading frame count from H5 file.\n"
                f"   🗂️  File: {h5_file_path.name}\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}\n"
                f"   🔍 H5 path: {h5_path}\n"
                f"   ❌ Error: {e!s}\n"
                f"   💡 Check if:\n"
                f"      1. h5_path exists in file\n"
                f"      2. Dataset has valid shape\n"
                f"      3. File format is correct"
            ) from e

    # @override
    def _get_task_episodes_num(self, task_path: Path) -> int:
        return len(self.task_episode_h5file_paths[task_path])

    # @override
    def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int) -> any:
        return self._get_episode_h5_data(task_path, ep_idx)

    # @override
    def _prepare_episode_states_buffer(self, task_path: Path, ep_idx: int) -> any:
        return self._get_episode_h5_data(task_path, ep_idx)

    # @override
    def _prepare_episode_actions_buffer(self, task_path: Path, ep_idx: int) -> any:
        return self._get_episode_h5_data(task_path, ep_idx)

    @cached_property
    def task_episode_h5file_paths(self) -> dict[Path, list[Path]]:
        task_episode_paths = {}
        for path in self.path_task_dict.keys():
            if path.exists():
                h5_files = natsorted(list(path.rglob("*.h5")))
                h5_files.extend(natsorted(list(path.rglob("*.hdf5"))))
                task_episode_paths[path] = h5_files
        return task_episode_paths

    def _get_episode_h5_data(self, task_path: Path, ep_idx: int) -> any:
        should_load = self.h5_buffer.task_path != task_path or self.h5_buffer.ep_idx != ep_idx
        if not should_load:
            return self.h5_buffer.h5_data
        self.h5_buffer.h5_data = {}

        h5_file_path = self.task_episode_h5file_paths[task_path][ep_idx]
        
        # 收集所有配置的相机路径及其 use_compressed_video 设置
        camera_configs = {}
        for image_config in self.converter_config.get(FEATURES_KEY, {}).get(OBSERVATION_KEY, {}).get(IMAGE_KEY, []):
            if ARGS_KEY in image_config and "h5_path" in image_config[ARGS_KEY]:
                h5_path = image_config[ARGS_KEY]["h5_path"]
                use_compressed = image_config[ARGS_KEY].get("use_compressed_video", False)
                camera_configs[h5_path] = use_compressed

        def _get_dataset(name: str, obj: any) -> None:
            if isinstance(obj, h5py.Dataset):
                try:
                    # 检查这个路径是否是配置中的图像路径
                    is_image_path = name in camera_configs
                    
                    if is_image_path:
                        use_compressed = camera_configs[name]
                        if use_compressed:
                            # 如果配置使用压缩视频，跳过加载 images，改为加载 video 和 video_index
                            # 跳过 images 路径，不加载
                            if self.logger:
                                self.logger.debug(f"Skipping images path {name}, will load video data instead")
                            return
                        # 否则正常加载 images
                    
                    self.h5_buffer.h5_data[name] = obj[()]
                except Exception as e:
                    # 提供详细的H5文件错误诊断信息
                    error_msg = (
                        f"H5 Dataset Read Error: Failed to read dataset '{name}' from H5 file '{h5_file_path}'. "
                        f"Task: {task_path}, Episode: {ep_idx}. "
                        f"Dataset shape: {getattr(obj, 'shape', 'Unknown')}, "
                        f"Dataset dtype: {getattr(obj, 'dtype', 'Unknown')}, "
                        f"Dataset size: {getattr(obj, 'size', 'Unknown')} bytes. "
                        f"Original error: {type(e).__name__}: {e}. "
                        f"This might indicate file corruption or incompatible H5 format."
                    )
                    
                    if self.logger:
                        self.logger.error(f"H5 File Error: {error_msg}")
                        self.logger.error("WARNING: If you see a simplified OSError, check the full error above!")
                    
                    raise ValueError(error_msg) from e

        try:
            with h5py.File(h5_file_path, "r") as h5_file:
                h5_file.visititems(_get_dataset)
                
                # 对于配置了 use_compressed_video 的相机，额外加载 video 和 video_index
                for h5_path, use_compressed in camera_configs.items():
                    if use_compressed:
                        video_path = h5_path.replace('/images', '/video')
                        video_index_path = h5_path.replace('/images', '/video_index')
                        
                        if video_path in h5_file:
                            self.h5_buffer.h5_data[video_path] = h5_file[video_path][()]
                            if self.logger:
                                self.logger.debug(f"Loaded compressed video: {video_path}")
                        else:
                            if self.logger:
                                self.logger.warning(f"Video path not found: {video_path}")
                        
                        if video_index_path in h5_file:
                            self.h5_buffer.h5_data[video_index_path] = h5_file[video_index_path][()]
                            if self.logger:
                                self.logger.debug(f"Loaded video index: {video_index_path}")
                        else:
                            if self.logger:
                                self.logger.warning(f"Video index path not found: {video_index_path}")
                
                self.h5_buffer.task_path = task_path
                self.h5_buffer.ep_idx = ep_idx
        except OSError as e:
            # 特定处理 H5 文件损坏错误
            error_str = str(e)
            if "bad global heap collection signature" in error_str:
                error_msg = (
                    f"H5 File Corruption Error: H5 file has corrupted global heap collection signature. "
                    f"File path: {h5_file_path}, "
                    f"Task: {task_path.name}, "
                    f"Episode: {ep_idx}, "
                    f"File size: {h5_file_path.stat().st_size if h5_file_path.exists() else 'N/A'} bytes. "
                    f"This indicates severe file corruption. Original error: {error_str}. "
                    f"Please regenerate or re-download this H5 file."
                )
            elif "unable to open file" in error_str.lower():
                error_msg = (
                    f"H5 File Access Error: Cannot open H5 file. "
                    f"File path: {h5_file_path}, "
                    f"Task: {task_path.name}, "
                    f"Episode: {ep_idx}, "
                    f"File exists: {h5_file_path.exists()}, "
                    f"File size: {h5_file_path.stat().st_size if h5_file_path.exists() else 'N/A'} bytes. "
                    f"Original error: {error_str}"
                )
            else:
                error_msg = (
                    f"H5 File OSError: H5 file operation failed. "
                    f"File path: {h5_file_path}, "
                    f"Task: {task_path.name}, "
                    f"Episode: {ep_idx}, "
                    f"Original error: {error_str}"
                )
            
            if self.logger:
                self.logger.error(f"H5 File Corruption Detected: {error_msg}")
            
            raise ValueError(error_msg) from e
        except Exception as e:
            # 捕获文件级别的其他错误
            if not isinstance(e, ValueError):  # 避免重复包装我们自己的ValueError
                error_msg = (
                    f"H5 File Access Error: Failed to access H5 file '{h5_file_path}'. "
                    f"Task: {task_path}, Episode: {ep_idx}. "
                    f"Original error: {type(e).__name__}: {e}. "
                    f"Please check if the file exists and is not corrupted."
                )
                
                if self.logger:
                    self.logger.error(f"H5 File Access Error: {error_msg}")
                
                raise ValueError(error_msg) from e
            
            # 重新抛出我们自己的ValueError
            raise

        return self.h5_buffer.h5_data
