from pathlib import Path

import numpy as np

from .state_action_data_processor_base import StateActionDataPostProcessorBase


class RuantongA2dProcessor(StateActionDataPostProcessorBase):
    def __init__(self, convert_path: str | Path) -> None:
        super().__init__(convert_path)

    def prepare_processing(self) -> None:
        pass

    def _smooth_gripper_open_data(self, data: np.ndarray) -> np.ndarray:
        smoothed = data.copy()
        return smoothed

    # 该方法将ori_state_data进行后处理，返回结果为后处理后的数据
    def process_episode_state_data(self, ori_state_data: np.ndarray) -> np.ndarray:
        new_state_data = ori_state_data.copy()
        return new_state_data

    # 该方法将ori_action_data进行后处理，返回结果为后处理后的数据
    def process_episode_action_data(self, ori_action_data: np.ndarray) -> np.ndarray:
        new_action_data = ori_action_data.copy()
        return new_action_data
    def get_modified_feature_names(self):
        return super().get_modified_feature_names()

    def get_modified_info_state_names(self) -> dict[str, str]:
        return {}

    # 该方法返回处理后的action数据名称
    def get_modified_info_action_names(self) -> dict[str, str]:
        return {}

class RuantongA2dGt02Processor(StateActionDataPostProcessorBase):
    def __init__(self, convert_path: str | Path) -> None:
        super().__init__(convert_path)

    def prepare_processing(self) -> None:
        pass

    # 该方法将ori_state_data进行后处理，返回结果为后处理后的数据
    def process_episode_state_data(self, ori_state_data: np.ndarray) -> np.ndarray:
        new_state_data = ori_state_data.copy()
        return new_state_data

    # 该方法将ori_action_data进行后处理，返回结果为后处理后的数据
    def process_episode_action_data(self, ori_action_data: np.ndarray) -> np.ndarray:
        new_action_data = ori_action_data.copy()
        return new_action_data
    def get_modified_feature_names(self):
        return super().get_modified_feature_names()

    def get_modified_info_state_names(self) -> dict[str, str]:
        return {}

    # 该方法返回处理后的action数据名称
    def get_modified_info_action_names(self) -> dict[str, str]:
        return {}


    def get_modified_state_feature_names(self) -> list[str]:
        return [
                "robot_joint_3_rad",
                "left_arm_joint_1_rad",
                "left_arm_joint_2_rad",
                "left_arm_joint_3_rad",
                "left_arm_joint_4_rad",
                "left_arm_joint_5_rad",
                "left_arm_joint_6_rad",
                "left_arm_joint_7_rad",
                "right_arm_joint_1_rad",
                "right_arm_joint_2_rad",
                "right_arm_joint_3_rad",
                "right_arm_joint_4_rad",
                "right_arm_joint_5_rad",
                "right_arm_joint_6_rad",
                "right_arm_joint_7_rad",
                "left_effector_open_deg",
                "right_effector_open_deg"
                ]

    def get_modified_action_feature_names(self) -> list[str]:
        return [
                "robot_joint_3_rad",
                "left_arm_joint_1_rad",
                "left_arm_joint_2_rad",
                "left_arm_joint_3_rad",
                "left_arm_joint_4_rad",
                "left_arm_joint_5_rad",
                "left_arm_joint_6_rad",
                "left_arm_joint_7_rad",
                "right_arm_joint_1_rad",
                "right_arm_joint_2_rad",
                "right_arm_joint_3_rad",
                "right_arm_joint_4_rad",
                "right_arm_joint_5_rad",
                "right_arm_joint_6_rad",
                "right_arm_joint_7_rad",
                "left_effector_open_deg",
                "right_effector_open_deg"
                ]

