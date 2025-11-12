from pathlib import Path

import numpy as np
import pandas as pd

from .state_action_data_processor_base import StateActionDataPostProcessorBase


class RuantongA2dProcessor(StateActionDataPostProcessorBase):
    def __init__(self, convert_path: str | Path) -> None:
        super().__init__(convert_path)

    def prepare_processing(self) -> None:
        pass

    def _smooth_data(self, data: np.ndarray, window_size: int = 8) -> np.ndarray:
        """
        对数据进行平滑滤波
        
        Args:
            data: 输入数据，shape 为 (n_frames, n_features)
            window_size: 滑动窗口大小
            
        Returns:
            平滑后的数据
        """
        if data.shape[0] < window_size:
            # 如果数据长度小于窗口大小，直接返回原数据
            return data
        
        smoothed_data = np.zeros_like(data)
        for i in range(data.shape[1]):
            series = pd.Series(data[:, i])
            smoothed_series = series.rolling(window=window_size, min_periods=1, center=True).mean()
            smoothed_data[:, i] = smoothed_series.values
        
        return smoothed_data

    # 该方法将ori_state_data进行后处理，返回结果为后处理后的数据
    def process_episode_state_data(self, ori_state_data: np.ndarray) -> np.ndarray:
        new_state_data = ori_state_data.copy()
        # 应用平滑滤波
        new_state_data = self._smooth_data(new_state_data, window_size=16)
        new_state_data[:, 32] = (140.0 - new_state_data[:, 32]) / 105.0
        new_state_data[:, 33] = (140.0 - new_state_data[:, 33]) / 105.0
        return new_state_data

    # 该方法将ori_action_data进行后处理，返回结果为后处理后的数据
    def process_episode_action_data(self, ori_action_data: np.ndarray) -> np.ndarray:
        new_action_data = ori_action_data.copy()
        # 应用平滑滤波
        new_action_data = self._smooth_data(new_action_data, window_size=8)
        new_action_data[:, 32] = (1.0 - new_action_data[:, 32])
        new_action_data[:, 33] = (1.0 - new_action_data[:, 33])
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
                "left_end_pos_x_m",
                "left_end_pos_y_m",
                "left_end_pos_z_m",
                "left_end_quat_x",
                "left_end_quat_y",
                "left_end_quat_z",
                "left_end_quat_w",
                "right_end_pos_x_m",
                "right_end_pos_y_m",
                "right_end_pos_z_m",
                "right_end_quat_x",
                "right_end_quat_y",
                "right_end_quat_z",
                "right_end_quat_w",
                "waist_yaw_rad",
                "waist_pitch_rad",
                "head_yaw_rad",
                "head_pitch_rad",
                "left_gripper_open",
                "right_gripper_open",
                "robot_pos_x_m",
                "robot_pos_y_m",
                "robot_pos_z_m",
                "robot_quat_x",
                "robot_quat_y",
                "robot_quat_z",
                "robot_quat_w"
            ]

    def get_modified_action_feature_names(self) -> list[str]:
        return [
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
                "left_end_pos_x_m",
                "left_end_pos_y_m",
                "left_end_pos_z_m",
                "left_end_quat_x",
                "left_end_quat_y",
                "left_end_quat_z",
                "left_end_quat_w",
                "right_end_pos_x_m",
                "right_end_pos_y_m",
                "right_end_pos_z_m",
                "right_end_quat_x",
                "right_end_quat_y",
                "right_end_quat_z",
                "right_end_quat_w",
                "waist_yaw_rad",
                "waist_pitch_rad",
                "head_yaw_rad",
                "head_pitch_rad",
                "left_gripper_open",
                "right_gripper_open"
            ]


class RuantongA2dGt02Processor(StateActionDataPostProcessorBase):
    def __init__(self, convert_path: str | Path) -> None:
        super().__init__(convert_path)

    def prepare_processing(self) -> None:
        pass

    def _smooth_data(self, data: np.ndarray, window_size: int = 8) -> np.ndarray:
        """
        对数据进行平滑滤波
        
        Args:
            data: 输入数据，shape 为 (n_frames, n_features)
            window_size: 滑动窗口大小
            
        Returns:
            平滑后的数据
        """
        if data.shape[0] < window_size:
            # 如果数据长度小于窗口大小，直接返回原数据
            return data
        
        smoothed_data = np.zeros_like(data)
        for i in range(data.shape[1]):
            series = pd.Series(data[:, i])
            smoothed_series = series.rolling(window=window_size, min_periods=1, center=True).mean()
            smoothed_data[:, i] = smoothed_series.values
        
        return smoothed_data

    # 该方法将ori_state_data进行后处理，返回结果为后处理后的数据
    def process_episode_state_data(self, ori_state_data: np.ndarray) -> np.ndarray:
        new_state_data = ori_state_data.copy()
        # 应用平滑滤波
        new_state_data = self._smooth_data(new_state_data, window_size=8)
        # 将第16,17列(索引15,16)从140-0归一化到0-1
        # left_gripper_open 和 right_gripper_open
        # 范围: 140(闭合) -> 0, 0(打开) -> 1
        new_state_data[:, 15] = (140.0 - new_state_data[:, 15]) / 145.0
        new_state_data[:, 16] = (140.0 - new_state_data[:, 16]) / 145.0
        return new_state_data

    # 该方法将ori_action_data进行后处理，返回结果为后处理后的数据
    def process_episode_action_data(self, ori_action_data: np.ndarray) -> np.ndarray:
        new_action_data = ori_action_data.copy()
        # 应用平滑滤波
        new_action_data = self._smooth_data(new_action_data, window_size=8)
        new_action_data[:, 15] = (140.0 - new_action_data[:, 15]) / 145.0
        new_action_data[:, 16] = (140.0 - new_action_data[:, 16]) / 145.0
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
                "left_gripper_open",
                "right_gripper_open"
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
                "left_gripper_open",
                "right_gripper_open"
                ]

