from pathlib import Path

import numpy as np

from .state_action_data_processor_base import StateActionDataPostProcessorBase


class GalaxeaR1LiteProcessor(StateActionDataPostProcessorBase):
    def __init__(self, convert_path: str | Path) -> None:
        super().__init__(convert_path)

    def prepare_processing(self) -> None:
        self.left_gripper_open_state_data_idx = 21
        pass

    def _remove_torso_state_data(self, data: np.ndarray) -> np.ndarray:
        """
        只保留前16个字段（双臂关节和夹爪）
        原始索引:
        - 0-15: 双臂关节和夹爪数据
        - 16+: torso、chassis等其他数据（删除）
        """
        # 只保留前16列
        modified_data = data[:, :16]
        
        return modified_data
    
    def _remove_torso_action_data(self, data: np.ndarray) -> np.ndarray:
        """
        只保留前16个字段（双臂关节和夹爪目标值）
        原始索引:
        - 0-15: 双臂关节和夹爪目标数据
        - 16+: chassis、torso等其他数据（删除）
        """
        # 只保留前16列
        modified_data = data[:, :16]
        
        return modified_data
    
        
    def get_modified_state_feature_names(self)-> list[str]:
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
                "left_gripper_open",
                "right_gripper_open",
                # "torso_joint_1",
                # "torso_joint_2",
                # "chassis_wheel_1",
                # "chassis_wheel_2",
                # "chassis_wheel_3",
                # "chassis_imu_accel_x",
                # "chassis_imu_accel_y",
                # "chassis_imu_accel_z",
                # "chassis_imu_gyro_x",
                # "chassis_imu_gyro_y",
                # "chassis_imu_gyro_z",
                # "torso_imu_accel_x",
                # "torso_imu_accel_y",
                # "torso_imu_accel_z",
                # "torso_imu_gyro_x",
                # "torso_imu_gyro_y",
                # "torso_imu_gyro_z"
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
                "left_gripper_open",
                "right_gripper_open",
                # "chassis_target_vel_linear_x",
                # "chassis_target_vel_linear_y",
                # "chassis_target_vel_linear_z",
                # "chassis_target_vel_angular_x",
                # "chassis_target_vel_angular_y",
                # "chassis_target_vel_angular_z",
                # # "torso_target_vel_linear_x",
                # # "torso_target_vel_linear_y",
                # # "torso_target_vel_linear_z",
                # # "torso_target_vel_angular_x",
                # # "torso_target_vel_angular_y",
                # # "torso_target_vel_angular_z"
        ]

    # 该方法将ori_state_data进行后处理，返回结果为后处理后的数据
    def process_episode_state_data(self, ori_state_data: np.ndarray) -> np.ndarray:
        new_state_data = ori_state_data.copy()
        # 删除 torso 相关的 state 数据列
        new_state_data = self._remove_torso_state_data(new_state_data)
        
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
        # 删除 torso 相关的 action 数据列
        new_action_data = self._remove_torso_action_data(new_action_data)
        
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



class GalaxeaR1LiteH5Mp4Processor(StateActionDataPostProcessorBase):
    def __init__(self, convert_path: str | Path) -> None:
        super().__init__(convert_path)

    def prepare_processing(self) -> None:
        pass

    def _smooth_gripper_open_data(self, data: np.ndarray) -> np.ndarray:
        smoothed = data.copy()
        return smoothed

    def get_modified_state_feature_names(self) -> list[str]:
        return [
                "left_arm_joint_1_rad",
                "left_arm_joint_2_rad",
                "left_arm_joint_3_rad",
                "left_arm_joint_4_rad",
                "left_arm_joint_5_rad",
                "left_arm_joint_6_rad",
                "left_gripper_open",
                "right_arm_joint_1_rad",
                "right_arm_joint_2_rad",
                "right_arm_joint_3_rad",
                "right_arm_joint_4_rad",
                "right_arm_joint_5_rad",
                "right_arm_joint_6_rad",
                "right_gripper_open",
                ]

    def get_modified_action_feature_names(self) -> list[str]:
        return [
                "left_arm_joint_1_rad",
                "left_arm_joint_2_rad",
                "left_arm_joint_3_rad",
                "left_arm_joint_4_rad",
                "left_arm_joint_5_rad",
                "left_arm_joint_6_rad",
                "left_gripper_open",
                "right_arm_joint_1_rad",
                "right_arm_joint_2_rad",
                "right_arm_joint_3_rad",
                "right_arm_joint_4_rad",
                "right_arm_joint_5_rad",
                "right_arm_joint_6_rad",
                "right_gripper_open",
                ]

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
