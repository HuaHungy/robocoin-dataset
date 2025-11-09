from pathlib import Path

import numpy as np

from .state_action_data_processor_base import StateActionDataPostProcessorBase


class YinheProcessor(StateActionDataPostProcessorBase):
    def __init__(self, convert_path: str | Path) -> None:
        super().__init__(convert_path)
        self.left_gripper_state_idx = None
        self.right_gripper_state_idx = None
        self.left_gripper_action_idx = None
        self.right_gripper_action_idx = None

    def prepare_processing(self) -> None:
        # 获取原始的 state 和 action 特征名称
        ori_names = self.get_ori_state_action_feature_names()
        state_names = ori_names["observation.state"]
        action_names = ori_names["action"]
        
        # 查找 gripper 字段在 state 中的索引
        try:
            self.left_gripper_state_idx = state_names.index("left_gripper_open")
        except ValueError:
            self.left_gripper_state_idx = None
            
        try:
            self.right_gripper_state_idx = state_names.index("right_gripper_open")
        except ValueError:
            self.right_gripper_state_idx = None
        
        # 查找 gripper 字段在 action 中的索引
        try:
            self.left_gripper_action_idx = action_names.index("left_gripper_open")
        except ValueError:
            self.left_gripper_action_idx = None
            
        try:
            self.right_gripper_action_idx = action_names.index("right_gripper_open")
        except ValueError:
            self.right_gripper_action_idx = None

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
    
    # 该方法将episode数据进行后处理，将 state 中的 gripper 数据复制到 action
    def process_episode_data(self, ori_data: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """
        保留完整的 state 数据，将 state 中的 left_gripper_open 和 right_gripper_open 
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
        out_state = self.process_episode_state_data(state)
        # 复制 action 以便修改
        out_action = self.process_episode_action_data(action)

        # 将 state 中的 gripper 数据复制到 action 对应列
        if (self.left_gripper_state_idx is not None and 
            self.left_gripper_action_idx is not None):
            out_action[:, self.left_gripper_action_idx] = state[:, self.left_gripper_state_idx]
            
        if (self.right_gripper_state_idx is not None and 
            self.right_gripper_action_idx is not None):
            out_action[:, self.right_gripper_action_idx] = state[:, self.right_gripper_state_idx]

        return {"observation.state": out_state, "action": out_action}
    
    def get_modified_feature_names(self):
        return super().get_modified_feature_names()

    def get_modified_info_state_names(self) -> dict[str, str]:
        return {}

    # 该方法返回处理后的action数据名称
    def get_modified_info_action_names(self) -> dict[str, str]:
        return {}

    def get_modified_state_feature_names(self)-> list[str]:
        return [
                "body_joint_1_rad",
                "body_joint_2_rad",
                "body_joint_3_rad",
                "head_joint_1_rad",
                "head_joint_2_rad",
                "left_arm_joint_1_rad",
                "left_arm_joint_2_rad",
                "left_arm_joint_3_rad",
                "left_arm_joint_4_rad",
                "left_arm_joint_5_rad",
                "left_arm_joint_6_rad",
                "left_arm_joint_7_rad",
                "left_gripper_open",
                "right_arm_joint_1_rad",
                "right_arm_joint_2_rad",
                "right_arm_joint_3_rad",
                "right_arm_joint_4_rad",
                "right_arm_joint_5_rad",
                "right_arm_joint_6_rad",
                "right_arm_joint_7_rad",
                "right_gripper_open",
                "left_arm_joint_1_vel_rad_s",
                "left_arm_joint_2_vel_rad_s",
                "left_arm_joint_3_vel_rad_s",
                "left_arm_joint_4_vel_rad_s",
                "left_arm_joint_5_vel_rad_s",
                "left_arm_joint_6_vel_rad_s",
                "left_arm_joint_7_vel_rad_s",
                "left_arm_joint_1_eff_nm",
                "left_arm_joint_2_eff_nm",
                "left_arm_joint_3_eff_nm",
                "left_arm_joint_4_eff_nm",
                "left_arm_joint_5_eff_nm",
                "left_arm_joint_6_eff_nm",
                "left_arm_joint_7_eff_nm",
                "right_arm_joint_1_vel_rad_s",
                "right_arm_joint_2_vel_rad_s",
                "right_arm_joint_3_vel_rad_s",
                "right_arm_joint_4_vel_rad_s",
                "right_arm_joint_5_vel_rad_s",
                "right_arm_joint_6_vel_rad_s",
                "right_arm_joint_7_vel_rad_s",
                "right_arm_joint_1_eff_nm",
                "right_arm_joint_2_eff_nm",
                "right_arm_joint_3_eff_nm",
                "right_arm_joint_4_eff_nm",
                "right_arm_joint_5_eff_nm",
                "right_arm_joint_6_eff_nm",
                "right_arm_joint_7_eff_nm"
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
                "left_gripper_open",
                "right_arm_joint_1_rad",
                "right_arm_joint_2_rad",
                "right_arm_joint_3_rad",
                "right_arm_joint_4_rad",
                "right_arm_joint_5_rad",
                "right_arm_joint_6_rad",
                "right_arm_joint_7_rad",
                "right_gripper_open"
            ]