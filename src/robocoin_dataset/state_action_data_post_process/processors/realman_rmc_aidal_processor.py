from pathlib import Path

import numpy as np

from .state_action_data_processor_base import StateActionDataPostProcessorBase


class RealmanRmcAidalProcessor(StateActionDataPostProcessorBase):
    def __init__(self, convert_path: str | Path) -> None:
        super().__init__(convert_path)

    def prepare_processing(self) -> None:
        self.left_gripper_open_state_data_idx = 21
        self.right_gripper_open_state_data_idx = 7
        self.left_gripper_open_action_data_idx = self.left_gripper_open_state_data_idx
        self.right_gripper_open_action_data_idx = self.right_gripper_open_state_data_idx
        pass

    def _smooth_gripper_open_data(self, data: np.ndarray) -> np.ndarray:
        smoothed = data.copy()
        start_idx = 0
        start_val = data[0]

        for i in range(1, len(data)):
            if data[i] != start_val:
                end_idx = i
                end_val = data[i]
                for j in range(start_idx + 1, end_idx):
                    t = (j - start_idx) / (end_idx - start_idx)
                    smoothed[j] = start_val + t * (end_val - start_val)
                start_idx = i
                start_val = data[i]

        return smoothed

    # 该方法将ori_state_data进行后处理，返回结果为后处理后的数据
    def process_episode_state_data(self, ori_state_data: np.ndarray) -> np.ndarray:
        new_state_data = ori_state_data.copy()
        left_gripper_data = ori_state_data[:, self.left_gripper_open_state_data_idx]
        right_gripper_data = ori_state_data[:, self.right_gripper_open_state_data_idx]

        new_left_gripper_data = self._smooth_gripper_open_data(left_gripper_data)
        new_right_gripper_data = self._smooth_gripper_open_data(right_gripper_data)

        new_state_data[:, self.left_gripper_open_state_data_idx] = new_left_gripper_data
        new_state_data[:, self.right_gripper_open_state_data_idx] = new_right_gripper_data

        return new_state_data

    # 该方法将ori_action_data进行后处理，返回结果为后处理后的数据
    def process_episode_action_data(self, ori_action_data: np.ndarray) -> np.ndarray:
        new_action_data = ori_action_data.copy()
        left_gripper_data = ori_action_data[:, self.left_gripper_open_action_data_idx]
        right_gripper_data = ori_action_data[:, self.right_gripper_open_action_data_idx]

        new_left_gripper_data = self._smooth_gripper_open_data(left_gripper_data)
        new_right_gripper_data = self._smooth_gripper_open_data(right_gripper_data)

        new_action_data[:, self.left_gripper_open_action_data_idx] = new_left_gripper_data
        new_action_data[:, self.right_gripper_open_action_data_idx] = new_right_gripper_data

        return new_action_data

    # 在这里填入修改后的state特征名称列表，如果没有修改，则不需要重写函数
    def get_modified_state_feature_names(self) -> list[str]:
        return [
            "right_arm_joint_1_rad",
            "right_arm_joint_2_rad",
            "right_arm_joint_3_rad",
            "right_arm_joint_4_rad",
            "right_arm_joint_5_rad",
            "right_arm_joint_6_rad",
            "right_arm_joint_7_rad",
            "right_gripper_open",
            "right_eef_pos_x_m",
            "right_eef_pos_y_m",
            "right_eef_pos_z_m",
            "right_eef_rot_euler_x_rad",
            "right_eef_rot_euler_y_rad",
            "right_eef_rot_euler_z_rad",
            "left_arm_joint_1_rad",
            "left_arm_joint_2_rad",
            "left_arm_joint_3_rad",
            "left_arm_joint_4_rad",
            "left_arm_joint_5_rad",
            "left_arm_joint_6_rad",
            "left_arm_joint_7_rad",
            "left_gripper_open",
            "left_eef_pos_x_m",
            "left_eef_pos_y_m",
            "left_eef_pos_z_m",
            "left_eef_rot_euler_x_rad",
            "left_eef_rot_euler_y_rad",
            "left_eef_rot_euler_z_rad",
        ]

    # 在这里填入修改后的action特征名称列表，如果没有修改，则不需要重写函数
    def get_modified_action_feature_names(self) -> list[str]:
        return [
            "right_arm_joint_1_rad",
            "right_arm_joint_2_rad",
            "right_arm_joint_3_rad",
            "right_arm_joint_4_rad",
            "right_arm_joint_5_rad",
            "right_arm_joint_6_rad",
            "right_arm_joint_7_rad",
            "right_gripper_open",
            "right_eef_pos_x_m",
            "right_eef_pos_y_m",
            "right_eef_pos_z_m",
            "right_eef_rot_euler_x_rad",
            "right_eef_rot_euler_y_rad",
            "right_eef_rot_euler_z_rad",
            "left_arm_joint_1_rad",
            "left_arm_joint_2_rad",
            "left_arm_joint_3_rad",
            "left_arm_joint_4_rad",
            "left_arm_joint_5_rad",
            "left_arm_joint_6_rad",
            "left_arm_joint_7_rad",
            "left_gripper_open",
            "left_eef_pos_x_m",
            "left_eef_pos_y_m",
            "left_eef_pos_z_m",
            "left_eef_rot_euler_x_rad",
            "left_eef_rot_euler_y_rad",
            "left_eef_rot_euler_z_rad",
        ]

