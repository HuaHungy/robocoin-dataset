from pathlib import Path

from robocoin_dataset.annotation.motion_annotation.compute_lerobot_eef import LerobotFkSolverConfig


class RealmanRmcAidalConfig(LerobotFkSolverConfig):
    mjcf_path = (
        Path(__file__).parent
        / "mjcfs/realman_rmc_aidal/overseas_75_b_v_description_rmg24_with_sites.xml"
    )
    left_arm_state_mjcf_joints_dict = {
        "left_arm_joint_1_rad": "l_joint1",
        "left_arm_joint_2_rad": "l_joint2",
        "left_arm_joint_3_rad": "l_joint3",
        "left_arm_joint_4_rad": "l_joint4",
        "left_arm_joint_5_rad": "l_joint5",
        "left_arm_joint_6_rad": "l_joint6",
        "left_arm_joint_7_rad": "l_joint7",
    }

    right_arm_state_mjcf_joints_dict = {
        "right_arm_joint_1_rad": "r_joint1",
        "right_arm_joint_2_rad": "r_joint2",
        "right_arm_joint_3_rad": "r_joint3",
        "right_arm_joint_4_rad": "r_joint4",
        "right_arm_joint_5_rad": "r_joint5",
        "right_arm_joint_6_rad": "r_joint6",
        "right_arm_joint_7_rad": "r_joint7",
    }

    left_arm_action_mjcf_joints_dict = left_arm_state_mjcf_joints_dict
    right_arm_action_mjcf_joints_dict = right_arm_state_mjcf_joints_dict

    left_arm_state_eefpos_list = ["left_eef_pos_x_m", "left_eef_pos_y_m", "left_eef_pos_z_m"]
    right_arm_state_eefpos_list = ["right_eef_pos_x_m", "right_eef_pos_y_m", "right_eef_pos_z_m"]

    left_arm_action_eefpos_list = left_arm_state_eefpos_list
    right_arm_action_eefpos_list = right_arm_state_eefpos_list

    left_arm_state_eefeuler_list = [
        "left_eef_rot_euler_x_rad",
        "left_eef_rot_euler_y_rad",
        "left_eef_rot_euler_z_rad",
    ]
    left_arm_action_eefeuler_list = left_arm_state_eefeuler_list

    right_arm_state_eefeuler_list = [
        "right_eef_rot_euler_x_rad",
        "right_eef_rot_euler_y_rad",
        "right_eef_rot_euler_z_rad",
    ]
    right_arm_action_eefeuler_list = right_arm_state_eefeuler_list
