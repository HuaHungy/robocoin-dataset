from pathlib import Path

import numpy as np

from .state_action_data_processor_base import StateActionDataPostProcessorBase


class UnitreeG1Processor(StateActionDataPostProcessorBase):
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

    # 该方法返回处理后的state数据名称
    def get_modified_feature_names(self):
        return super().get_modified_feature_names()

    def get_modified_info_state_names(self) -> dict[str, str]:
        return {}

    # 该方法返回处理后的action数据名称
    def get_modified_info_action_names(self) -> dict[str, str]:
        return {}
    
    def get_modified_state_feature_names(self)-> list[str]:
        return [
        # left arm (7个)
        "left_arm_joint_1_rad",
        "left_arm_joint_2_rad",
        "left_arm_joint_3_rad",
        "left_arm_joint_4_rad",
        "left_arm_joint_5_rad",
        "left_arm_joint_6_rad",
        "left_arm_joint_7_rad",
        # right arm (7个)
        "right_arm_joint_1_rad",
        "right_arm_joint_2_rad",
        "right_arm_joint_3_rad",
        "right_arm_joint_4_rad",
        "right_arm_joint_5_rad",
        "right_arm_joint_6_rad",
        "right_arm_joint_7_rad",
        # left_hand (7个)
        "left_hand_joint_1_rad",
        "left_hand_joint_2_rad",
        "left_hand_joint_3_rad",
        "left_hand_joint_4_rad",
        "left_hand_joint_5_rad",
        "left_hand_joint_6_rad",
        "left_hand_joint_7_rad",
        # right_hand (7个)
        "right_hand_joint_1_rad",
        "right_hand_joint_2_rad",
        "right_hand_joint_3_rad",
        "right_hand_joint_4_rad",
        "right_hand_joint_5_rad",
        "right_hand_joint_6_rad",
        "right_hand_joint_7_rad",
    ]

    def get_modified_action_feature_names(self)-> list[str]:
        return [
        # left arm (7个)
        "left_arm_joint_1_rad",
        "left_arm_joint_2_rad",
        "left_arm_joint_3_rad",
        "left_arm_joint_4_rad",
        "left_arm_joint_5_rad",
        "left_arm_joint_6_rad",
        "left_arm_joint_7_rad",
        # right arm (7个)
        "right_arm_joint_1_rad",
        "right_arm_joint_2_rad",
        "right_arm_joint_3_rad",
        "right_arm_joint_4_rad",
        "right_arm_joint_5_rad",
        "right_arm_joint_6_rad",
        "right_arm_joint_7_rad",
        # left_hand (7个)
        "left_hand_joint_1_rad",
        "left_hand_joint_2_rad",
        "left_hand_joint_3_rad",
        "left_hand_joint_4_rad",
        "left_hand_joint_5_rad",
        "left_hand_joint_6_rad",
        "left_hand_joint_7_rad",
        # right_hand (7个)
        "right_hand_joint_1_rad",
        "right_hand_joint_2_rad",
        "right_hand_joint_3_rad",
        "right_hand_joint_4_rad",
        "right_hand_joint_5_rad",
        "right_hand_joint_6_rad",
        "right_hand_joint_7_rad",
    ]



