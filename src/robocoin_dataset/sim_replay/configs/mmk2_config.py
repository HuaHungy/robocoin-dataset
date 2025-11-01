from pathlib import Path

from robocoin_dataset.sim_replay.configs.lerobot_sim_replay_config import (
    LerobotSimReplayConfig,
)


class Mmk2LerobotSimReplayConfig(LerobotSimReplayConfig):
    mjcf_path = (
        Path(__file__).parent
        / "mjcfs/mmk2/mmk2_with_sites.xml"
    )

    # fixed
    left_eef_mjcf_site_name: str = "left_eef_site"
    right_eef_mjcf_site_name: str = "right_eef_site"

    # joint_names should be 1 v 1 assignment
    state_arm_joint_mjcf_names: list[str] = [
        # left arm
        "lftarm_joint1",
        "lftarm_joint2",
        "lftarm_joint3",
        "lftarm_joint4",
        "lftarm_joint5",
        "lftarm_joint6",
        # right arm
        "rgtarm_joint1",
        "rgtarm_joint2",
        "rgtarm_joint3",
        "rgtarm_joint4",
        "rgtarm_joint5",
        "rgtarm_joint6",
        # # left_hand
        # "left_hand_thumb_bend_joint",
        # "left_hand_thumb_rota_joint1",
        # "left_hand_thumb_rota_joint2",
        # "left_hand_index_bend_joint",
        # "left_hand_index_joint1",
        # "left_hand_index_joint2",
        # "left_hand_mid_joint1",
        # "left_hand_mid_joint2",
        # "left_hand_ring_joint1",
        # "left_hand_ring_joint2",
        # "left_hand_pinky_joint1",
        # "left_hand_pinky_joint2",
        # # right hand
        # "right_hand_thumb_bend_joint",
        # "right_hand_thumb_rota_joint1",
        # "right_hand_thumb_rota_joint2",
        # "right_hand_index_bend_joint",
        # "right_hand_index_joint1",
        # "right_hand_index_joint2",
        # "right_hand_mid_joint1",
        # "right_hand_mid_joint2",
        # "right_hand_ring_joint1",
        # "right_hand_ring_joint2",
        # "right_hand_pinky_joint1",
        # "right_hand_pinky_joint2",        
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
        # right arm
        "right_arm_joint_1_rad",
        "right_arm_joint_2_rad",
        "right_arm_joint_3_rad",
        "right_arm_joint_4_rad",
        "right_arm_joint_5_rad",
        "right_arm_joint_6_rad",
        # left hand
        # "left_hand_joint_1_rad",
        # "left_hand_joint_2_rad",
        # "left_hand_joint_3_rad",
        # "left_hand_joint_4_rad",
        # "left_hand_joint_5_rad",
        # "left_hand_joint_6_rad",
        # "left_hand_joint_7_rad",
        # "left_hand_joint_8_rad",
        # "left_hand_joint_9_rad",
        # "left_hand_joint_10_rad",
        # "left_hand_joint_11_rad",
        # "left_hand_joint_12_rad",
        # right hand
        # "right_hand_joint_1_rad",
        # "right_hand_joint_2_rad",
        # "right_hand_joint_3_rad",
        # "right_hand_joint_4_rad",
        # "right_hand_joint_5_rad",
        # "right_hand_joint_6_rad", 
        # "right_hand_joint_7_rad",
        # "right_hand_joint_8_rad",
        # "right_hand_joint_9_rad",
        # "right_hand_joint_10_rad",
        # "right_hand_joint_11_rad",
        # "right_hand_joint_12_rad",
    ]

    action_arm_joint_lerobot_names: list[str] = [
        # left arm
        "left_arm_joint_1_rad",
        "left_arm_joint_2_rad",
        "left_arm_joint_3_rad",
        "left_arm_joint_4_rad",
        "left_arm_joint_5_rad",
        "left_arm_joint_6_rad",
        # right arm
        "right_arm_joint_1_rad",
        "right_arm_joint_2_rad",
        "right_arm_joint_3_rad",
        "right_arm_joint_4_rad",
        "right_arm_joint_5_rad",
        "right_arm_joint_6_rad",
        # left hand
        # "left_hand_action_1_rad",
        # "left_hand_action_2_rad",
        # "left_hand_action_3_rad",
        # "left_hand_action_4_rad",
        # "left_hand_action_5_rad",
        # "left_hand_action_6_rad",
        # "left_hand_action_7_rad",
        # "left_hand_action_8_rad",
        # "left_hand_action_9_rad",
        # "left_hand_action_10_rad",
        # "left_hand_action_11_rad",
        # "left_hand_action_12_rad",
        # right hand
        # "right_hand_action_1_rad",
        # "right_hand_action_2_rad",
        # "right_hand_action_3_rad",
        # "right_hand_action_4_rad",
        # "right_hand_action_5_rad",
        # "right_hand_action_6_rad",
        # "right_hand_action_7_rad",
        # "right_hand_action_8_rad",
        # "right_hand_action_9_rad",
        # "right_hand_action_10_rad",
        # "right_hand_action_11_rad",
        # "right_hand_action_12_rad"
    ]
    # gripper names allow not 1v1 assignment
    state_gripper_joint_mjcf_names: list[str] = []
    action_gripper_joint_mjcf_names = state_gripper_joint_mjcf_names

    state_gripper_lerobot_names: list[str] = [
        # left hand
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
        # right hand
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
        "right_hand_joint_12_rad",
    ]
    action_gripper_lerobot_names: list[str] = [
        # left hand
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
        # right hand
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
    def get_mjcf_gripper_joint_data(self, lerobot_gripper_data: list[float]) -> list[float]:
        return []