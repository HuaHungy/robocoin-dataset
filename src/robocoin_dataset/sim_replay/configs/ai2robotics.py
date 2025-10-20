from pathlib import Path

from robocoin_dataset.annotation.motion_annotation.lerobot_sim_replay import (
    LerobotFkSolverConfig,
)


class Ai2RoboticsConfig(LerobotFkSolverConfig):
    mjcf_path = (
        Path(__file__).parent
        / "mjcfs/realman_rmc_aidal/overseas_75_b_v_description_rmg24_with_sites.xml"
    )
    state_lejoint_mjcfjoints_dict = {}
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
