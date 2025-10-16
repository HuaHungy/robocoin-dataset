from pathlib import Path

from robocoin_dataset.annotation.motion_annotation.compute_lerobot_eef import LerobotFkSolverConfig


class AgilexCobotMagicConfig(LerobotFkSolverConfig):
    mjcf_path = (
        Path(__file__).parent / "mjcfs/agilex_cobot_magic/aloha_new/aloha_new_v00_with_sites.xml"
    )
    state_lejoint_mjcfjoints_dict = {
        "left_arm_joint_1_rad": "fl_joint1",
        "left_arm_joint_2_rad": "fl_joint2",
        "left_arm_joint_3_rad": "fl_joint3",
        "left_arm_joint_4_rad": "fl_joint4",
        "left_arm_joint_5_rad": "fl_joint5",
        "left_arm_joint_6_rad": "fl_joint6",
        "right_arm_joint_1_rad": "fr_joint1",
        "right_arm_joint_2_rad": "fr_joint2",
        "right_arm_joint_3_rad": "fr_joint3",
        "right_arm_joint_4_rad": "fr_joint4",
        "right_arm_joint_5_rad": "fr_joint5",
        "right_arm_joint_6_rad": "fr_joint6",
    }
    action_lejoint_mjcfjoints_dict = state_lejoint_mjcfjoints_dict

    left_arm_state_eefpos_list = ["left_eef_pos_x_m", "left_eef_pos_y_m", "left_eef_pos_z_m"]
    right_arm_state_eefpos_list = ["right_eef_pos_x_m", "right_eef_pos_y_m", "right_eef_pos_z_m"]
    left_arm_state_eefeuler_list = [
        "left_eef_rot_euler_x_rad",
        "left_eef_rot_euler_y_rad",
        "left_eef_rot_euler_z_rad",
    ]
    right_arm_state_eefeuler_list = [
        "right_eef_rot_euler_x_rad",
        "right_eef_rot_euler_y_rad",
        "right_eef_rot_euler_z_rad",
    ]

    left_arm_action_eefpos_list = left_arm_state_eefpos_list
    right_arm_action_eefpos_list = right_arm_state_eefpos_list
    left_arm_action_eefeuler_list = left_arm_state_eefeuler_list
    right_arm_action_eefeuler_list = right_arm_state_eefeuler_list


class AgilexCobotMagicWithoutEEFConfig(LerobotFkSolverConfig):
    mjcf_path = (
        Path(__file__).parent / "mjcfs/agilex_cobot_magic/aloha_new/aloha_new_v00_with_sites.xml"
    )
    state_lejoint_mjcfjoints_dict = {
        "left_arm_joint_1_rad": "fl_joint1",
        "left_arm_joint_2_rad": "fl_joint2",
        "left_arm_joint_3_rad": "fl_joint3",
        "left_arm_joint_4_rad": "fl_joint4",
        "left_arm_joint_5_rad": "fl_joint5",
        "left_arm_joint_6_rad": "fl_joint6",
        "right_arm_joint_1_rad": "fr_joint1",
        "right_arm_joint_2_rad": "fr_joint2",
        "right_arm_joint_3_rad": "fr_joint3",
        "right_arm_joint_4_rad": "fr_joint4",
        "right_arm_joint_5_rad": "fr_joint5",
        "right_arm_joint_6_rad": "fr_joint6",
    }
    action_lejoint_mjcfjoints_dict = state_lejoint_mjcfjoints_dict

    left_arm_state_eefpos_list = []
    right_arm_state_eefpos_list = []
    left_arm_state_eefeuler_list = []
    right_arm_state_eefeuler_list = []

    left_arm_action_eefpos_list = left_arm_state_eefpos_list
    right_arm_action_eefpos_list = right_arm_state_eefpos_list
    left_arm_action_eefeuler_list = left_arm_state_eefeuler_list
    right_arm_action_eefeuler_list = right_arm_state_eefeuler_list
