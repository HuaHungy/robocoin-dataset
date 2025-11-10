from pathlib import Path

import numpy as np
import pandas as pd

from .state_action_data_processor_base import StateActionDataPostProcessorBase

class ThirdViewProcessor(StateActionDataPostProcessorBase):
    def __init__(self, convert_path: str | Path) -> None:
        super().__init__(convert_path)

    def prepare_processing(self) -> None:
        # 定义需要保留的state索引
        self.keep_state_indices = [
            0, 1, 2, 3, 4, 5,    # left arm joint positions
            # 6, 7, 8, 9, 10, 11,  # left arm joint velocities
            # 12, 13, 14, 15, 16, 17,  # left arm joint efforts
            # 18, 19, 20,          # left eef position
            # 21, 22, 23,          # left eef orientation (euler)
            24, 25, 26, 27, 28, 29,  # right arm joint positions
            # 30, 31, 32, 33, 34, 35,  # right arm joint velocities
            # 36, 37, 38, 39, 40, 41,  # right arm joint efforts
            # 42, 43, 44,          # right eef position
            # 45, 46, 47,          # right eef orientation (euler)
            # 48, 49,              # head joint positions
            # 50, 51,              # head joint velocities
            # 52, 53,              # head joint efforts
            # 54,                 # spine joint position
            # Left hand joints
            55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66,
            # Right hand joints
            67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78
        ]
    
    def _smooth_joint_data(self, data: np.ndarray, window_size: int = 8) -> np.ndarray:
        """
        对关节数据进行平滑滤波
        
        Args:
            data: 输入数据，shape 为 (n_frames, n_joints)
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
    
    # 该方法将episode数据进行后处理，返回结果为后处理后的数据
    def process_episode_data(self, ori_data: dict[str, np.ndarray]) -> dict[str, np.ndarray]:

        new_state = ori_data["observation.state"][:, self.keep_state_indices]
        
        # 对 state 数据进行平滑滤波（窗口大小为16）
        new_state = self._smooth_joint_data(new_state, window_size=16)
        
        # 将 state 复制给 action
        new_action = new_state.copy()
        
        return {"observation.state": new_state, "action": new_action}

    # 该方法返回处理后的state数据名称
    def get_modified_feature_names(self):
        return super().get_modified_feature_names()

    def get_modified_state_feature_names(self) -> list[str]:
        return [
                "left_arm_joint_1_rad",
                "left_arm_joint_2_rad",
                "left_arm_joint_3_rad",
                "left_arm_joint_4_rad",
                "left_arm_joint_5_rad",
                "left_arm_joint_6_rad",
                # "left_arm_joint_1_vel_rad_s",
                # "left_arm_joint_2_vel_rad_s",
                # "left_arm_joint_3_vel_rad_s",
                # "left_arm_joint_4_vel_rad_s",
                # "left_arm_joint_5_vel_rad_s",
                # "left_arm_joint_6_vel_rad_s",
                # "left_arm_joint_1_eff_nm",
                # "left_arm_joint_2_eff_nm",
                # "left_arm_joint_3_eff_nm",
                # "left_arm_joint_4_eff_nm",
                # "left_arm_joint_5_eff_nm",
                # "left_arm_joint_6_eff_nm",
                # "left_eef_pos_x_m",
                # "left_eef_pos_y_m",
                # "left_eef_pos_z_m",
                # "left_eef_euler_x_rad",
                # "left_eef_euler_y_rad",
                # "left_eef_euler_z_rad",
                "right_arm_joint_1_rad",
                "right_arm_joint_2_rad",
                "right_arm_joint_3_rad",
                "right_arm_joint_4_rad",
                "right_arm_joint_5_rad",
                "right_arm_joint_6_rad",
                # "right_arm_joint_1_vel_rad_s",
                # "right_arm_joint_2_vel_rad_s",
                # "right_arm_joint_3_vel_rad_s",
                # "right_arm_joint_4_vel_rad_s",
                # "right_arm_joint_5_vel_rad_s",
                # "right_arm_joint_6_vel_rad_s",
                # "right_arm_joint_1_eff_nm",
                # "right_arm_joint_2_eff_nm",
                # "right_arm_joint_3_eff_nm",
                # "right_arm_joint_4_eff_nm",
                # "right_arm_joint_5_eff_nm",
                # "right_arm_joint_6_eff_nm",
                # "right_eef_pos_x_m",
                # "right_eef_pos_y_m",
                # "right_eef_pos_z_m",
                # "right_eef_euler_x_rad",
                # "right_eef_euler_y_rad",
                # "right_eef_euler_z_rad",
                # "head_joint_1_rad",
                # "head_joint_2_rad",
                # "head_joint_1_vel_rad_s",
                # "head_joint_2_vel_rad_s",
                # "head_joint_1_eff_nm",
                # "head_joint_2_eff_nm",
                # "spine_joint_1_rad",
                "left_hand_joint_1_rad",
                "left_hand_joint_2_rad",
                "left_hand_joint_3_rad",
                "left_hand_joint_4_rad",
                "left_hand_joint_5_rad",
                "left_hand_joint_6_rad",
                "left_hand_joint_7_rad",
                "left_hand_joint_8_rad",
                "left_hand_joint_9_rad",
                "left_hand_joint_10_rad",
                "left_hand_joint_11_rad",
                "left_hand_joint_12_rad",
                "right_hand_joint_1_rad",
                "right_hand_joint_2_rad",
                "right_hand_joint_3_rad",
                "right_hand_joint_4_rad",
                "right_hand_joint_5_rad",
                "right_hand_joint_6_rad",
                "right_hand_joint_7_rad",
                "right_hand_joint_8_rad",
                "right_hand_joint_9_rad",
                "right_hand_joint_10_rad",
                "right_hand_joint_11_rad",
                "right_hand_joint_12_rad"
            ]
    
    def get_modified_action_feature_names(self) -> list[str]:
        # action 和 state 特征名称相同
        return self.get_modified_state_feature_names()

    def get_modified_info_state_names(self) -> dict[str, str]:
        return {}

    # 该方法返回处理后的action数据名称
    def get_modified_info_action_names(self) -> dict[str, str]:
        return {}