class UnitreeG1ThreeFingerOutProcessor(StateActionDataPostProcessorBase):
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
    
    def process_episode_data(self, ori_data: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """
        将 action 的手部数据（后14维）复制给 state 的手部数据
        state 和 action 的前14维（双臂）保持不变
        """
        state = ori_data.get("observation.state")
        action = ori_data.get("action")
        
        if state is None or action is None:
            raise ValueError("ori_data must contain 'observation.state' and 'action'")
        
        if not isinstance(state, np.ndarray) or not isinstance(action, np.ndarray):
            raise ValueError("state and action must be numpy arrays")
        
        if state.shape[0] != action.shape[0]:
            raise ValueError("state and action must have same number of frames")
        
        # 复制 state 和 action
        new_state = state.copy()
        new_action = action.copy()
        
        # 将 action 的后14维（手部数据）复制给 state 的后14维
        # 前14维是双臂（左臂7个 + 右臂7个）
        # 后14维是手部（左手7个 + 右手7个）
        new_state[:, 14:] = action[:, 14:]
        
        return {"observation.state": new_state, "action": new_action}


    # 该方法返回处理后的state数据名称
    def get_modified_feature_names(self):
        return super().get_modified_feature_names()

    def get_modified_info_state_names(self) -> dict[str, str]:
        return {}

    # 该方法返回处理后的action数据名称
    def get_modified_info_action_names(self) -> dict[str, str]:
        return {}
    
    def get_modified_state_feature_names(self)-> list[str]:
        return [
        # left arm (7个)
        "left_arm_joint_1_rad",
        "left_arm_joint_2_rad",
        "left_arm_joint_3_rad",
        "left_arm_joint_4_rad",
        "left_arm_joint_5_rad",
        "left_arm_joint_6_rad",
        "left_arm_joint_7_rad",
        # right arm (7个)
        "right_arm_joint_1_rad",
        "right_arm_joint_2_rad",
        "right_arm_joint_3_rad",
        "right_arm_joint_4_rad",
        "right_arm_joint_5_rad",
        "right_arm_joint_6_rad",
        "right_arm_joint_7_rad",
        # left_hand (7个)
        "left_hand_joint_1_rad",
        "left_hand_joint_2_rad",
        "left_hand_joint_3_rad",
        "left_hand_joint_4_rad",
        "left_hand_joint_5_rad",
        "left_hand_joint_6_rad",
        "left_hand_joint_7_rad",
        # right_hand (7个)
        "right_hand_joint_1_rad",
        "right_hand_joint_2_rad",
        "right_hand_joint_3_rad",
        "right_hand_joint_4_rad",
        "right_hand_joint_5_rad",
        "right_hand_joint_6_rad",
        "right_hand_joint_7_rad",
    ]

    def get_modified_action_feature_names(self)-> list[str]:
        return [
        # left arm (7个)
        "left_arm_joint_1_rad",
        "left_arm_joint_2_rad",
        "left_arm_joint_3_rad",
        "left_arm_joint_4_rad",
        "left_arm_joint_5_rad",
        "left_arm_joint_6_rad",
        "left_arm_joint_7_rad",
        # right arm (7个)
        "right_arm_joint_1_rad",
        "right_arm_joint_2_rad",
        "right_arm_joint_3_rad",
        "right_arm_joint_4_rad",
        "right_arm_joint_5_rad",
        "right_arm_joint_6_rad",
        "right_arm_joint_7_rad",
        # left_hand (7个)
        "left_hand_joint_1_rad",
        "left_hand_joint_2_rad",
        "left_hand_joint_3_rad",
        "left_hand_joint_4_rad",
        "left_hand_joint_5_rad",
        "left_hand_joint_6_rad",
        "left_hand_joint_7_rad",
        # right_hand (7个)
        "right_hand_joint_1_rad",
        "right_hand_joint_2_rad",
        "right_hand_joint_3_rad",
        "right_hand_joint_4_rad",
        "right_hand_joint_5_rad",
        "right_hand_joint_6_rad",
        "right_hand_joint_7_rad",
    ]


# class UnitreeG1FiveFingerHandProcessor(StateActionDataPostProcessorBase):
#     def __init__(self, convert_path: str | Path) -> None:
#         super().__init__(convert_path)

#     def prepare_processing(self) -> None:
#         pass

#     # 该方法将ori_state_data进行后处理，返回结果为后处理后的数据
#     def process_episode_state_data(self, ori_state_data: np.ndarray) -> np.ndarray:
#         return ori_state_data.copy()

#     # 该方法将ori_action_data进行后处理，返回结果为后处理后的数据
#     def process_episode_action_data(self, ori_action_data: np.ndarray) -> np.ndarray:
#         return ori_action_data.copy()

#     # 该方法返回处理后的state数据名称
#     def get_modified_feature_names(self):
#         return super().get_modified_feature_names()

#     def get_modified_info_state_names(self) -> dict[str, str]:
#         return {}

#     # 该方法返回处理后的action数据名称
#     def get_modified_info_action_names(self) -> dict[str, str]:
#         return {}
