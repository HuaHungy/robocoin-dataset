import io
import logging
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

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
    "other_suffixes": {".yaml", ".txt", ".mp4", ".db", ".doc", ".docx"},
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
        raise FileNotFoundError(f"Dir dose not exist: {directory}.")
    if not directory.is_dir():
        raise NotADirectoryError(f"{directory} is not directory.")

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
        raise FileNotFoundError(f"{h5_file_path} does not exist")

    if not h5_file_path.is_file():
        raise Exception(f"{h5_file_path} is not a file")

    try:
        with h5py.File(h5_file_path, "r") as h5_file:
            explore_hdf5_group(h5_file)
    except Exception as e:
        raise Exception(f"Error validating {h5_file_path}: {e}")


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
                raise FileNotFoundError(f"{path} does not exist")
            if path.is_file():
                raise ValueError(f"{path} is a file")

            unexpected_files.extend(find_unexpected_files(path))

        if unexpected_files:
            err_msg = "Found unexpected files in dataset directory:"
            err_msg += "\n".join(f"{path}" for path in unexpected_files)
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
            err_msg = "Found invalid h5 files:"
            err_msg += "\n".join(f"{h5_file}" for h5_file in invalid_h5_files)
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
                            f"Missing required paths in {sample_h5_file}: {missing_paths}"
                        )

                    if invalid_paths:
                        validation_errors.append(
                            f"Invalid datasets in {sample_h5_file}: {invalid_paths}"
                        )

                    if self.logger and not missing_paths and not invalid_paths:
                        self.logger.info(f"H5 structure validation passed for task: {task_path}")

            except Exception as e:
                validation_errors.append(f"Error reading H5 file {sample_h5_file}: {e}")

        if validation_errors:
            error_msg = "H5 structure validation failed:\n" + "\n".join(validation_errors)
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

        h5_path = args_dict["h5_path"]
        image_data = images_buffer[h5_path][frame_idx]

        if self._image_is_iobytes:
            try:
                img = Image.open(io.BytesIO(image_data))
                return np.array(img)
            except Exception:
                self._image_is_iobytes = False
        return image_data

    # @override
    def _get_frame_sub_states(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        sub_states_buffer: any = None,
    ) -> np.ndarray:
        h5_path = args_dict["h5_path"]
        from_idx = args_dict["range_from"]
        to_idx = args_dict["range_to"]
        return sub_states_buffer[h5_path][frame_idx][from_idx:to_idx]

    # @override
    def _get_frame_sub_actions(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        sub_actions_buffer: any = None,
    ) -> np.ndarray:
        h5_path = args_dict["h5_path"]
        from_idx = args_dict["range_from"]
        to_idx = args_dict["range_to"]
        return sub_actions_buffer[h5_path][frame_idx][from_idx:to_idx]

    # @override
    def _get_episode_frames_num(self, task_path: Path, ep_idx: int) -> int:
        args = self.converter_config[FEATURES_KEY][OBSERVATION_KEY][STATE_KEY][SUB_STATE_KEY][0][
            ARGS_KEY
        ]
        if "h5_path" not in args:
            raise ValueError("h5_path is not specified in the config")
        h5_path = args["h5_path"]

        h5_file_path = self.task_episode_h5file_paths[task_path][ep_idx]
        try:
            with h5py.File(h5_file_path, "r") as h5_file:
                return h5_file[h5_path].shape[0]
        except OSError as e:
            error_str = str(e)
            if "bad global heap collection signature" in error_str:
                raise ValueError(f"H5 File Corruption Error (Frame Count): H5 file has corrupted global heap collection signature. "
                               f"File path: {h5_file_path}, Task: {task_path.name}, Episode: {ep_idx}, "
                               f"Original error: {error_str}. Please regenerate this H5 file.") from e
            raise ValueError(f"H5 File OSError (Frame Count): Cannot read frame count from H5 file. "
                           f"File path: {h5_file_path}, Task: {task_path.name}, Episode: {ep_idx}, "
                           f"Original error: {error_str}") from e
        except Exception as e:
            raise ValueError(f"H5 File Error (Frame Count): Error while reading frame count from H5 file. "
                           f"File path: {h5_file_path}, Task: {task_path.name}, Episode: {ep_idx}, "
                           f"H5 path: {h5_path}, Original error: {e}") from e

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

        def _get_dataset(name: str, obj: any) -> None:
            if isinstance(obj, h5py.Dataset):
                try:
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
