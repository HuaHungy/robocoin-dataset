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
        ]

    # 该方法将ori_state_data进行后处理，返回结果为后处理后的数据
    def process_episode_state_data(self, ori_state_data: np.ndarray) -> np.ndarray:
        new_state_data = ori_state_data.copy()
        # 删除 torso 相关的 state 数据列
        new_state_data = self._remove_torso_state_data(new_state_data)
        
        return new_state_data

    # 该方法将ori_action_data进行后处理，返回结果为后处理后的数据
    def process_episode_action_data(self, ori_action_data: np.ndarray, ori_state_data: np.ndarray = None) -> np.ndarray:
        new_action_data = ori_action_data.copy()
        # 删除 torso 相关的 action 数据列
        new_action_data = self._remove_torso_action_data(new_action_data)
        
        # action 数据缺少 left_arm_joint_7 和 right_arm_joint_7
        # 从对应的 state 数据中复制这两个关节的值
        if ori_state_data is not None:
            # 先处理 state 数据以获取正确的索引
            processed_state = self._remove_torso_state_data(ori_state_data)
            
            # 从 state 数据中提取 joint_7 的值
            # processed_state 布局: 0-6: left_arm_1~7, 7-13: right_arm_1~7, 14-15: grippers
            left_joint_7 = processed_state[:, 6:7]  # left_arm_joint_7
            right_joint_7 = processed_state[:, 13:14]  # right_arm_joint_7
        else:
            # 如果没有 state 数据，则复制 joint_6 的值作为 fallback
            left_joint_7 = new_action_data[:, 5:6]
            right_joint_7 = new_action_data[:, 12:13]
        
        # 原始 action 数据布局（删除torso后14个字段）:
        # 0-5: left_arm_joint_1~6
        # 6: left_gripper
        # 7-12: right_arm_joint_1~6  
        # 13: right_gripper
        
        # 目标布局（16个字段）:
        # 0-6: left_arm_joint_1~7
        # 7-13: right_arm_joint_1~7
        # 14: left_gripper
        # 15: right_gripper
        
        # 在索引6处插入一列（从state复制的left_arm_joint_7）
        new_action_data = np.insert(new_action_data, 6, left_joint_7.squeeze(), axis=1)
        
        # 在索引13处插入一列（从state复制的right_arm_joint_7，注意前面插入后索引+1）
        new_action_data = np.insert(new_action_data, 13, right_joint_7.squeeze(), axis=1)
        
        return new_action_data
    
    def process_episode_data(self, ori_data: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """重写此方法以便在处理 action 时访问 state 数据"""
        state_data = ori_data["observation.state"]
        action_data = ori_data["action"]
        
        return {
            "observation.state": self.process_episode_state_data(state_data),
            "action": self.process_episode_action_data(action_data, state_data),
        }

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
    
    # 忽略原始 action 数据，全部使用 state 数据覆盖
    def process_episode_data(self, ori_data: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        processed_state = self.process_episode_state_data(ori_data["observation.state"])
        # action 特征在本 processor 中与 state 特征长度一致，直接复制
        processed_action = processed_state.copy()
        return {"observation.state": processed_state, "action": processed_action}

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
