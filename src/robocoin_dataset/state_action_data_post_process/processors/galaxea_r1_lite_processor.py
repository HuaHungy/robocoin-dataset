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
        删除 state 数据中的 torso 相关列
        原始索引:
        - 16-17: torso_joint_1, torso_joint_2
        - 24-29: torso_imu_accel_x/y/z, torso_imu_gyro_x/y/z
        """
        # 删除索引 16-17 (torso_joint_1, torso_joint_2)
        modified_data = np.delete(data, [16, 17], axis=1)
        # 删除索引 24-29 (torso_imu，注意删除前面的列后索引变化，所以是22-27)
        modified_data = np.delete(modified_data, [22, 23, 24, 25, 26, 27], axis=1)
        
        return modified_data
    
    def _remove_torso_action_data(self, data: np.ndarray) -> np.ndarray:
        """
        删除 action 数据中的 torso 相关列
        原始索引:
        - 20-25: torso_target_vel_linear_x/y/z, torso_target_vel_angular_x/y/z
        """
        # 删除索引 20-25 (torso_target_vel)
        modified_data = np.delete(data, [20, 21, 22, 23, 24, 25], axis=1)
        
        return modified_data
    
        
    def get_modified_state_feature_names(self)-> list[str]:
        return [
                "left_arm_joint_1",
                "left_arm_joint_2",
                "left_arm_joint_3",
                "left_arm_joint_4",
                "left_arm_joint_5",
                "left_arm_joint_6",
                "left_arm_joint_7",
                "right_arm_joint_1",
                "right_arm_joint_2",
                "right_arm_joint_3",
                "right_arm_joint_4",
                "right_arm_joint_5",
                "right_arm_joint_6",
                "right_arm_joint_7",
                "left_gripper_position",
                "right_gripper_position",
                # "torso_joint_1",
                # "torso_joint_2",
                "chassis_wheel_1",
                "chassis_wheel_2",
                "chassis_wheel_3",
                "chassis_imu_accel_x",
                "chassis_imu_accel_y",
                "chassis_imu_accel_z",
                "chassis_imu_gyro_x",
                "chassis_imu_gyro_y",
                "chassis_imu_gyro_z",
                # "torso_imu_accel_x",
                # "torso_imu_accel_y",
                # "torso_imu_accel_z",
                # "torso_imu_gyro_x",
                # "torso_imu_gyro_y",
                # "torso_imu_gyro_z"
        ]
    
    def get_modified_action_feature_names(self) -> list[str]:
        return [
                "left_arm_target_joint_1",
                "left_arm_target_joint_2",
                "left_arm_target_joint_3",
                "left_arm_target_joint_4",
                "left_arm_target_joint_5",
                "left_arm_target_joint_6",
                "right_arm_target_joint_1",
                "right_arm_target_joint_2",
                "right_arm_target_joint_3",
                "right_arm_target_joint_4",
                "right_arm_target_joint_5",
                "right_arm_target_joint_6",
                "left_gripper_target_position",
                "right_gripper_target_position",
                "chassis_target_vel_linear_x",
                "chassis_target_vel_linear_y",
                "chassis_target_vel_linear_z",
                "chassis_target_vel_angular_x",
                "chassis_target_vel_angular_y",
                "chassis_target_vel_angular_z",
                # "torso_target_vel_linear_x",
                # "torso_target_vel_linear_y",
                # "torso_target_vel_linear_z",
                # "torso_target_vel_angular_x",
                # "torso_target_vel_angular_y",
                # "torso_target_vel_angular_z"
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
                "left_arm_joint_1",
                "left_arm_joint_2",
                "left_arm_joint_3",
                "left_arm_joint_4",
                "left_arm_joint_5",
                "left_arm_joint_6",
                "left_gripper_position",
                "right_arm_joint_1",
                "right_arm_joint_2",
                "right_arm_joint_3",
                "right_arm_joint_4",
                "right_arm_joint_5",
                "right_arm_joint_6",
                "right_gripper_position"
                ]

    def get_modified_action_feature_names(self) -> list[str]:
        return [
                "left_arm_target_joint_1",
                "left_arm_target_joint_2",
                "left_arm_target_joint_3",
                "left_arm_target_joint_4",
                "left_arm_target_joint_5",
                "left_arm_target_joint_6",
                "left_gripper_target_position",
                "right_arm_target_joint_1",
                "right_arm_target_joint_2",
                "right_arm_target_joint_3",
                "right_arm_target_joint_4",
                "right_arm_target_joint_5",
                "right_arm_target_joint_6",
                "right_gripper_target_position"
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