class RealmanRmcAidalMcapProcessor(StateActionDataPostProcessorBase):
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

    # 在这里填入修改后的state特征名称列表，如果没有修改，则不需要重写函数
    def get_modified_state_feature_names(self) -> list[str]:
        return [
                "right_arm_joint_1_rad",
                "right_arm_joint_2_rad",
                "right_arm_joint_3_rad",
                "right_arm_joint_4_rad",
                "right_arm_joint_5_rad",
                "right_arm_joint_6_rad",
                "right_arm_joint_7_rad",
                "right_gripper_open",
                "right_eef_pos_x_m",
                "right_eef_pos_y_m",
                "right_eef_pos_z_m",
                "right_eef_rot_euler_x_rad",
                "right_eef_rot_euler_y_rad",
                "right_eef_rot_euler_z_rad",
                "right_six_force_fx",
                "right_six_force_fy",
                "right_six_force_fz",
                "right_six_force_mx",
                "right_six_force_my",
                "right_six_force_mz",
                "left_arm_joint_1_rad",
                "left_arm_joint_2_rad",
                "left_arm_joint_3_rad",
                "left_arm_joint_4_rad",
                "left_arm_joint_5_rad",
                "left_arm_joint_6_rad",
                "left_arm_joint_7_rad",
                "left_gripper_open",
                "left_eef_pos_x_m",
                "left_eef_pos_y_m",
                "left_eef_pos_z_m",
                "left_eef_rot_euler_x_rad",
                "left_eef_rot_euler_y_rad",
                "left_eef_rot_euler_z_rad",
                "left_six_force_fx",
                "left_six_force_fy",
                "left_six_force_fz",
                "left_six_force_mx",
                "left_six_force_my",
                "left_six_force_mz"
            ]

    # 在这里填入修改后的action特征名称列表，如果没有修改，则不需要重写函数
    def get_modified_action_feature_names(self) -> list[str]:
        return [
                "right_arm_joint_1_rad",
                "right_arm_joint_2_rad",
                "right_arm_joint_3_rad",
                "right_arm_joint_4_rad",
                "right_arm_joint_5_rad",
                "right_arm_joint_6_rad",
                "right_arm_joint_7_rad",
                "right_gripper_open",
                "right_eef_pos_x_m",
                "right_eef_pos_y_m",
                "right_eef_pos_z_m",
                "right_eef_rot_euler_x_rad",
                "right_eef_rot_euler_y_rad",
                "right_eef_rot_euler_z_rad",
                "left_arm_joint_1_rad",
                "left_arm_joint_2_rad",
                "left_arm_joint_3_rad",
                "left_arm_joint_4_rad",
                "left_arm_joint_5_rad",
                "left_arm_joint_6_rad",
                "left_arm_joint_7_rad",
                "left_gripper_open",
                "left_eef_pos_x_m",
                "left_eef_pos_y_m",
                "left_eef_pos_z_m",
                "left_eef_rot_euler_x_rad",
                "left_eef_rot_euler_y_rad",
                "left_eef_rot_euler_z_rad"
            ]