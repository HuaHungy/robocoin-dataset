import importlib
import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path

import numpy as np
import yaml
from lerobot.datasets.lerobot_dataset import LeRobotDataset

from robocoin_dataset.constant import (
    LOCAL_DATASET_INFO_FILE,
    LOCAL_TASK_INFO_FILE_NAME,
    TASK_DESCRIPTIONS_KEY,
    TASK_INDEX_KEY,
)
from robocoin_dataset.format_converter.tolerobot.constant import (
    ACTION_KEY,
    ARGS_KEY,
    CAM_NAME_KEY,
    CONVERT_FUNC_KEY,
    DEFAULT_IMAGE_SHAPE_NAMES,
    DTYPE_KEY,
    FEATURES_KEY,
    FLOAT32,
    FPS,
    FRAME_IDX_KEY,
    IMAGE_DTYPE_VALUE,
    IMAGE_KEY,
    LEROBOT_FEATURE_KEY,
    NAME_KEY,
    OBSERVATION_KEY,
    SHAPE_KEY,
    STATE_KEY,
    SUB_ACTION_KEY,
    SUB_STATE_KEY,
    TIMELINE_OFFSET_KEY,
)
from robocoin_dataset.format_converter.utils.spatial_data_convertor import spatial_covertor_funcs


class LerobotFormatConverter(ABC):
    """
    Base class for converting datasets to the LeRobot format.
    This class should be extended by specific dataset format converters.
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
        if not dataset_path:
            raise ValueError("Dataset path must be provided.")
        if not output_path:
            raise ValueError("LeRobot destination path must be provided.")

        if dataset_path == output_path:
            raise ValueError("Dataset path and LeRobot destination path cannot be the same.")

        self.dataset_path = Path(dataset_path).expanduser().absolute()
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"Dataset path {self.dataset_path} does not exist.")
        self.output_path = Path(output_path).expanduser().absolute()

        if not converter_config:
            raise ValueError("Convertor config must be provided.")

        self.converter_config = converter_config

        self.repo_id = repo_id

        if not logger:
            raise ValueError("Logger must be provided.")
        self.logger = logger
        self.logger.info(f"Using dataset path: {self.dataset_path}")
        self.device_model = device_model

        try:
            self._validate_convertor_config()
        except Exception as e:
            raise ValueError(f"Invalid features description: {e}") from e

        # Standard converter initialization
        self.tasks = self._get_tasks()
        self.path_task_dict: dict[Path, str] = self._get_dataset_task_paths()
        self.task_episodes_num: dict[Path, int] = {}
        for task_path in self.path_task_dict.keys():
            self.task_episodes_num[task_path] = self._get_task_episodes_num(task_path)

        self.fps = self.converter_config[FPS]

        self._gen_image_configs()
        self._gen_action_configs()
        self._gen_state_configs()

        self.video_backend = video_backend
        self.image_writer_processes = image_writer_processes
        self.image_writer_threads = image_writer_threads

        # Episode source file mapping: {global_ep_idx: {task, task_ep_idx, source_files}}
        self.episode_source_mapping: dict[int, dict] = {}

        self._prevalidate_files()

    @abstractmethod
    def _prevalidate_files(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def _get_frame_image(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        images_buffer: any = None,
    ) -> np.ndarray:
        raise NotImplementedError

    @abstractmethod
    def _get_frame_sub_states(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        sub_states_buffer: any = None,
    ) -> np.ndarray:
        raise NotImplementedError

    @abstractmethod
    def _get_frame_sub_actions(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        sub_actions_buffer: any = None,
    ) -> np.ndarray:
        raise NotImplementedError

    @abstractmethod
    def _get_episode_frames_num(self, task_path: Path, ep_idx: int) -> int:
        raise NotImplementedError

    @abstractmethod
    def _get_task_episodes_num(self, task_path: Path) -> int:
        raise NotImplementedError

    def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
        """获取 episode 的源文件信息
        
        Returns:
            dict: 包含源文件信息的字典，例如：
                {
                    "episode_directory": str,  # episode 目录路径
                    "h5_files": list[str],     # H5 文件列表（如果有）
                    "image_directories": list[str],  # 图像目录列表（如果有）
                    "json_files": list[str],   # JSON 文件列表（如果有）
                    "other_files": list[str],  # 其他相关文件
                }
        """
        # 默认实现：返回空字典，子类可以覆盖此方法提供详细信息
        return {}

    def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int) -> any:
        return None

    def _prepare_episode_states_buffer(self, task_path: Path, ep_idx: int) -> any:
        return None

    def _prepare_episode_actions_buffer(self, task_path: Path, ep_idx: int) -> any:
        return None

    def _get_task_episodes_num(self, task_path: Path) -> int:
        if task_path not in self.task_episodes_num:
            return self.task_episodes_num[task_path]
        raise ValueError(f"Dataset task_path {task_path} not found")

    def _gen_episode_frame(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        images_buffer: any,
        states_buffer: any,
        actions_buffer: any,
    ) -> dict:
        """
        Generate a single frame for the episode.
        """
        frame_data = {}
        frame_data[FRAME_IDX_KEY] = frame_idx
        frame_data[IMAGE_KEY] = self._get_frame_images(task_path, ep_idx, frame_idx, images_buffer)
        frame_data[STATE_KEY] = self._get_frame_states(task_path, ep_idx, frame_idx, states_buffer)
        frame_data[ACTION_KEY] = self._get_frame_actions(
            task_path, ep_idx, frame_idx, actions_buffer
        )

        return frame_data

    def _validate_convertor_config(self) -> None:
        """
        Validate the convertor config.
        """
        # check features:
        if FEATURES_KEY not in self.converter_config:
            raise ValueError(f"Convertion config must contain {FEATURES_KEY} key.")

        # check features.observation:
        if OBSERVATION_KEY not in self.converter_config[FEATURES_KEY]:
            raise ValueError(
                f"Convertion config must contain {OBSERVATION_KEY} key in {FEATURES_KEY}."
            )

        # check features.observation.images:
        if IMAGE_KEY not in self.converter_config[FEATURES_KEY][OBSERVATION_KEY]:
            raise ValueError(
                f"Convertion config must contain {IMAGE_KEY} key in {FEATURES_KEY}.{OBSERVATION_KEY}."
            )

        cam_names: list[str] = []
        for image_config in self.converter_config[FEATURES_KEY][OBSERVATION_KEY][IMAGE_KEY]:
            if CAM_NAME_KEY not in image_config:
                raise ValueError(
                    f"Convertion config must contain {CAM_NAME_KEY} key in {FEATURES_KEY}.{OBSERVATION_KEY}.{IMAGE_KEY}."
                )
            cam_names.append(image_config[CAM_NAME_KEY])
            if ARGS_KEY not in image_config:
                raise ValueError(
                    f"Convertion config must contain {ARGS_KEY} key in {FEATURES_KEY}.{OBSERVATION_KEY}.{IMAGE_KEY}."
                )

        if len(set(cam_names)) != len(cam_names):
            raise ValueError(
                f"Convertion config has same cam_names in {FEATURES_KEY}.{OBSERVATION_KEY}.{IMAGE_KEY}"
            )

        if STATE_KEY not in self.converter_config[FEATURES_KEY][OBSERVATION_KEY]:
            raise ValueError(
                f"Convertion config must contain {STATE_KEY} key in {FEATURES_KEY}.{OBSERVATION_KEY}."
            )

        if SUB_STATE_KEY not in self.converter_config[FEATURES_KEY][OBSERVATION_KEY][STATE_KEY]:
            raise ValueError(
                f"Convertion config must contain {SUB_STATE_KEY} key in {FEATURES_KEY}.{OBSERVATION_KEY}.{STATE_KEY}."
            )

        sub_state_names = []
        for sub_state_config in self.converter_config[FEATURES_KEY][OBSERVATION_KEY][STATE_KEY][
            SUB_STATE_KEY
        ]:
            if NAME_KEY not in sub_state_config:
                raise ValueError(
                    f"Convertion config must contain {NAME_KEY} key in {FEATURES_KEY}.{OBSERVATION_KEY}.{STATE_KEY}.{SUB_STATE_KEY}."
                )
            sub_state_names.extend(sub_state_config[NAME_KEY])
            if ARGS_KEY not in sub_state_config:
                raise ValueError(
                    f"Convertion config must contain {ARGS_KEY} key in {FEATURES_KEY}.{OBSERVATION_KEY}.{STATE_KEY}.{SUB_STATE_KEY}."
                )

        if len(set(sub_state_names)) != len(sub_state_names):
            seen = set()
            duplicates = {x for x in sub_state_names if x in seen or seen.add(x)}
            raise ValueError(
                f"Convertion config has same state names in {FEATURES_KEY}.{OBSERVATION_KEY}.{STATE_KEY}. "
                f"Duplicates: {list(duplicates)}"
            )

        # check features.action:
        if ACTION_KEY not in self.converter_config[FEATURES_KEY]:
            raise ValueError(f"Convertion config must contain {ACTION_KEY} key in {FEATURES_KEY}.")

        if SUB_ACTION_KEY not in self.converter_config[FEATURES_KEY][ACTION_KEY]:
            raise ValueError(
                f"Convertion config must contain {SUB_ACTION_KEY} key in {FEATURES_KEY}.{ACTION_KEY}."
            )

        sub_action_names = []
        for sub_action_config in self.converter_config[FEATURES_KEY][ACTION_KEY][SUB_ACTION_KEY]:
            if NAME_KEY not in sub_action_config:
                raise ValueError(
                    f"Convertion config must contain {NAME_KEY} key in {FEATURES_KEY}.{ACTION_KEY}.{SUB_ACTION_KEY}."
                )
            sub_action_names.extend(sub_action_config[NAME_KEY])
            if ARGS_KEY not in sub_action_config:
                raise ValueError(
                    f"Convertion config must contain {ARGS_KEY} key in {FEATURES_KEY}.{ACTION_KEY}.{SUB_ACTION_KEY}."
                )

        if len(set(sub_action_names)) != len(sub_action_names):
            raise ValueError(
                f"Convertion config has same state names in {FEATURES_KEY}.{OBSERVATION_KEY}.{ACTION_KEY}"
            )

    def _get_tasks(self) -> list[str]:
        dataset_info_file_path = self.dataset_path / LOCAL_DATASET_INFO_FILE
        if not dataset_info_file_path.exists():
            raise ValueError(f"Dataset info file {dataset_info_file_path} not found.")
        with open(dataset_info_file_path) as file:
            ds_info_dict = yaml.safe_load(file)
            if not ds_info_dict:
                raise ValueError(f"Dataset info file {dataset_info_file_path} is empty.")
            if TASK_DESCRIPTIONS_KEY not in ds_info_dict:
                raise ValueError(
                    f"Dataset info file {dataset_info_file_path} does not contain task_description."
                )
            if not isinstance(ds_info_dict[TASK_DESCRIPTIONS_KEY], list):
                raise ValueError(
                    f"Dataset info file {dataset_info_file_path} does not contain task_description as list[str]."
                )
            return ds_info_dict[TASK_DESCRIPTIONS_KEY]

    def _get_dataset_task_paths(self) -> dict[Path, str]:
        """Get the paths of all tasks in the dataset."""
        dirs_to_scan = [self.dataset_path]
        task_paths_dict = {}
        try:
            while len(dirs_to_scan) > 0:
                current_path = dirs_to_scan.pop(0)
                files = Path(current_path).glob(LOCAL_TASK_INFO_FILE_NAME)
                has_task_file = False
                for file in files:
                    try:
                        with file.open("r") as f:
                            task_info_dict = yaml.safe_load(f)
                            task_index = task_info_dict[TASK_INDEX_KEY]
                            task = self.tasks[task_index]
                            task_paths_dict[file.parent] = task
                            has_task_file = True
                    except Exception as e:  # noqa: PERF203
                        raise {f"Found task index error from {file}"} from e

                if not has_task_file:
                    sub_dirs = [item for item in Path(current_path).glob("*") if item.is_dir()]
                    dirs_to_scan.extend(sub_dirs)

        except Exception as e:
            raise e

        return task_paths_dict

    def _get_one_frame_image(self, args_dict: dict) -> np.ndarray:
        task_path = list(self.path_task_dict.keys())[0]
        try:
            return self._get_frame_image(
                task_path=task_path, ep_idx=0, frame_idx=0, args_dict=args_dict
            )
        except Exception as e:
            cam_name = args_dict.get(CAM_NAME_KEY, "unknown")
            raise RuntimeError(
                f"Failed to get sample image for camera '{cam_name}' "
                f"from task_path={task_path}"
                f"Original error: {type(e).__name__}: {e}"
            ) from e

    def _get_one_frame_images(self, image_configs: list[dict]) -> dict[str, np.ndarray]:
        images = {}
        for image_config in image_configs:
            image_name = image_config[CAM_NAME_KEY]
            args_dict = image_config[ARGS_KEY]
            image = self._get_one_frame_image(args_dict)
            images[image_name] = image
        return images

    def _gen_image_configs(self) -> None:
        sample_frame_images = self._get_one_frame_images(
            self.converter_config[FEATURES_KEY][OBSERVATION_KEY][IMAGE_KEY]
        )
        for image_config in self.converter_config[FEATURES_KEY][OBSERVATION_KEY][IMAGE_KEY]:
            image_config[LEROBOT_FEATURE_KEY] = (
                f"{OBSERVATION_KEY}.{IMAGE_KEY}.{image_config[CAM_NAME_KEY]}"
            )
            try:
                image = sample_frame_images[image_config[CAM_NAME_KEY]]
                image_config[DTYPE_KEY] = IMAGE_DTYPE_VALUE
                image_config[NAME_KEY] = DEFAULT_IMAGE_SHAPE_NAMES
                image_config[SHAPE_KEY] = image.shape
            except KeyError as e:
                raise ValueError(
                    f"Convertion config has no {image_config[CAM_NAME_KEY]} in sample frame images"
                ) from e

    def _gen_state_configs(self) -> None:
        sub_state_names = []
        for sub_state_config in self.converter_config[FEATURES_KEY][OBSERVATION_KEY][STATE_KEY][
            SUB_STATE_KEY
        ]:
            sub_state_names.extend(sub_state_config[NAME_KEY])
        self.converter_config[FEATURES_KEY][OBSERVATION_KEY][STATE_KEY][NAME_KEY] = sub_state_names
        self.converter_config[FEATURES_KEY][OBSERVATION_KEY][STATE_KEY][SHAPE_KEY] = (
            len(sub_state_names),
        )
        self.converter_config[FEATURES_KEY][OBSERVATION_KEY][STATE_KEY][LEROBOT_FEATURE_KEY] = (
            f"{OBSERVATION_KEY}.{STATE_KEY}"
        )

    def _gen_action_configs(self) -> None:
        sub_action_names = []
        for sub_action_config in self.converter_config[FEATURES_KEY][ACTION_KEY][SUB_ACTION_KEY]:
            sub_action_names.extend(sub_action_config[NAME_KEY])
        self.converter_config[FEATURES_KEY][ACTION_KEY][NAME_KEY] = sub_action_names

        self.converter_config[FEATURES_KEY][ACTION_KEY][SHAPE_KEY] = (len(sub_action_names),)

        self.converter_config[FEATURES_KEY][ACTION_KEY][LEROBOT_FEATURE_KEY] = ACTION_KEY

    def _get_frame_images(
        self, task_path: Path, ep_idx: int, frame_idx: int, images_buffer: any
    ) -> dict[str, np.ndarray]:
        images = {}
        for image_config in self.converter_config[FEATURES_KEY][OBSERVATION_KEY][IMAGE_KEY]:
            try:
                lerobot_feature = image_config[LEROBOT_FEATURE_KEY]
                args_dict = image_config[ARGS_KEY]
                image = self._get_frame_image(
                    task_path=task_path,
                    ep_idx=ep_idx,
                    frame_idx=frame_idx,
                    args_dict=args_dict,
                    images_buffer=images_buffer,
                )
                
                # 验证图像数据
                if not isinstance(image, np.ndarray):
                    raise TypeError(
                        f"❌ Invalid image data type\n"
                        f"   🎥 Camera: {args_dict.get(CAM_NAME_KEY, 'unknown')}\n"
                        f"   📁 Location: task={task_path.name}, ep={ep_idx}, frame={frame_idx}\n"
                        f"   💡 Expected: numpy.ndarray, Got: {type(image).__name__}"
                    )
                
                if image.size == 0:
                    raise ValueError(
                        f"❌ Empty image data\n"
                        f"   🎥 Camera: {args_dict.get(CAM_NAME_KEY, 'unknown')}\n"
                        f"   📁 Location: task={task_path.name}, ep={ep_idx}, frame={frame_idx}\n"
                        f"   📐 Image shape: {image.shape}\n"
                        f"   💡 Image has no pixels - source may be corrupted"
                    )
                
                if len(image.shape) != 3 or image.shape[2] != 3:
                    self.logger.warning(
                        f"⚠️ Unexpected image shape\n"
                        f"   🎥 Camera: {args_dict.get(CAM_NAME_KEY, 'unknown')}\n"
                        f"   📁 Location: task={task_path.name}, ep={ep_idx}, frame={frame_idx}\n"
                        f"   📐 Expected shape: (H, W, 3), Got: {image.shape}"
                    )
                
                images[lerobot_feature] = image
            except Exception as e:  # noqa: PERF203
                raise Exception(f"Failed to get frame images for {lerobot_feature} failed") from e

        return images

    def _get_frame_states(
        self, task_path: Path, ep_idx: int, frame_idx: int, states_buffer: any = None
    ) -> dict[str, np.ndarray]:
        lerobot_feature = self.converter_config[FEATURES_KEY][OBSERVATION_KEY][STATE_KEY][
            LEROBOT_FEATURE_KEY
        ]

        sub_states_datas: list[np.ndarray] = []
        for state_config in self.converter_config[FEATURES_KEY][OBSERVATION_KEY][STATE_KEY][
            SUB_STATE_KEY
        ]:
            args_dict = state_config[ARGS_KEY]
            sub_states_data = self._get_frame_sub_states(
                task_path=task_path,
                ep_idx=ep_idx,
                frame_idx=frame_idx,
                args_dict=args_dict,
                sub_states_buffer=states_buffer,
            )
            if CONVERT_FUNC_KEY in state_config:
                if state_config[CONVERT_FUNC_KEY] in spatial_covertor_funcs:
                    if spatial_covertor_funcs[state_config[CONVERT_FUNC_KEY]]:
                        sub_states_data = spatial_covertor_funcs[state_config[CONVERT_FUNC_KEY]](
                            sub_states_data
                        ).astype(np.float32)

            sub_states_datas.append(sub_states_data)

        # 检查所有 sub_states 的维度是否一致
        try:
            return {lerobot_feature: np.concatenate(sub_states_datas)}
        except ValueError as e:
            # 提供详细的维度信息
            shapes_info = []
            for idx, data in enumerate(sub_states_datas):
                state_config = self.converter_config[FEATURES_KEY][OBSERVATION_KEY][STATE_KEY][SUB_STATE_KEY][idx]
                names = state_config.get('names', ['unknown'])
                args = state_config.get(ARGS_KEY, {})
                shapes_info.append(f"   [{idx}] {names[0]}: shape={data.shape}, ndim={data.ndim}, dtype={data.dtype}, args={args}")
            
            shapes_str = "\n".join(shapes_info)
            raise ValueError(
                f"❌ Cannot concatenate sub_states due to dimension mismatch.\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                f"   📊 Sub-states dimensions:\n"
                f"{shapes_str}\n"
                f"   ❌ Original error: {str(e)}\n"
                f"   💡 All sub_states must have the same number of dimensions (ndim)\n"
                f"   💡 Most likely cause: One sub_state returns 2D array instead of 1D\n"
                f"   💡 Solution: Ensure all _get_frame_sub_states() return 1D arrays"
            ) from e

    def _get_frame_actions(
        self, task_path: Path, ep_idx: int, frame_idx: int, actions_buffer: any = None
    ) -> dict[str, np.ndarray]:
        lerobot_feature = self.converter_config[FEATURES_KEY][ACTION_KEY][LEROBOT_FEATURE_KEY]
        
        # Apply timeline_offset to get action from a future frame
        timeline_offset = self.converter_config[FEATURES_KEY][ACTION_KEY].get(TIMELINE_OFFSET_KEY, 0)
        action_frame_idx = frame_idx + timeline_offset
        
        sub_actions_datas: list[np.ndarray] = []
        for action_config in self.converter_config[FEATURES_KEY][ACTION_KEY][SUB_ACTION_KEY]:
            args_dict = action_config[ARGS_KEY]
            sub_actions_data = self._get_frame_sub_actions(
                task_path=task_path,
                ep_idx=ep_idx,
                frame_idx=action_frame_idx,  # Use offset frame index for actions
                args_dict=args_dict,
                sub_actions_buffer=actions_buffer,
            )

            if CONVERT_FUNC_KEY in action_config:
                if action_config[CONVERT_FUNC_KEY] in spatial_covertor_funcs:
                    if spatial_covertor_funcs[action_config[CONVERT_FUNC_KEY]]:
                        sub_actions_data = spatial_covertor_funcs[action_config[CONVERT_FUNC_KEY]](
                            sub_actions_data
                        ).astype(np.float32)
            sub_actions_datas.append(sub_actions_data)

        # 检查所有 sub_actions 的维度是否一致
        try:
            return {lerobot_feature: np.concatenate(sub_actions_datas)}
        except ValueError as e:
            # 提供详细的维度信息
            shapes_info = []
            for idx, data in enumerate(sub_actions_datas):
                action_config = self.converter_config[FEATURES_KEY][ACTION_KEY][SUB_ACTION_KEY][idx]
                names = action_config.get('names', ['unknown'])
                args = action_config.get(ARGS_KEY, {})
                shapes_info.append(f"   [{idx}] {names[0]}: shape={data.shape}, ndim={data.ndim}, dtype={data.dtype}, args={args}")
            
            shapes_str = "\n".join(shapes_info)
            raise ValueError(
                f"❌ Cannot concatenate sub_actions due to dimension mismatch.\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                f"   📊 Sub-actions dimensions:\n"
                f"{shapes_str}\n"
                f"   ❌ Original error: {str(e)}\n"
                f"   💡 All sub_actions must have the same number of dimensions (ndim)\n"
                f"   💡 Most likely cause: One sub_action returns 2D array instead of 1D\n"
                f"   💡 Solution: Ensure all _get_frame_sub_actions() return 1D arrays"
            ) from e

    def _get_lerobot_datas(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        images_buffer: any = None,
        states_buffer: any = None,
        actions_buffer: any = None,
    ) -> dict[str, np.ndarray]:
        return {
            **self._get_frame_images(
                task_path=task_path,
                ep_idx=ep_idx,
                frame_idx=frame_idx,
                images_buffer=images_buffer,
            ),
            **self._get_frame_states(
                task_path=task_path,
                ep_idx=ep_idx,
                frame_idx=frame_idx,
                states_buffer=states_buffer,
            ),
            **self._get_frame_actions(
                task_path=task_path,
                ep_idx=ep_idx,
                frame_idx=frame_idx,
                actions_buffer=actions_buffer,
            ),
        }

    def _prepare_episode_buffers(self, task_path: Path, ep_idx: int) -> tuple[any, any, any]:
        return (
            self._prepare_episode_images_buffer(task_path=task_path, ep_idx=ep_idx),
            self._prepare_episode_states_buffer(task_path=task_path, ep_idx=ep_idx),
            self._prepare_episode_actions_buffer(task_path=task_path, ep_idx=ep_idx),
        )

    def _get_lerobot_image_features(self) -> dict:
        lerobot_image_features = {}
        for image_config in self.converter_config[FEATURES_KEY][OBSERVATION_KEY][IMAGE_KEY]:
            leroot_feature_key = image_config[LEROBOT_FEATURE_KEY]
            image_feature = {}
            image_feature[DTYPE_KEY] = image_config[DTYPE_KEY]
            image_feature[SHAPE_KEY] = image_config[SHAPE_KEY]
            image_feature[NAME_KEY] = image_config[NAME_KEY]
            lerobot_image_features[leroot_feature_key] = image_feature
        return lerobot_image_features

    def _get_lerobot_state_feature(self) -> dict:
        lerobot_state_feature = {}
        lerobot_feature_key = self.converter_config[FEATURES_KEY][OBSERVATION_KEY][STATE_KEY][
            LEROBOT_FEATURE_KEY
        ]
        state_feature = {}
        state_feature[DTYPE_KEY] = FLOAT32
        state_feature[SHAPE_KEY] = self.converter_config[FEATURES_KEY][OBSERVATION_KEY][STATE_KEY][
            SHAPE_KEY
        ]
        state_feature[NAME_KEY] = self.converter_config[FEATURES_KEY][OBSERVATION_KEY][STATE_KEY][
            NAME_KEY
        ]
        lerobot_state_feature[lerobot_feature_key] = state_feature
        return lerobot_state_feature

    def _get_lerobot_action_feature(self) -> dict:
        lerobot_action_feature = {}
        lerobot_feature_key = self.converter_config[FEATURES_KEY][ACTION_KEY][LEROBOT_FEATURE_KEY]
        action_feature = {}
        action_feature[DTYPE_KEY] = FLOAT32
        action_feature[SHAPE_KEY] = self.converter_config[FEATURES_KEY][ACTION_KEY][SHAPE_KEY]
        action_feature[NAME_KEY] = self.converter_config[FEATURES_KEY][ACTION_KEY][NAME_KEY]
        lerobot_action_feature[lerobot_feature_key] = action_feature
        return lerobot_action_feature

    def _get_lerobot_features(self) -> dict:
        return {
            **self._get_lerobot_image_features(),
            **self._get_lerobot_state_feature(),
            **self._get_lerobot_action_feature(),
        }

    def _create_lerobot_dataset(self) -> LeRobotDataset:
        return LeRobotDataset.create(
            repo_id=self.repo_id,
            features=self._get_lerobot_features(),
            fps=self.fps,
            robot_type=self.device_model,
            root=self.output_path,
            video_backend=self.video_backend,
            image_writer_processes=self.image_writer_processes,
            image_writer_threads=self.image_writer_threads,
        )

    def _get_episode_task(self, ep_idx: int) -> str:
        return ""

    def _gen_episode_frames(
        self,
        task_path: Path,
        ep_idx: int,
        images_buffer: any = None,
        states_buffer: any = None,
        actions_buffer: any = None,
    ) -> Iterable[dict]:
        total_frames = self._get_episode_frames_num(task_path=task_path, ep_idx=ep_idx)
        
        # Get timeline_offset from action config to determine how many frames to generate
        timeline_offset = self.converter_config[FEATURES_KEY][ACTION_KEY].get(TIMELINE_OFFSET_KEY, 0)
        
        # When timeline_offset > 0, we need to stop earlier to avoid accessing frames beyond the episode
        # For example, if timeline_offset=1, we can only use frames 0 to total_frames-2,
        # because frame total_frames-1 would need to access frame total_frames (which doesn't exist)
        max_frame_idx = total_frames - timeline_offset if timeline_offset > 0 else total_frames
        
        for frame_idx in range(max_frame_idx):
            try:
                frame_data = self._gen_episode_frame(
                    task_path, ep_idx, frame_idx, images_buffer, states_buffer, actions_buffer
                )
            except Exception as e:
                if self.logger:
                    self.logger.error(
                        f"Error generating frame data: task_path={task_path}, "
                        f"episode={ep_idx}, frame={frame_idx}/{max_frame_idx}, "
                        f"timeline_offset={timeline_offset}. Error: {e}"
                    )
                raise RuntimeError(
                    f"Failed to generate frame at task_path={task_path}, "
                    f"episode={ep_idx}, frame={frame_idx}/{max_frame_idx} "
                    f"(timeline_offset={timeline_offset})"
                ) from e
            yield frame_data

        pass

    def convert(self, is_test: bool = False) -> Iterable[tuple[str, int, int]]:
        dataset = None
        try:
            if not is_test:
                dataset = self._create_lerobot_dataset()
            ep_idx = 0
            for task_path, task in self.path_task_dict.items():
                episodes_num = self._get_task_episodes_num(task_path)
                if is_test:
                    episodes_num = 1
                for task_ep_idx in range(episodes_num):
                    try:
                        images_buffer, states_buffer, actions_buffer = self._prepare_episode_buffers(
                            task_path, task_ep_idx
                        )
                        for frame_data in self._gen_episode_frames(
                            task_path, task_ep_idx, images_buffer, states_buffer, actions_buffer
                        ):
                            try:
                                lerobot_datas = self._get_lerobot_datas(
                                    task_path=task_path,
                                    ep_idx=task_ep_idx,
                                    frame_idx=frame_data[FRAME_IDX_KEY],
                                    images_buffer=images_buffer,
                                    states_buffer=states_buffer,
                                    actions_buffer=actions_buffer,
                                )

                                if not is_test:
                                    dataset.add_frame(
                                        frame=lerobot_datas,
                                        task=task,
                                    )
                            except Exception as e:  # noqa: PERF203
                                if self.logger:
                                    self.logger.error(
                                        f"Failed to process frame: task_path={task_path}, "
                                        f"episode={task_ep_idx}, frame={frame_data[FRAME_IDX_KEY]}. "
                                        f"Error: {e}"
                                    )
                                raise RuntimeError(
                                    f"Failed to process frame {frame_data[FRAME_IDX_KEY]} "
                                    f"of episode {task_ep_idx} at task_path={task_path}"
                                ) from e

                        if not is_test:
                            try:
                                dataset.save_episode()
                            except OSError as e:
                                # 特别处理图像文件损坏的情况
                                error_msg = str(e)
                                if "unrecognized data stream" in error_msg or "image file" in error_msg.lower():
                                    if self.logger:
                                        self.logger.error(
                                            f"❌ Image file corruption detected during episode encoding\n"
                                            f"   📁 Task path: {task_path}\n"
                                            f"   📊 Episode: {task_ep_idx} (global: {ep_idx})\n"
                                            f"   💡 One or more image files are corrupted or invalid\n"
                                            f"   🔍 Check temporary image files in output directory\n"
                                            f"   Original error: {error_msg}"
                                        )
                                    raise RuntimeError(
                                        f"❌ Corrupted image file(s) in episode {task_ep_idx} (global: {ep_idx})\n"
                                        f"   📁 Task: {task_path}\n"
                                        f"   💡 Possible causes:\n"
                                        f"      1. Source image/video files are corrupted\n"
                                        f"      2. Disk I/O error during frame extraction\n"
                                        f"      3. Insufficient disk space\n"
                                        f"   🔧 Suggested actions:\n"
                                        f"      1. Verify source data integrity\n"
                                        f"      2. Check disk space and permissions\n"
                                        f"      3. Re-run conversion for this episode"
                                    ) from e
                                raise
                            except Exception as e:
                                if self.logger:
                                    self.logger.error(
                                        f"Failed to save episode: task_path={task_path}, "
                                        f"episode={task_ep_idx}, global_ep_idx={ep_idx}. "
                                        f"Error: {e}"
                                    )
                                raise RuntimeError(
                                    f"Failed to save episode {task_ep_idx} (global episode {ep_idx}) "
                                    f"at task_path={task_path}"
                                ) from e
                        
                        # Collect source file mapping information
                        source_files = self._get_episode_source_files(task_path, task_ep_idx)
                        self.episode_source_mapping[ep_idx] = {
                            "task": task,
                            "task_path": str(task_path),
                            "task_ep_idx": task_ep_idx,
                            "global_ep_idx": ep_idx,
                            "source_files": source_files,
                        }
                        
                        yield (task, task_ep_idx, ep_idx)
                        ep_idx += 1
                    except Exception as e:  # noqa: PERF203
                        if self.logger:
                            self.logger.error(
                                f"Failed to process episode: task_path={task_path}, "
                                f"episode={task_ep_idx}, global_ep_idx={ep_idx}. "
                                f"Error: {e}"
                            )
                        raise RuntimeError(
                            f"Failed to process episode {task_ep_idx} (global episode {ep_idx}) "
                            f"at task_path={task_path}"
                        ) from e
        finally:
            # 清理资源：确保 LeRobotDataset 内部的异步 image writer 和其他多进程资源被释放
            if dataset is not None:
                try:
                    if self.logger:
                        self.logger.info("Cleaning up dataset resources...")

                    # 1) Stop image writer if available (this will stop processes/threads used for async image writing)
                    if hasattr(dataset, "stop_image_writer"):
                        try:
                            dataset.stop_image_writer()
                            if self.logger:
                                self.logger.info("✅ Dataset image writer stopped")
                        except Exception as e:
                            if self.logger:
                                self.logger.warning(f"⚠️ Error while stopping image writer: {e}")

                    # 2) Wait for image writer to finish if such a method exists
                    if hasattr(dataset, "_wait_image_writer"):
                        try:
                            dataset._wait_image_writer()
                            if self.logger:
                                self.logger.info("✅ Image writer joined successfully")
                        except Exception as e:
                            if self.logger:
                                self.logger.warning(f"⚠️ Error while waiting for image writer: {e}")

                    # 3) Call consolidate() if available (legacy API in some forks)
                    if hasattr(dataset, "consolidate"):
                        try:
                            dataset.consolidate()
                            if self.logger:
                                self.logger.info("✅ Dataset consolidated successfully")
                        except Exception as e:
                            if self.logger:
                                self.logger.warning(f"⚠️ Error during dataset consolidate: {e}")

                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"⚠️ General error during dataset cleanup: {e}")

    def save_episode_source_mapping(self, mapping_filename: str = "episode_source_mapping.json") -> None:
        """保存 episode 源文件映射到 JSON 文件
        
        生成的文件将与 meta.json, info.json 等文件同级，位于转换后的数据集根目录
        
        Args:
            mapping_filename: 映射文件名，默认为 "episode_source_mapping.json"
        """
        import json
        
        mapping_file = self.output_path / mapping_filename
        
        # 转换为更易读的格式
        formatted_mapping = {
            "dataset_info": {
                "source_dataset_path": str(self.dataset_path),
                "output_dataset_path": str(self.output_path),
                "repo_id": self.repo_id,
                "device_model": self.device_model,
                "total_episodes": len(self.episode_source_mapping),
            },
            "episodes": []
        }
        
        # 按 global_ep_idx 排序
        for ep_idx in sorted(self.episode_source_mapping.keys()):
            ep_info = self.episode_source_mapping[ep_idx]
            formatted_mapping["episodes"].append({
                "global_episode_index": ep_info["global_ep_idx"],
                "task": ep_info["task"],
                "task_episode_index": ep_info["task_ep_idx"],
                "task_path": ep_info["task_path"],
                "source_files": ep_info["source_files"],
            })
        
        with open(mapping_file, 'w', encoding='utf-8') as f:
            json.dump(formatted_mapping, f, indent=2, ensure_ascii=False)
        
        if self.logger:
            self.logger.info(f"✅ Episode source mapping saved to: {mapping_file}")
            self.logger.info(f"   Total episodes mapped: {len(self.episode_source_mapping)}")

    def get_episodes_num(self) -> int:
        return sum(self._get_task_episodes_num(task) for task in self.path_task_dict.keys())


class LerobotFormatConverterFactory:
    @staticmethod
    def create_converter(
        dataset_path: Path,
        device_model: str,
        output_path: Path,
        converter_config: dict,
        converter_module_path: str,
        converter_class_name: str,
        repo_id: str,
        video_backend: str = "pyav",
        image_writer_processes: int = 4,
        image_writer_threads: int = 4,
        logger: logging.Logger | None = None,
        converter_log_dir: Path | None = None,
    ) -> LerobotFormatConverter:
        # 确保 dataset_path 是 Path 对象，并处理可能的字符串空格问题
        original_path = dataset_path
        if isinstance(dataset_path, str):
            dataset_path = Path(dataset_path.strip())
        elif isinstance(dataset_path, Path):
            # 如果已经是 Path 对象，重新构造以去除可能的空格
            dataset_path = Path(str(dataset_path).strip())
        
        if not dataset_path.exists():
            # 尝试额外的诊断信息
            parent = dataset_path.parent
            parent_exists = parent.exists() if parent else False
            
            error_msg = (
                f"❌ Dataset path does not exist.\n"
                f"   📁 Requested path: {dataset_path}\n"
                f"   📝 Original input: {repr(original_path)}\n"
                f"   📏 Path length: {len(str(dataset_path))}\n"
                f"   🔤 Path bytes: {str(dataset_path).encode('utf-8')}\n"
            )
            
            if parent_exists:
                try:
                    siblings = list(parent.iterdir())
                    sibling_names = [s.name for s in siblings]
                    target_name = dataset_path.name
                    
                    error_msg += (
                        f"   📂 Parent directory exists: {parent}\n"
                        f"   🎯 Looking for: {repr(target_name)}\n"
                        f"   📋 Available in parent ({len(sibling_names)} items):\n"
                    )
                    
                    # 显示前10个
                    for name in sibling_names[:10]:
                        match_indicator = "✅" if name == target_name else "  "
                        error_msg += f"      {match_indicator} {repr(name)}\n"
                    
                    if len(sibling_names) > 10:
                        error_msg += f"      ... and {len(sibling_names) - 10} more\n"
                    
                    # 尝试找相似的名字
                    similar = [n for n in sibling_names if target_name in n or n in target_name]
                    if similar and target_name not in sibling_names:
                        error_msg += f"   🔍 Similar names found: {similar}\n"
                        
                except Exception as e:
                    error_msg += f"   ⚠️ Could not list parent directory: {e}\n"
            else:
                error_msg += f"   ❌ Parent directory does not exist: {parent}\n"
            
            error_msg += (
                "   💡 Possible causes:\n"
                "      1. Path contains trailing/leading spaces\n"
                "      2. Path contains invisible Unicode characters\n"
                "      3. Database path is outdated or incorrect\n"
                "      4. File was moved or deleted\n"
            )
            
            raise FileNotFoundError(error_msg)

        # Create logger from converter_log_dir if provided and logger is None
        if logger is None and converter_log_dir is not None:
            from robocoin_dataset.utils.logger import setup_logger

            logger = setup_logger(
                name="lerobot_format_converter", log_dir=converter_log_dir, level=logging.INFO
            )

        module = importlib.import_module(converter_module_path)
        convertor_class = getattr(module, converter_class_name)
        return convertor_class(
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
