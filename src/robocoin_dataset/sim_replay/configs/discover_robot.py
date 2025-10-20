from pathlib import Path

from robocoin_dataset.annotation.motion_annotation.lerobot_sim_replay import (
    LerobotFkSolverConfig,
)



class DiscoverMmk2Config(LerobotFkSolverConfig):
    mjcf_path = (
        Path(__file__).parent
        / "mjcfs/galaxea_r1_lite/mmp_revB_invconfig_upright_a1x_with_sites.xml"
    )
    state_lejoint_mjcfjoints_dict = {}

    action_lejoint_mjcfjoints_dict = {}

    left_arm_state_eefpos_list = []
    right_arm_state_eefpos_list = []
    left_arm_state_eefeuler_list = []
    right_arm_state_eefeuler_list = []

    left_arm_action_eefpos_list = left_arm_state_eefpos_list
    right_arm_action_eefpos_list = right_arm_state_eefpos_list
    left_arm_action_eefeuler_list = left_arm_state_eefeuler_list
    right_arm_action_eefeuler_list = right_arm_state_eefeuler_list
