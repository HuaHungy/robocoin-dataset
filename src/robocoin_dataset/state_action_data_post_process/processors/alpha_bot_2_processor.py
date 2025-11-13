from pathlib import Path

import numpy as np
import pandas as pd

from .state_action_data_processor_base import StateActionDataPostProcessorBase


class AlphaBot2Processor(StateActionDataPostProcessorBase):
    def __init__(self, convert_path: str | Path) -> None:
        super().__init__(convert_path)

    def prepare_processing(self) -> None:
                self.keep_indices = [
                0, 1, 2, 3, 4, 5, 6,
                # 7, 8, 9, 10, 11, 12,
                13, 14, 15, 16, 17, 18, 19,
                # 20, 21, 22, 23, 24, 25,
                26, 27,
        ]
        # pass

    def _smooth_data(self, data: np.ndarray, window_size: int = 16) -> np.ndarray:
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
        # new_state_data = ori_state_data[:, self.keep_indices]
        new_state_data = ori_state_data.copy()
        # 应用平滑滤波
        new_state_data = self._smooth_data(new_state_data, window_size=16)
        return new_state_data

    # 该方法将ori_action_data进行后处理，返回结果为后处理后的数据
    def process_episode_action_data(self, ori_action_data: np.ndarray) -> np.ndarray:
        # new_action_data = ori_action_data[:, self.keep_indices]
        new_action_data = ori_action_data.copy()
        # 应用平滑滤波
        new_action_data = self._smooth_data(new_action_data, window_size=16)
        return new_action_data
    
    def get_modified_feature_names(self):
        return super().get_modified_feature_names()

    def get_modified_state_feature_names(self)-> list[str]:
        return [
                "left_arm_joint_1_rad",
                "left_arm_joint_2_rad",
                "left_arm_joint_3_rad",
                "left_arm_joint_4_rad",
                "left_arm_joint_5_rad",
                "left_arm_joint_6_rad",
                "left_arm_joint_7_rad",
                "left_eef_pos_x_m",
                "left_eef_pos_y_m",
                "left_eef_pos_z_m",
                "left_eef_rot_euler_x_rad",
                "left_eef_rot_euler_y_rad",
                "left_eef_rot_euler_z_rad",
                "right_arm_joint_1_rad",
                "right_arm_joint_2_rad",
                "right_arm_joint_3_rad",
                "right_arm_joint_4_rad",
                "right_arm_joint_5_rad",
                "right_arm_joint_6_rad",
                "right_arm_joint_7_rad",
                "right_eef_pos_x_m",
                "right_eef_pos_y_m",
                "right_eef_pos_z_m",
                "right_eef_rot_euler_x_rad",
                "right_eef_rot_euler_y_rad",
                "right_eef_rot_euler_z_rad",
                "left_gripper_open",
                "right_gripper_open",
            ]
    
    def get_modified_action_feature_names(self)-> list[str]:
        return [
                "left_arm_joint_1_rad",
                "left_arm_joint_2_rad",
                "left_arm_joint_3_rad",
                "left_arm_joint_4_rad",
                "left_arm_joint_5_rad",
                "left_arm_joint_6_rad",
                "left_arm_joint_7_rad",
                "left_eef_pos_x_m",
                "left_eef_pos_y_m",
                "left_eef_pos_z_m",
                "left_eef_rot_euler_x_rad",
                "left_eef_rot_euler_y_rad",
                "left_eef_rot_euler_z_rad",
                "right_arm_joint_1_rad",
                "right_arm_joint_2_rad",
                "right_arm_joint_3_rad",
                "right_arm_joint_4_rad",
                "right_arm_joint_5_rad",
                "right_arm_joint_6_rad",
                "right_arm_joint_7_rad",
                "right_eef_pos_x_m",
                "right_eef_pos_y_m",
                "right_eef_pos_z_m",
                "right_eef_rot_euler_x_rad",
                "right_eef_rot_euler_y_rad",
                "right_eef_rot_euler_z_rad",
                "left_gripper_open",
                "right_gripper_open",
            ]