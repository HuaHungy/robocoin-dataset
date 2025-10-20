from pathlib import Path

from ..lerobot_sim_replayer import LerobotFkSolverConfig


class UnitreeG129DofConfig(LerobotFkSolverConfig):
    mjcf_path = Path(__file__).parent / "mjcfs/unitree_g1/g1_29dof.xml"
    state_lejoint_mjcfjoints_dict = {
        "left_arm_joint_1_rad" : "left_shoulder_pitch_joint",
        "left_arm_joint_2_rad" : "left_shoulder_roll_joint",
        "left_arm_joint_3_rad" : "left_shoulder_yaw_joint",
        "left_arm_joint_4_rad" : "left_elbow_joint",
        "left_arm_joint_5_rad" : "left_wrist_roll_joint",
        "left_arm_joint_6_rad" : "left_wrist_pitch_joint",
        "left_arm_joint_7_rad" : "left_wrist_yaw_joint",
        "right_arm_joint_1_rad": "right_shoulder_pitch_joint",
        "right_arm_joint_2_rad": "right_shoulder_roll_joint",
        "right_arm_joint_3_rad": "right_shoulder_yaw_joint",
        "right_arm_joint_4_rad": "right_elbow_joint",
        "right_arm_joint_5_rad": "right_wrist_roll_joint",
        "right_arm_joint_6_rad": "right_wrist_pitch_joint",
        "right_arm_joint_7_rad": "right_wrist_yaw_joint",       
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
