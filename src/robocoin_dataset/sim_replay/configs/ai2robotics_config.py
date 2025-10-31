from pathlib import Path

from robocoin_dataset.sim_replay.configs.lerobot_sim_replay_config import (
    LerobotSimReplayConfig,
)


class Ai2roboticsLerobotSimReplayConfig(LerobotSimReplayConfig):
    mjcf_path = (
        Path(__file__).parent
        / "mjcfs/ai2robotics/Bot1S_RM75_6FB_2Fgripper_A_description_with_sites.xml"
    )

    # fixed
    left_eef_mjcf_site_name: str = "left_eef_site"
    right_eef_mjcf_site_name: str = "right_eef_site"

    # joint_names should be 1 v 1 assignment
    state_arm_joint_mjcf_names: list[str] = [
        # left arm
        "RM75_6FB_l_joint_1",
        "RM75_6FB_l_joint_2",
        "RM75_6FB_l_joint_3",
        "RM75_6FB_l_joint_4",
        "RM75_6FB_l_joint_5",
        "RM75_6FB_l_joint_6",
        "RM75_6FB_l_joint7",
        # right arm
        "RM75_6FB_r_joint_1",
        "RM75_6FB_r_joint_2",
        "RM75_6FB_r_joint_3",
        "RM75_6FB_r_joint_4",
        "RM75_6FB_r_joint_5",
        "RM75_6FB_r_joint_6",
        "RM75_6FB_r_joint7",
    ]
    action_arm_joint_mjcf_names = state_arm_joint_mjcf_names
    state_arm_joint_lerobot_names: list[str] = [
        # left arm
        "left_arm_joint_0",
        "left_arm_joint_1",
        "left_arm_joint_2",
        "left_arm_joint_3",
        "left_arm_joint_4",
        "left_arm_joint_5",
        "left_arm_joint_6",
        # right arm
        "right_arm_joint_0",
        "right_arm_joint_1",
        "right_arm_joint_2",
        "right_arm_joint_3",
        "right_arm_joint_4",
        "right_arm_joint_5",
        "right_arm_joint_6",
    ]

    action_arm_joint_lerobot_names: list[str] = [
        # left arm
        "left_arm_joint_0",
        "left_arm_joint_1",
        "left_arm_joint_2",
        "left_arm_joint_3",
        "left_arm_joint_4",
        "left_arm_joint_5",
        "left_arm_joint_6",
        # right arm
        "right_arm_joint_0",
        "right_arm_joint_1",
        "right_arm_joint_2",
        "right_arm_joint_3",
        "right_arm_joint_4",
        "right_arm_joint_5",
        "right_arm_joint_6",
    ]

 # gripper names allow not 1v1 assignment
    state_gripper_joint_mjcf_names: list[str] = []
    action_gripper_joint_mjcf_names = state_gripper_joint_mjcf_names


    # eef_sim 配置
    has_gripper = False


    state_gripper_lerobot_names: list[str] = ["left_effector_position", "right_effector_position"]
    action_gripper_lerobot_names: list[str] = [
        "left_effector_position",
        "right_effector_position",
    ]
    def get_mjcf_gripper_joint_data(self, lerobot_gripper_data: list[float]) -> list[float]:
        return []
    
