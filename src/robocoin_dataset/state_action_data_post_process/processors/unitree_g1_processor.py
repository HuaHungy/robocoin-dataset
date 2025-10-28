from pathlib import Path

import numpy as np

from .state_action_data_processor_base import StateActionDataPostProcessorBase


class UnitreeG1Processor(StateActionDataPostProcessorBase):
    def __init__(self, convert_path: str | Path) -> None:
        super().__init__(convert_path)

    def prepare_processing(self) -> None:
        self.left_gripper_open_state_data_idx = 21
        self.right_gripper_open_state_data_idx = 7
        # self.left_gripper_open_action_data_idx = self.left_gripper_open_state_data_idx
        # self.right_gripper_open_action_data_idx = self.right_gripper_open_state_data_idx
        pass

    def _smooth_gripper_open_data(self, data: np.ndarray) -> np.ndarray:
        smoothed = data.copy()
        # start_idx = 0
        # start_val = data[0]

        # for i in range(1, len(data)):
        #     if data[i] != start_val:
        #         end_idx = i
        #         end_val = data[i]
        #         for j in range(start_idx + 1, end_idx):
        #             t = (j - start_idx) / (end_idx - start_idx)
        #             smoothed[j] = start_val + t * (end_val - start_val)
        #         start_idx = i
        #         start_val = data[i]

        return smoothed

    # 该方法将ori_state_data进行后处理，返回结果为后处理后的数据
    def process_episode_state_data(self, ori_state_data: np.ndarray) -> np.ndarray:
        new_state_data = ori_state_data.copy()
        # left_gripper_data = ori_state_data[:, self.left_gripper_open_state_data_idx]
        # right_gripper_data = ori_state_data[:, self.right_gripper_open_state_data_idx]

        # new_left_gripper_data = self._smooth_gripper_open_data(left_gripper_data)
        # new_right_gripper_data = self._smooth_gripper_open_data(right_gripper_data)

        # new_state_data[:, self.left_gripper_open_state_data_idx] = new_left_gripper_data
        # new_state_data[:, self.right_gripper_open_state_data_idx] = new_right_gripper_data

        return new_state_data

    # 该方法将ori_action_data进行后处理，返回结果为后处理后的数据
    def process_episode_action_data(self, ori_action_data: np.ndarray) -> np.ndarray:
        new_action_data = ori_action_data.copy()
        # left_gripper_data = ori_action_data[:, self.left_gripper_open_action_data_idx]
        # right_gripper_data = ori_action_data[:, self.right_gripper_open_action_data_idx]

        # new_left_gripper_data = self._smooth_gripper_open_data(left_gripper_data)
        # new_right_gripper_data = self._smooth_gripper_open_data(right_gripper_data)

        # new_action_data[:, self.left_gripper_open_action_data_idx] = new_left_gripper_data
        # new_action_data[:, self.right_gripper_open_action_data_idx] = new_right_gripper_data

        return new_action_data

    # 该方法返回处理后的state数据名称
    def get_modified_feature_names(self):
        return super().get_modified_feature_names()

    def get_modified_info_state_names(self) -> dict[str, str]:
        return {}

    # 该方法返回处理后的action数据名称
    def get_modified_info_action_names(self) -> dict[str, str]:
        return {}






class UnitreeG1FiveFingerHandProcessor(StateActionDataPostProcessorBase):
    def __init__(self, convert_path: str | Path) -> None:
        super().__init__(convert_path)

    def prepare_processing(self) -> None:
        self.left_gripper_open_state_data_idx = 21
        self.right_gripper_open_state_data_idx = 7
        # self.left_gripper_open_action_data_idx = self.left_gripper_open_state_data_idx
        # self.right_gripper_open_action_data_idx = self.right_gripper_open_state_data_idx
        pass

    def _smooth_gripper_open_data(self, data: np.ndarray) -> np.ndarray:
        smoothed = data.copy()
        # start_idx = 0
        # start_val = data[0]

        # for i in range(1, len(data)):
        #     if data[i] != start_val:
        #         end_idx = i
        #         end_val = data[i]
        #         for j in range(start_idx + 1, end_idx):
        #             t = (j - start_idx) / (end_idx - start_idx)
        #             smoothed[j] = start_val + t * (end_val - start_val)
        #         start_idx = i
        #         start_val = data[i]

        return smoothed

    # 该方法将ori_state_data进行后处理，返回结果为后处理后的数据
    def process_episode_state_data(self, ori_state_data: np.ndarray) -> np.ndarray:
        new_state_data = ori_state_data.copy()
        # left_gripper_data = ori_state_data[:, self.left_gripper_open_state_data_idx]
        # right_gripper_data = ori_state_data[:, self.right_gripper_open_state_data_idx]

        # new_left_gripper_data = self._smooth_gripper_open_data(left_gripper_data)
        # new_right_gripper_data = self._smooth_gripper_open_data(right_gripper_data)

        # new_state_data[:, self.left_gripper_open_state_data_idx] = new_left_gripper_data
        # new_state_data[:, self.right_gripper_open_state_data_idx] = new_right_gripper_data

        return new_state_data

    # 该方法将ori_action_data进行后处理，返回结果为后处理后的数据
    def process_episode_action_data(self, ori_action_data: np.ndarray) -> np.ndarray:
        new_action_data = ori_action_data.copy()
        # left_gripper_data = ori_action_data[:, self.left_gripper_open_action_data_idx]
        # right_gripper_data = ori_action_data[:, self.right_gripper_open_action_data_idx]

        # new_left_gripper_data = self._smooth_gripper_open_data(left_gripper_data)
        # new_right_gripper_data = self._smooth_gripper_open_data(right_gripper_data)

        # new_action_data[:, self.left_gripper_open_action_data_idx] = new_left_gripper_data
        # new_action_data[:, self.right_gripper_open_action_data_idx] = new_right_gripper_data

        return new_action_data

    # 该方法返回处理后的state数据名称
    def get_modified_feature_names(self):
        return super().get_modified_feature_names()

    def get_modified_info_state_names(self) -> dict[str, str]:
        return {}

    # 该方法返回处理后的action数据名称
    def get_modified_info_action_names(self) -> dict[str, str]:
        return {}

