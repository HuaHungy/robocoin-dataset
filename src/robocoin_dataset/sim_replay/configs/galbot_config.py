from pathlib import Path

from robocoin_dataset.sim_replay.configs.lerobot_sim_replay_config import (
    LerobotSimReplayConfig,
)


class GalbotLerobotSimReplayConfig(LerobotSimReplayConfig):
    mjcf_path = (
        Path(__file__).parent
        / "mjcfs/galbot/galbot_one_golf_with_sites.xml"
    )

    # fixed
    left_eef_mjcf_site_name: str = "left_eef_site"
    right_eef_mjcf_site_name: str = "right_eef_site"

    # joint_names should be 1 v 1 assignment
    state_arm_joint_mjcf_names: list[str] = [
        # left arm
        "left_arm_joint1",
        "left_arm_joint2",
        "left_arm_joint3",
        "left_arm_joint4",
        "left_arm_joint5",
        "left_arm_joint6",
        "left_arm_joint7",
        # right arm
        "right_arm_joint1",
        "right_arm_joint2",
        "right_arm_joint3",
        "right_arm_joint4",
        "right_arm_joint5",
        "right_arm_joint6",
        "right_arm_joint7",

        # left_hand
        # "left_gripper_finger_joint1",
        # "left_gripper_finger_joint2",
        # right hand
        # "left_gripper_finger_joint1",
        # "left_gripper_finger_joint2",
        # torso
        "leg_joint1",
        "leg_joint2",
        "leg_joint3",
    ]
    action_arm_joint_mjcf_names = state_arm_joint_mjcf_names
    state_arm_joint_lerobot_names: list[str] = [
        # left arm
        "left_arm_joint_1",
        "left_arm_joint_2",
        "left_arm_joint_3",
        "left_arm_joint_4",
        "left_arm_joint_5",
        "left_arm_joint_6",
        "left_arm_joint_7",
        # right arm
        "right_arm_joint_1",
        "right_arm_joint_2",
        "right_arm_joint_3",
        "right_arm_joint_4",
        "right_arm_joint_5",
        "right_arm_joint_6",
        "right_arm_joint_7",
        # torso
        "torso_joint_1",
        "torso_joint_2",
        "torso_joint_3",
    ]

    action_arm_joint_lerobot_names: list[str] = [
        # left arm
        "left_arm_target_joint_1",
        "left_arm_target_joint_2",
        "left_arm_target_joint_3",
        "left_arm_target_joint_4",
        "left_arm_target_joint_5",
        "left_arm_target_joint_6",
        "left_arm_target_joint_7",
        # right arm
        "right_arm_target_joint_1",
        "right_arm_target_joint_2",
        "right_arm_target_joint_3",
        "right_arm_target_joint_4",
        "right_arm_target_joint_5",
        "right_arm_target_joint_6",
        "right_arm_target_joint_7",
    ]

    