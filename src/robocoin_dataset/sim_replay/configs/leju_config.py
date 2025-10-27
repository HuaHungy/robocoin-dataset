from pathlib import Path

from robocoin_dataset.sim_replay.configs.lerobot_sim_replay_config import (
    LerobotSimReplayConfig,
)


class LejuLerobotSimReplayConfig(LerobotSimReplayConfig):
    mjcf_path = Path(__file__).parent / "mjcfs/leju/biped_s49_with_sites.xml"

    left_eef_mjcf_site_name: str = "left_eef_site"
    right_eef_mjcf_site_name: str = "right_eef_site"

    # joint_names should be 1 v 1 assignment
    state_arm_joint_mjcf_names: list[str] = [
        # left arm
        "zarm_l1_joint",
        "zarm_l2_joint",
        "zarm_l3_joint",
        "zarm_l4_joint",
        "zarm_l5_joint",
        "zarm_l6_joint",
        "zarm_l7_joint",
        # right arm
        "zarm_r1_joint",
        "zarm_r2_joint",
        "zarm_r3_joint",
        "zarm_r4_joint",
        "zarm_r5_joint",
        "zarm_r6_joint",
        "zarm_r7_joint",
    ]
    action_arm_joint_mjcf_names = state_arm_joint_mjcf_names
    state_arm_joint_lerobot_names: list[str] = [
        # left arm
        "left_arm_joint_1_rad",
        "left_arm_joint_2_rad",
        "left_arm_joint_3_rad",
        "left_arm_joint_4_rad",
        "left_arm_joint_5_rad",
        "left_arm_joint_6_rad",
        "left_arm_joint_7_rad",
        # right arm
        "right_arm_joint_1_rad",
        "right_arm_joint_2_rad",
        "right_arm_joint_3_rad",
        "right_arm_joint_4_rad",
        "right_arm_joint_5_rad",
        "right_arm_joint_6_rad",
        "right_arm_joint_7_rad",
    ]

    action_arm_joint_lerobot_names = state_arm_joint_lerobot_names

    # gripper names allow not 1v1 assignment
    state_gripper_joint_mjcf_names: list[str] = []
    action_gripper_joint_mjcf_names = state_gripper_joint_mjcf_names

    state_gripper_lerobot_names: list[str] = [
        # left_hand
        "left_hand_joint_1_rad",
        "left_hand_joint_2_rad",
        "left_hand_joint_3_rad",
        "left_hand_joint_4_rad",
        "left_hand_joint_5_rad",
        "left_hand_joint_6_rad",
        "left_hand_joint_7_rad",
        # right hand
        "right_hand_joint_1_rad",
        "right_hand_joint_2_rad",
        "right_hand_joint_3_rad",
        "right_hand_joint_4_rad",
        "right_hand_joint_5_rad",
        "right_hand_joint_6_rad",
        "right_hand_joint_7_rad",
    ]
    action_gripper_lerobot_names = state_gripper_lerobot_names

    def get_mjcf_gripper_joint_data(self, lerobot_gripper_data: list[float]) -> list[float]:
        return []
