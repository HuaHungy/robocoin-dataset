from pathlib import Path

import numpy as np

from .state_action_data_processor_base import StateActionDataPostProcessorBase

class ThirdViewProcessor(StateActionDataPostProcessorBase):
    def __init__(self, convert_path: str | Path) -> None:
        super().__init__(convert_path)

    def prepare_processing(self) -> None:
        # 获取原始特征名称以便查找索引
        ori_names = self.get_ori_state_action_feature_names()
        self.state_names = ori_names.get("observation.state", [])
        self.action_names = ori_names.get("action", [])
        
        # 查找需要复制的列索引
        self.left_arm_joint_6_state_idx = None
        self.right_arm_joint_6_state_idx = None
        self.left_arm_joint_6_action_idx = None
        self.right_arm_joint_6_action_idx = None
        
        if "left_arm_joint_6_rad" in self.state_names:
            self.left_arm_joint_6_state_idx = self.state_names.index("left_arm_joint_6_rad")
        if "right_arm_joint_6_rad" in self.state_names:
            self.right_arm_joint_6_state_idx = self.state_names.index("right_arm_joint_6_rad")
        if "left_arm_joint_6_rad" in self.action_names:
            self.left_arm_joint_6_action_idx = self.action_names.index("left_arm_joint_6_rad")
        if "right_arm_joint_6_rad" in self.action_names:
            self.right_arm_joint_6_action_idx = self.action_names.index("right_arm_joint_6_rad")

    # 该方法将ori_state_data进行后处理，返回结果为后处理后的数据
    def process_episode_state_data(self, ori_state_data: np.ndarray) -> np.ndarray:
        # 保持 state 数据不变
        new_state_data = ori_state_data.copy()
        return new_state_data

    # 该方法将episode数据进行后处理，返回结果为后处理后的数据
    def process_episode_data(self, ori_data: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """
        保留完整的 state 数据，将 state 中的 left_arm_joint_6_rad 和 right_arm_joint_6_rad 
        复制到 action 对应列，其他 action 数据保持不变。
        """
        state = ori_data.get("observation.state")
        action = ori_data.get("action")

        if state is None or action is None:
            raise ValueError("ori_data must contain 'observation.state' and 'action'")

        if not isinstance(state, np.ndarray) or not isinstance(action, np.ndarray):
            raise ValueError("state and action must be numpy arrays")

        if state.shape[0] != action.shape[0]:
            raise ValueError("state and action must have same number of frames")

        # 保持 state 不变
        out_state = state.copy()
        # 复制 action 以便修改
        out_action = action.copy()

        # 将 state 中的 joint_6 数据插入到 action 中
        # 如果 action 中不存在 joint_6，则需要插入
        if (self.left_arm_joint_6_state_idx is not None and 
            self.left_arm_joint_6_action_idx is None):
            # 插入 left_arm_joint_6 到索引 5 (在 joint_5 之后)
            left_joint_6_data = state[:, self.left_arm_joint_6_state_idx:self.left_arm_joint_6_state_idx+1]
            out_action = np.concatenate([
                out_action[:, :5],        # left_arm_joint_1 到 joint_5
                left_joint_6_data,        # left_arm_joint_6
                out_action[:, 5:],        # 剩余部分
            ], axis=1)
            
        if (self.right_arm_joint_6_state_idx is not None and 
            self.right_arm_joint_6_action_idx is None):
            # 插入 right_arm_joint_6 到索引 11 (在 right_arm_joint_5 之后，考虑已插入的 left_joint_6)
            right_joint_6_data = state[:, self.right_arm_joint_6_state_idx:self.right_arm_joint_6_state_idx+1]
            # 注意：如果 left_joint_6 已插入，索引需要 +1
            insert_idx = 11 if self.left_arm_joint_6_action_idx is None else 12
            out_action = np.concatenate([
                out_action[:, :insert_idx],   # 前面的部分
                right_joint_6_data,           # right_arm_joint_6
                out_action[:, insert_idx:],   # 剩余部分
            ], axis=1)

        return {"observation.state": out_state, "action": out_action}

    # 该方法返回处理后的state数据名称
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
                "left_arm_joint_1_vel_rad_s",
                "left_arm_joint_2_vel_rad_s",
                "left_arm_joint_3_vel_rad_s",
                "left_arm_joint_4_vel_rad_s",
                "left_arm_joint_5_vel_rad_s",
                "left_arm_joint_6_vel_rad_s",
                "left_arm_joint_1_eff_nm",
                "left_arm_joint_2_eff_nm",
                "left_arm_joint_3_eff_nm",
                "left_arm_joint_4_eff_nm",
                "left_arm_joint_5_eff_nm",
                "left_arm_joint_6_eff_nm",
                "left_eef_pos_x_m",
                "left_eef_pos_y_m",
                "left_eef_pos_z_m",
                "left_eef_euler_x_rad",
                "left_eef_euler_y_rad",
                "left_eef_euler_z_rad",
                "right_arm_joint_1_rad",
                "right_arm_joint_2_rad",
                "right_arm_joint_3_rad",
                "right_arm_joint_4_rad",
                "right_arm_joint_5_rad",
                "right_arm_joint_6_rad",
                "right_arm_joint_1_vel_rad_s",
                "right_arm_joint_2_vel_rad_s",
                "right_arm_joint_3_vel_rad_s",
                "right_arm_joint_4_vel_rad_s",
                "right_arm_joint_5_vel_rad_s",
                "right_arm_joint_6_vel_rad_s",
                "right_arm_joint_1_eff_nm",
                "right_arm_joint_2_eff_nm",
                "right_arm_joint_3_eff_nm",
                "right_arm_joint_4_eff_nm",
                "right_arm_joint_5_eff_nm",
                "right_arm_joint_6_eff_nm",
                "right_eef_pos_x_m",
                "right_eef_pos_y_m",
                "right_eef_pos_z_m",
                "right_eef_euler_x_rad",
                "right_eef_euler_y_rad",
                "right_eef_euler_z_rad",
                "head_joint_1_rad",
                "head_joint_2_rad",
                "head_joint_1_vel_rad_s",
                "head_joint_2_vel_rad_s",
                "head_joint_1_eff_nm",
                "head_joint_2_eff_nm",
                "spine_joint_1_rad",
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
        return [
                "left_arm_joint_1_rad",
                "left_arm_joint_2_rad",
                "left_arm_joint_3_rad",
                "left_arm_joint_4_rad",
                "left_arm_joint_5_rad",
                "left_arm_joint_6_rad",
                "right_arm_joint_1_rad",
                "right_arm_joint_2_rad",
                "right_arm_joint_3_rad",
                "right_arm_joint_4_rad",
                "right_arm_joint_5_rad",
                "right_arm_joint_6_rad",
                "head_joint_1_rad",
                "head_joint_2_rad",
                "spine_joint_1_rad",
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

