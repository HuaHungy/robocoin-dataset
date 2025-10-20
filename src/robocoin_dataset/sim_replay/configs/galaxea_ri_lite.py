from pathlib import Path

from robocoin_dataset.annotation.motion_annotation.lerobot_sim_replay import (
    LerobotFkSolverConfig,
)


class GalaxeaR1LiteConfig(LerobotFkSolverConfig):
    mjcf_path = (
        Path(__file__).parent
        / "mjcfs/galaxea_r1_lite/mmp_revB_invconfig_upright_a1x_with_sites.xml"
    )
    state_lejoint_mjcfjoints_dict = {
        "torso_joint_1": "torso_joint1",
        "torso_joint_2": "torso_joint2",
        # "torso_joint_3": "torso_joint3",
        "chassis_wheel_1": "wheel_motor_joint1",
        "chassis_wheel_2": "wheel_motor_joint2",
        "chassis_wheel_3": "wheel_motor_joint3",
        "left_arm_joint_1": "left_arm_joint1",
        "left_arm_joint_2": "left_arm_joint2",
        "left_arm_joint_3": "left_arm_joint3",
        "left_arm_joint_4": "left_arm_joint4",
        "left_arm_joint_5": "left_arm_joint5",
        "left_arm_joint_6": "left_arm_joint6",
        # "left_arm_joint_7": "left_gripper_joint",
        "right_arm_joint_1": "right_arm_joint1",
        "right_arm_joint_2": "right_arm_joint2",
        "right_arm_joint_3": "right_arm_joint3",
        "right_arm_joint_4": "right_arm_joint4",
        "right_arm_joint_5": "right_arm_joint5",
        "right_arm_joint_6": "right_arm_joint6",
        # "right_arm_joint_7": "right_gripper_joint",
    }

    action_lejoint_mjcfjoints_dict = {
        "left_arm_target_joint_1": "left_arm_joint1",
        "left_arm_target_joint_2": "left_arm_joint2",
        "left_arm_target_joint_3": "left_arm_joint3",
        "left_arm_target_joint_4": "left_arm_joint4",
        "left_arm_target_joint_5": "left_arm_joint5",
        "left_arm_target_joint_6": "left_arm_joint6",
        # "left_gripper_target_position": "left_gripper_joint",
        "right_arm_target_joint_1": "right_arm_joint1",
        "right_arm_target_joint_2": "right_arm_joint2",
        "right_arm_target_joint_3": "right_arm_joint3",
        "right_arm_target_joint_4": "right_arm_joint4",
        "right_arm_target_joint_5": "right_arm_joint5",
        "right_arm_target_joint_6": "right_arm_joint6",
        # "right_gripper_target_position": "right_gripper_joint",
    }

    left_arm_state_eefpos_list = []
    right_arm_state_eefpos_list = []
    left_arm_state_eefeuler_list = []
    right_arm_state_eefeuler_list = []

    left_arm_action_eefpos_list = left_arm_state_eefpos_list
    right_arm_action_eefpos_list = right_arm_state_eefpos_list
    left_arm_action_eefeuler_list = left_arm_state_eefeuler_list
    right_arm_action_eefeuler_list = right_arm_state_eefeuler_list
