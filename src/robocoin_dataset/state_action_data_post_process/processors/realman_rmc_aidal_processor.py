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
        # 创建state特征映射表：键是目标特征名称，值是可能的原始特征名称列表
        self.state_feature_mapping = {
            "left_arm_joint_1_rad": ["left_arm_joint_1_rad","LeftFollowerArm_Joint1.pos"],
            "left_arm_joint_2_rad": ["left_arm_joint_2_rad","LeftFollowerArm_Joint2.pos"], 
            "left_arm_joint_3_rad": ["left_arm_joint_3_rad","LeftFollowerArm_Joint3.pos"],
            "left_arm_joint_4_rad": ["left_arm_joint_4_rad","LeftFollowerArm_Joint4.pos"],
            "left_arm_joint_5_rad": ["left_arm_joint_5_rad","LeftFollowerArm_Joint5.pos"],
            "left_arm_joint_6_rad": ["left_arm_joint_6_rad","LeftFollowerArm_Joint6.pos"],
            "left_arm_joint_7_rad": ["left_arm_joint_7_rad","LeftFollowerArm_Joint7.pos"],
            "left_gripper_open": ["left_gripper_open","LeftGripper.pos"],
            "right_arm_joint_1_rad": ["right_arm_joint_1_rad","RightFollowerArm_Joint1.pos"],
            "right_arm_joint_2_rad": ["right_arm_joint_2_rad","RightFollowerArm_Joint2.pos"],
            "right_arm_joint_3_rad": ["right_arm_joint_3_rad","RightFollowerArm_Joint3.pos"],
            "right_arm_joint_4_rad": ["right_arm_joint_4_rad","RightFollowerArm_Joint4.pos"],
            "right_arm_joint_5_rad": ["right_arm_joint_5_rad","RightFollowerArm_Joint5.pos"],
            "right_arm_joint_6_rad": ["right_arm_joint_6_rad","RightFollowerArm_Joint6.pos"],
            "right_arm_joint_7_rad": ["right_arm_joint_7_rad","RightFollowerArm_Joint7.pos"],
            "right_gripper_open": ["right_gripper_open","RightGripper.pos"],
        }
        
        # 创建action特征映射表：键是目标特征名称，值是可能的原始特征名称列表
        self.action_feature_mapping = {
            "left_arm_joint_1_rad": ["left_arm_joint_1_rad","LeftLeaderArm_Joint1.pos"],
            "left_arm_joint_2_rad": ["left_arm_joint_2_rad","LeftLeaderArm_Joint2.pos"], 
            "left_arm_joint_3_rad": ["left_arm_joint_3_rad","LeftLeaderArm_Joint3.pos"],
            "left_arm_joint_4_rad": ["left_arm_joint_4_rad","LeftLeaderArm_Joint4.pos"],
            "left_arm_joint_5_rad": ["left_arm_joint_5_rad","LeftLeaderArm_Joint5.pos"],
            "left_arm_joint_6_rad": ["left_arm_joint_6_rad","LeftLeaderArm_Joint6.pos"],
            "left_arm_joint_7_rad": ["left_arm_joint_7_rad","LeftLeaderArm_Joint7.pos"],
            "left_gripper_open": ["left_gripper_open","LeftGripper.pos","left_gripper_open_rad"],
            "right_arm_joint_1_rad": ["right_arm_joint_1_rad","RightLeaderArm_Joint1.pos"],
            "right_arm_joint_2_rad": ["right_arm_joint_2_rad","RightLeaderArm_Joint2.pos"],
            "right_arm_joint_3_rad": ["right_arm_joint_3_rad","RightLeaderArm_Joint3.pos"],
            "right_arm_joint_4_rad": ["right_arm_joint_4_rad","RightLeaderArm_Joint4.pos"],
            "right_arm_joint_5_rad": ["right_arm_joint_5_rad","RightLeaderArm_Joint5.pos"],
            "right_arm_joint_6_rad": ["right_arm_joint_6_rad","RightLeaderArm_Joint6.pos"],
            "right_arm_joint_7_rad": ["right_arm_joint_7_rad","RightLeaderArm_Joint7.pos"],
            "right_gripper_open": ["right_gripper_open","RightGripper.pos","right_gripper_open_rad"],
        }
        
        # 获取原始特征名称并建立索引映射
        ori_names = self.get_ori_state_action_feature_names()
        self.state_indices = []
        self.action_indices = []
        self.missing_state_features = []  # 记录缺失的state特征
        self.missing_action_features = []  # 记录缺失的action特征
        
        # 处理state特征映射
        for target_name, alt_names in self.state_feature_mapping.items():
            found = False
            for alt_name in alt_names:
                if alt_name in ori_names["observation.state"]:
                    index = ori_names["observation.state"].index(alt_name)
                    self.state_indices.append(index)
                    found = True
                    break
            if not found:
                # 如果找不到，添加占位符索引 -1，并记录缺失特征
                self.state_indices.append(-1)
                self.missing_state_features.append(target_name)
        
        # 处理action特征映射
        for target_name, alt_names in self.action_feature_mapping.items():
            found = False
            for alt_name in alt_names:
                if alt_name in ori_names["action"]:
                    index = ori_names["action"].index(alt_name)
                    self.action_indices.append(index)
                    found = True
                    break
            if not found:
                # 如果找不到，添加占位符索引 -1，并记录缺失特征
                self.action_indices.append(-1)
                self.missing_action_features.append(target_name)

    # 重写 process_episode_data 方法，根据映射表提取和组合数据
    def process_episode_data(self, ori_data: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        state_data = ori_data["observation.state"]
        action_data = ori_data["action"]
        
        # 获取时间步长
        n_timesteps = state_data.shape[0]
        
        # 从state数据中提取映射的特征
        combined_state_data = np.zeros((n_timesteps, len(self.state_indices)))
        for i, idx in enumerate(self.state_indices):
            if idx >= 0:
                combined_state_data[:, i] = state_data[:, idx]
            # 如果idx为-1，保持为0（已经初始化为0）
            
        # 从action数据中提取映射的特征
        combined_action_data = np.zeros((n_timesteps, len(self.action_indices)))
        for i, idx in enumerate(self.action_indices):
            if idx >= 0:
                combined_action_data[:, i] = action_data[:, idx]
            # 如果idx为-1，保持为0（已经初始化为0）
        
        # 将 action 的 gripper_open 复制到 state
        state_keys = list(self.state_feature_mapping.keys())
        action_keys = list(self.action_feature_mapping.keys())
        
        # 找到 gripper_open 在提取后的数组中的索引
        left_gripper_state_idx = state_keys.index("left_gripper_open") if "left_gripper_open" in state_keys else -1
        right_gripper_state_idx = state_keys.index("right_gripper_open") if "right_gripper_open" in state_keys else -1
        left_gripper_action_idx = action_keys.index("left_gripper_open") if "left_gripper_open" in action_keys else -1
        right_gripper_action_idx = action_keys.index("right_gripper_open") if "right_gripper_open" in action_keys else -1
        
        # 复制 gripper_open 值（只有当两个索引都有效时才复制）
        if left_gripper_state_idx >= 0 and left_gripper_action_idx >= 0:
            combined_state_data[:, left_gripper_state_idx] = combined_action_data[:, left_gripper_action_idx]
        
        if right_gripper_state_idx >= 0 and right_gripper_action_idx >= 0:
            combined_state_data[:, right_gripper_state_idx] = combined_action_data[:, right_gripper_action_idx]
        
        return {
            "observation.state": combined_state_data,
            "action": combined_action_data,
        }

    # 该方法将ori_state_data进行后处理，返回结果为后处理后的数据
    def process_episode_state_data(self, ori_state_data: np.ndarray) -> np.ndarray:
        new_state_data = ori_state_data.copy()
        return new_state_data

    # 该方法将ori_action_data进行后处理，返回结果为后处理后的数据
    def process_episode_action_data(self, ori_action_data: np.ndarray) -> np.ndarray:
        new_action_data = ori_action_data.copy()
        return new_action_data

    # 在这里填入修改后的state特征名称列表，返回目标特征名称（映射表的键）
    def get_modified_state_feature_names(self) -> list[str]:
        # 如果映射表还未初始化，先调用prepare_processing
        if not hasattr(self, 'state_feature_mapping'):
            self.prepare_processing()
        return list(self.state_feature_mapping.keys())

    # 在这里填入修改后的action特征名称列表，返回目标特征名称（映射表的键）
    def get_modified_action_feature_names(self) -> list[str]:
        # 如果映射表还未初始化，先调用prepare_processing
        if not hasattr(self, 'action_feature_mapping'):
            self.prepare_processing()
        return list(self.action_feature_mapping.keys())