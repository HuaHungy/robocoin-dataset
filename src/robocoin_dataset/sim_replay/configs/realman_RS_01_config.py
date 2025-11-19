from pathlib import Path

from robocoin_dataset.sim_replay.configs.lerobot_sim_replay_config import (
    LerobotSimReplayConfig,
)


class RealmanRS01LerobotSimReplayConfig(LerobotSimReplayConfig):
    mjcf_path = (
        Path(__file__).parent
        / "mjcfs/realman_RS-01/mujoco_model_with_sites.xml"
    )

    # fixed
    left_eef_mjcf_site_name: str = "left_eef_site"
    right_eef_mjcf_site_name: str = "right_eef_site"

    # joint_names should be 1 v 1 assignment
    state_arm_joint_mjcf_names: list[str] = [
        # left arm
        "l_joint1",
        "l_joint2",
        "l_joint3",
        "l_joint4",
        "l_joint5",
        "l_joint6",
        "l_joint7",
        # right arm
        "r_joint1",
        "r_joint2",
        "r_joint3",
        "r_joint4",
        "r_joint5",
        "r_joint6",
        "r_joint7",
    ]
    action_arm_joint_mjcf_names = state_arm_joint_mjcf_names
    state_arm_joint_lerobot_names: list[str] = [
        "LeftFollowerArm_Joint1.pos",
        "LeftFollowerArm_Joint2.pos",
        "LeftFollowerArm_Joint3.pos",
        "LeftFollowerArm_Joint4.pos",
        "LeftFollowerArm_Joint5.pos",
        "LeftFollowerArm_Joint6.pos",
        "LeftFollowerArm_Joint7.pos",

        "RightFollowerArm_Joint1.pos",
        "RightFollowerArm_Joint2.pos",
        "RightFollowerArm_Joint3.pos",
        "RightFollowerArm_Joint4.pos",
        "RightFollowerArm_Joint5.pos",
        "RightFollowerArm_Joint6.pos",
        "RightFollowerArm_Joint7.pos",

    ]


    action_arm_joint_lerobot_names: list[str] = [
        "LeftLeaderArm_Joint1.pos",
        "LeftLeaderArm_Joint2.pos",
        "LeftLeaderArm_Joint3.pos",
        "LeftLeaderArm_Joint4.pos",
        "LeftLeaderArm_Joint5.pos",
        "LeftLeaderArm_Joint6.pos",
        "LeftLeaderArm_Joint7.pos",

        "RightLeaderArm_Joint1.pos",
        "RightLeaderArm_Joint2.pos",
        "RightLeaderArm_Joint3.pos",
        "RightLeaderArm_Joint4.pos",
        "RightLeaderArm_Joint5.pos",
        "RightLeaderArm_Joint6.pos",
        "RightLeaderArm_Joint7.pos",
    ]
    
     # gripper names allow not 1v1 assignment
    state_gripper_joint_mjcf_names: list[str] = []
    action_gripper_joint_mjcf_names = state_gripper_joint_mjcf_names

    state_gripper_lerobot_names: list[str] = [
        "LeftGripper.pos",
        "RightGripper.pos",
    ]
    action_gripper_lerobot_names = state_gripper_lerobot_names

    def get_mjcf_gripper_joint_data(self, lerobot_gripper_data: list[float]) -> list[float]:
        return []