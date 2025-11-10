from pathlib import Path

from robocoin_dataset.sim_replay.configs.lerobot_sim_replay_config import (
    LerobotSimReplayConfig,
)


class AlphaBot2LerobotSimReplayConfig(LerobotSimReplayConfig):
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
        # "left_arm_joint_0_rad",
        "left_arm_joint_1_rad",
        "left_arm_joint_2_rad",
        "left_arm_joint_3_rad",
        "left_arm_joint_4_rad",
        "left_arm_joint_5_rad",
        "left_arm_joint_6_rad",
        "left_arm_joint_7_rad",
        # right arm
        # "right_arm_joint_0_rad",
        "right_arm_joint_1_rad",
        "right_arm_joint_2_rad",
        "right_arm_joint_3_rad",
        "right_arm_joint_4_rad",
        "right_arm_joint_5_rad",
        "right_arm_joint_6_rad",
        "right_arm_joint_7_rad",
    ]

    action_arm_joint_lerobot_names: list[str] = state_arm_joint_lerobot_names

 # gripper names allow not 1v1 assignment
    state_gripper_joint_mjcf_names: list[str] = []
    action_gripper_joint_mjcf_names = state_gripper_joint_mjcf_names


    # eef_sim 配置
    has_gripper = False


    state_gripper_lerobot_names: list[str] = ["left_gripper_open", "right_gripper_open"]
    action_gripper_lerobot_names: list[str] = [
        "left_gripper_open",
        "right_gripper_open",
    ]
    def get_mjcf_gripper_joint_data(self, lerobot_gripper_data: list[float]) -> list[float]:
        return []
    
