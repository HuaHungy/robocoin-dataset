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
        strict_episodes: int = 3,
        failure_threshold: float = 0.8,
        min_valid_frame_ratio: float = 0.5,
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

        # Fault tolerance configuration
        self.strict_episodes = strict_episodes  # 前N个episode使用严格模式
        self.failure_threshold = failure_threshold  # 失败率阈值，超过则认为是配置错误
        self.min_valid_frame_ratio = min_valid_frame_ratio  # episode最小有效帧比例
        
        # Conversion statistics
        self._conversion_stats = {
            'total_episodes': 0,
            'successful_episodes': 0,
            'skipped_episodes': 0,
            'total_frames': 0,
            'skipped_frames': 0,
            'skip_details': [],
        }

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

    def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int, is_test: bool = False) -> any:
        """Prepare images buffer for an episode.
        
        Args:
            task_path: Path to the task directory
            ep_idx: Episode index
            is_test: Whether in test mode (子类可选实现优化)
            
        Returns:
            Images buffer (format depends on subclass implementation)
        """
        return None

    def _prepare_episode_states_buffer(self, task_path: Path, ep_idx: int, is_test: bool = False) -> any:
        """Prepare states buffer for an episode.
        
        Args:
            task_path: Path to the task directory
            ep_idx: Episode index
            is_test: Whether in test mode (子类可选实现优化)
            
        Returns:
            States buffer (format depends on subclass implementation)
        """
        return None

    def _prepare_episode_actions_buffer(self, task_path: Path, ep_idx: int, is_test: bool = False) -> any:
        """Prepare actions buffer for an episode.
        
        Args:
            task_path: Path to the task directory
            ep_idx: Episode index
            is_test: Whether in test mode (子类可选实现优化)
            
        Returns:
            Actions buffer (format depends on subclass implementation)
        """
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

        return {lerobot_feature: np.concatenate(sub_states_datas)}

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

        return {lerobot_feature: np.concatenate(sub_actions_datas)}

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

    def _prepare_episode_buffers(self, task_path: Path, ep_idx: int, is_test: bool = False) -> tuple[any, any, any]:
        """Prepare all buffers for an episode.
        
        智能调用子类方法：如果子类方法支持 is_test 参数则传入，否则只传基本参数。
        这样保证了向后兼容性 - 旧的子类实现不需要修改。
        """
        import inspect
        from collections.abc import Callable
        
        # 检查子类方法是否接受 is_test 参数
        images_method = self._prepare_episode_images_buffer
        states_method = self._prepare_episode_states_buffer
        actions_method = self._prepare_episode_actions_buffer
        
        # 智能调用：检查方法签名
        def smart_call(method: Callable, task_path: Path, ep_idx: int, is_test: bool) -> any:
            sig = inspect.signature(method)
            if 'is_test' in sig.parameters:
                return method(task_path=task_path, ep_idx=ep_idx, is_test=is_test)
            return method(task_path=task_path, ep_idx=ep_idx)
        
        return (
            smart_call(images_method, task_path, ep_idx, is_test),
            smart_call(states_method, task_path, ep_idx, is_test),
            smart_call(actions_method, task_path, ep_idx, is_test),
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
        
        # Check if episode should be skipped (indicated by total_frames == -1)
        # This happens when data quality issues are detected and file is auto-moved to error/
        if total_frames == -1:
            if self.logger:
                self.logger.info(
                    f"⏭️  Skipping episode {ep_idx} at {task_path.name} "
                    f"(auto-moved to error/ due to data quality issues)"
                )
            return  # Return empty iterator to skip this episode
        
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

    def _convert_episode_with_fault_tolerance(
        self,
        dataset: LeRobotDataset,
        task_path: Path,
        task: str,
        task_ep_idx: int,
        global_ep_idx: int,
        is_strict: bool,
        is_test: bool,
    ) -> tuple[int, int]:
        """转换单个episode，支持episode级容错
        
        重要：为了保持时序数据的连续性，任何单帧错误都会导致整个episode被跳过。
        这是因为跳过单帧会破坏observation-action的时间对齐关系。
        
        Args:
            dataset: LeRobot数据集对象
            task_path: 任务路径
            task: 任务名称
            task_ep_idx: 任务内episode索引
            global_ep_idx: 全局episode索引
            is_strict: 是否为严格模式
            is_test: 是否为测试模式
        
        Returns:
            (converted_frames, 0): 成功转换的帧数（跳过的帧数始终为0，因为要么全转要么全跳）
            
        Raises:
            ConfigError: 严格模式下遇到数据错误（表明配置可能有问题）
            CriticalDataError: 非严格模式下遇到数据错误（跳过整个episode）
        """
        from .exceptions import ConfigError, DataQualityError, CriticalDataError
        
        images_buffer, states_buffer, actions_buffer = self._prepare_episode_buffers(
            task_path, task_ep_idx, is_test=is_test
        )
        
        converted_frames = 0
        
        for frame_data in self._gen_episode_frames(
            task_path, task_ep_idx, images_buffer, states_buffer, actions_buffer
        ):
            frame_idx = frame_data[FRAME_IDX_KEY]
            
            try:
                lerobot_datas = self._get_lerobot_datas(
                    task_path=task_path,
                    ep_idx=task_ep_idx,
                    frame_idx=frame_idx,
                    images_buffer=images_buffer,
                    states_buffer=states_buffer,
                    actions_buffer=actions_buffer,
                )

                if not is_test:
                    dataset.add_frame(frame=lerobot_datas, task=task)
                
                converted_frames += 1
                
            except DataQualityError as e:
                # 数据质量问题：
                # - 严格模式：升级为配置错误，停止整个转换
                # - 非严格模式：升级为严重数据错误，跳过整个episode
                if is_strict:
                    raise ConfigError(
                        f"严格模式下检测到数据质量问题（可能是配置错误）:\n"
                        f"  Episode: {global_ep_idx} (task episode: {task_ep_idx})\n"
                        f"  Frame: {frame_idx}\n"
                        f"  Error: {e}\n"
                        f"\n💡 在前{self.strict_episodes}个episode中发现此问题，"
                        f"可能是配置错误而非数据问题"
                    ) from e
                else:
                    # 非严格模式：跳过整个episode以保持时序连续性
                    raise CriticalDataError(
                        f"Episode {global_ep_idx} 数据质量问题，跳过整个episode:\n"
                        f"  任务: {task}\n"
                        f"  Episode索引: {task_ep_idx}\n"
                        f"  问题帧: {frame_idx}\n"
                        f"  错误: {e}\n"
                        f"\n⚠️  为保持时序连续性，不能跳过单帧，必须跳过整个episode"
                    ) from e
                
            except Exception as e:
                # 未分类的异常：在严格模式下作为配置错误处理
                if is_strict:
                    raise ConfigError(
                        f"严格模式下遇到未预期的错误:\n"
                        f"  Episode: {global_ep_idx} (task episode: {task_ep_idx})\n"
                        f"  Frame: {frame_idx}\n"
                        f"  Error type: {type(e).__name__}\n"
                        f"  Error: {e}"
                    ) from e
                else:
                    # 非严格模式：也升级为CriticalDataError
                    raise CriticalDataError(
                        f"Episode {global_ep_idx} 遇到错误，跳过整个episode:\n"
                        f"  任务: {task}\n"
                        f"  Episode索引: {task_ep_idx}\n"
                        f"  问题帧: {frame_idx}\n"
                        f"  错误类型: {type(e).__name__}\n"
                        f"  错误: {e}"
                    ) from e
        
        # 如果成功遍历所有帧，返回转换的帧数
        # 注意：skipped_frames始终为0，因为我们不支持跳过单帧
        return converted_frames, 0

    def _get_conversion_report(self) -> dict:
        """生成转换报告"""
        stats = self._conversion_stats
        total = stats['total_episodes']
        successful = stats['successful_episodes']
        
        return {
            'dataset': str(self.dataset_path.name),
            'total_episodes_attempted': total,
            'successful_episodes': successful,
            'skipped_episodes': stats['skipped_episodes'],
            'total_frames_converted': stats['total_frames'],
            'total_frames_skipped': stats['skipped_frames'],
            'success_rate': successful / total if total > 0 else 0,
            'skip_details': stats['skip_details'][-50:],  # 只保留最近50条
        }

    def convert(self, is_test: bool = False) -> Iterable[tuple[str, int, int]]:
        """转换数据集，使用智能容错机制
        
        Args:
            is_test: 是否为测试模式（只转换第一个episode）
        
        Yields:
            (task, task_ep_idx, global_ep_idx): 成功转换的episode信息
        
        Raises:
            ConfigError: 检测到配置错误（前N个episode高失败率）
        """
        from .exceptions import ConfigError, CriticalDataError
        
        if not is_test:
            dataset = self._create_lerobot_dataset()
        else:
            dataset = None  # 测试模式不需要数据集对象
        
        global_ep_idx = 0
        task_stats = {}  # 每个task的统计信息
        
        for task_path, task in self.path_task_dict.items():
            episodes_num = self._get_task_episodes_num(task_path)
            if is_test:
                episodes_num = 1
            
            # 初始化任务统计
            task_stats[task] = {
                'attempted': 0,
                'successful': 0,
                'skipped': 0,
                'skipped_frames': 0,
            }
            
            for task_ep_idx in range(episodes_num):
                is_strict = global_ep_idx < self.strict_episodes
                
                # 更新统计
                self._conversion_stats['total_episodes'] += 1
                task_stats[task]['attempted'] += 1
                
                try:
                    converted_frames, skipped_frames = self._convert_episode_with_fault_tolerance(
                        dataset=dataset if not is_test else None,
                        task_path=task_path,
                        task=task,
                        task_ep_idx=task_ep_idx,
                        global_ep_idx=global_ep_idx,
                        is_strict=is_strict,
                        is_test=is_test,
                    )
                    
                    # Episode完全为空，跳过
                    if converted_frames == 0 and skipped_frames == 0:
                        self._conversion_stats['skipped_episodes'] += 1
                        task_stats[task]['skipped'] += 1
                        
                        self._conversion_stats['skip_details'].append({
                            'episode': global_ep_idx,
                            'task': task,
                            'task_episode': task_ep_idx,
                            'reason': 'Empty episode or data quality issue',
                            'skipped_entire_episode': True,
                        })
                        
                        self.logger.info(
                            f"⏭️ 跳过 episode {global_ep_idx} "
                            f"(task: {task}, task_ep: {task_ep_idx}): 空episode"
                        )
                        continue
                    
                    # 更新统计
                    self._conversion_stats['successful_episodes'] += 1
                    self._conversion_stats['total_frames'] += converted_frames
                    self._conversion_stats['skipped_frames'] += skipped_frames
                    task_stats[task]['successful'] += 1
                    task_stats[task]['skipped_frames'] += skipped_frames
                    
                    if skipped_frames > 0:
                        self._conversion_stats['skip_details'].append({
                            'episode': global_ep_idx,
                            'task': task,
                            'task_episode': task_ep_idx,
                            'converted_frames': converted_frames,
                            'skipped_frames': skipped_frames,
                        })
                    
                    # 保存episode
                    if not is_test:
                        dataset.save_episode()
                    
                    # 检查失败率（在严格阶段结束时）
                    if global_ep_idx == self.strict_episodes - 1:
                        self._check_failure_rate_threshold(task_stats)
                    
                    yield (task, task_ep_idx, global_ep_idx)
                    global_ep_idx += 1
                    
                except CriticalDataError as e:
                    # 严重数据错误：跳过整个episode
                    self._conversion_stats['skipped_episodes'] += 1
                    task_stats[task]['skipped'] += 1
                    
                    self._conversion_stats['skip_details'].append({
                        'episode': global_ep_idx,
                        'task': task,
                        'task_episode': task_ep_idx,
                        'reason': str(e),
                        'skipped_entire_episode': True,
                    })
                    
                    self.logger.warning(
                        f"⏭️ 跳过 episode {global_ep_idx} "
                        f"(task: {task}, task_ep: {task_ep_idx}): {e}"
                    )
                    continue
                    
                except ConfigError:
                    # 配置错误：立即停止
                    self.logger.error("检测到配置错误，停止转换")
                    raise
                    
                except Exception as e:
                    # 其他未处理的异常
                    self.logger.error(
                        f"处理episode时发生未预期的错误: "
                        f"task={task}, task_ep={task_ep_idx}, global_ep={global_ep_idx}. "
                        f"Error: {e}"
                    )
                    raise RuntimeError(
                        f"Failed to process episode {task_ep_idx} (global: {global_ep_idx}) "
                        f"at task {task}"
                    ) from e
        
        # 转换完成后打印统计信息
        self._print_conversion_summary(task_stats)

    def _check_failure_rate_threshold(self, task_stats: dict) -> None:
        """检查失败率是否超过阈值
        
        Args:
            task_stats: 任务统计信息
            
        Raises:
            ConfigError: 失败率超过阈值
        """
        from .exceptions import ConfigError
        
        total_attempted = self._conversion_stats['total_episodes']
        total_skipped = self._conversion_stats['skipped_episodes']
        failure_rate = total_skipped / total_attempted if total_attempted > 0 else 0
        
        if failure_rate > self.failure_threshold:
            # 收集详细错误信息
            recent_failures = self._conversion_stats['skip_details'][-self.strict_episodes:]
            
            raise ConfigError(
                f"前{self.strict_episodes}个episode失败率过高，可能存在配置错误:\n"
                f"  尝试转换: {total_attempted} episodes\n"
                f"  跳过: {total_skipped} episodes\n"
                f"  失败率: {failure_rate:.1%}\n"
                f"  阈值: {self.failure_threshold:.1%}\n"
                f"\n最近失败的episodes:\n" +
                "\n".join(
                    f"  - Episode {f['episode']} (task: {f['task']}): {f.get('reason', 'Unknown')}"
                    for f in recent_failures
                ) +
                f"\n\n💡 建议：\n"
                f"  1. 检查配置文件中的字段路径是否正确\n"
                f"  2. 使用 diagnose_converter_config.py 诊断配置\n"
                f"  3. 检查数据集格式是否与配置匹配"
            )

    def _print_conversion_summary(self, task_stats: dict) -> None:
        """打印转换统计摘要"""
        stats = self._conversion_stats
        
        self.logger.info("="*70)
        self.logger.info("转换完成 - 统计摘要")
        self.logger.info("="*70)
        self.logger.info(f"总Episodes: {stats['total_episodes']}")
        self.logger.info(f"成功: {stats['successful_episodes']}")
        self.logger.info(f"跳过: {stats['skipped_episodes']}")
        self.logger.info(f"成功率: {stats['successful_episodes']/stats['total_episodes']*100:.1f}%")
        self.logger.info(f"总帧数: {stats['total_frames']}")
        self.logger.info(f"跳过帧数: {stats['skipped_frames']}")
        
        if task_stats:
            self.logger.info("\n任务详情:")
            for task, task_stat in task_stats.items():
                success_rate = (task_stat['successful'] / task_stat['attempted'] * 100 
                               if task_stat['attempted'] > 0 else 0)
                self.logger.info(
                    f"  {task}: {task_stat['successful']}/{task_stat['attempted']} "
                    f"({success_rate:.1f}%), 跳过帧: {task_stat['skipped_frames']}"
                )
        
        if stats['skip_details']:
            skipped_count = len([d for d in stats['skip_details'] 
                                if d.get('skipped_entire_episode')])
            self.logger.info(f"\n完全跳过的episodes: {skipped_count}")
        
        self.logger.info("="*70)

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
        strict_episodes: int = 3,
        failure_threshold: float = 0.8,
        min_valid_frame_ratio: float = 0.5,
    ) -> LerobotFormatConverter:
        if not dataset_path.exists():
            raise FileNotFoundError(f"Dataset path {dataset_path} does not exist.")

        # Create logger from converter_log_dir if provided and logger is None
        if logger is None and converter_log_dir is not None:
            from robocoin_dataset.utils.logger import setup_logger

            logger = setup_logger(
                name="lerobot_format_converter", log_dir=converter_log_dir, level=logging.INFO
            )

        module = importlib.import_module(converter_module_path)
        convertor_class = getattr(module, converter_class_name)
        
        # 构建基础参数
        init_kwargs = {
            'dataset_path': dataset_path,
            'output_path': output_path,
            'converter_config': converter_config,
            'repo_id': repo_id,
            'device_model': device_model,
            'logger': logger,
            'video_backend': video_backend,
            'image_writer_processes': image_writer_processes,
            'image_writer_threads': image_writer_threads,
        }
        
        # 检查子类是否支持新的容错参数（向后兼容）
        import inspect
        sig = inspect.signature(convertor_class.__init__)
        
        if 'strict_episodes' in sig.parameters:
            init_kwargs['strict_episodes'] = strict_episodes
        if 'failure_threshold' in sig.parameters:
            init_kwargs['failure_threshold'] = failure_threshold
        if 'min_valid_frame_ratio' in sig.parameters:
            init_kwargs['min_valid_frame_ratio'] = min_valid_frame_ratio
        
        return convertor_class(**init_kwargs)
