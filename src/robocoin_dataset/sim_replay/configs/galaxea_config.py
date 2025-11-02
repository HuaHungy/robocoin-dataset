from pathlib import Path

from robocoin_dataset.sim_replay.configs.lerobot_sim_replay_config import (
    LerobotSimReplayConfig,
)


class GalaxeaR1LiteLerobotSimReplayConfig(LerobotSimReplayConfig):
    mjcf_path = (
        Path(__file__).parent
        / "mjcfs/galaxea_r1_lite/mmp_revB_invconfig_upright_a1x_with_sites.xml"
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
        # right arm
        "right_arm_joint1",
        "right_arm_joint2",
        "right_arm_joint3",
        "right_arm_joint4",
        "right_arm_joint5",
        "right_arm_joint6",
        # left_hand
        # "left_gripper_finger_joint1",
        # "left_gripper_finger_joint2",
        # right hand
        # "left_gripper_finger_joint1",
        # "left_gripper_finger_joint2",
        # torso
        "torso_joint1",
        "torso_joint2",
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
        # right arm
        "right_arm_joint_1",
        "right_arm_joint_2",
        "right_arm_joint_3",
        "right_arm_joint_4",
        "right_arm_joint_5",
        "right_arm_joint_6",
        # torso
        # "torso_joint_1",
        # "torso_joint_2",
    ]

    action_arm_joint_lerobot_names: list[str] = [
        # left arm
        "left_arm_target_joint_1",
        "left_arm_target_joint_2",
        "left_arm_target_joint_3",
        "left_arm_target_joint_4",
        "left_arm_target_joint_5",
        "left_arm_target_joint_6",
        # right arm
        "right_arm_target_joint_1",
        "right_arm_target_joint_2",
        "right_arm_target_joint_3",
        "right_arm_target_joint_4",
        "right_arm_target_joint_5",
        "right_arm_target_joint_6",
    ]

    # gripper names allow not 1v1 assignment
    state_gripper_joint_mjcf_names: list[str] = [
        "left_gripper_finger_joint1",
        "left_gripper_finger_joint2",
        "right_gripper_finger_joint1",
        "right_gripper_finger_joint2",
    ]
    action_gripper_joint_mjcf_names = state_gripper_joint_mjcf_names

    state_gripper_lerobot_names: list[str] = ["left_gripper_position", "right_gripper_position"]
    action_gripper_lerobot_names: list[str] = [
        "left_gripper_target_position",
        "right_gripper_target_position",
    ]

    gripper_position_max = 100
    gripper_position_min = 0
    gripper_mjcf_joint_max = 0.05
    gripper_mjcf_joint_min = 0

    def get_mjcf_gripper_joint_data(self, lerobot_gripper_data: list[float]) -> list[float]:
        lflj_joint_data = (
            (self.gripper_mjcf_joint_max - self.gripper_mjcf_joint_min)
            * (lerobot_gripper_data[0] - self.gripper_position_min)
            / (self.gripper_position_max - self.gripper_position_min)
        )
        lfrj_joint_data = -lflj_joint_data
        rflj_joint_data = (
            (self.gripper_mjcf_joint_max - self.gripper_mjcf_joint_min)
            * (lerobot_gripper_data[1] - self.gripper_position_min)
            / (self.gripper_position_max - self.gripper_position_min)
        )
        rfrj_joint_data = -rflj_joint_data
        return [lflj_joint_data, lfrj_joint_data, rflj_joint_data, rfrj_joint_data]


class GalaxeaR1LiteH5Mp4LerobotSimReplayConfig(LerobotSimReplayConfig):
    mjcf_path = (
        Path(__file__).parent
        / "mjcfs/galaxea_r1_lite/mmp_revB_invconfig_upright_a1x_with_sites.xml"
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
        # right arm
        "right_arm_joint1",
        "right_arm_joint2",
        "right_arm_joint3",
        "right_arm_joint4",
        "right_arm_joint5",
        "right_arm_joint6",
        # left_hand
        # "left_gripper_finger_joint1",
        # "left_gripper_finger_joint2",
        # right hand
        # "left_gripper_finger_joint1",
        # "left_gripper_finger_joint2",
        # torso
        "torso_joint1",
        "torso_joint2",
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
        # right arm
        "right_arm_joint_1",
        "right_arm_joint_2",
        "right_arm_joint_3",
        "right_arm_joint_4",
        "right_arm_joint_5",
        "right_arm_joint_6",
        # torso
        # "torso_joint_1",
        # "torso_joint_2",
    ]

    action_arm_joint_lerobot_names: list[str] = [
        # left arm
        "left_arm_target_joint_1",
        "left_arm_target_joint_2",
        "left_arm_target_joint_3",
        "left_arm_target_joint_4",
        "left_arm_target_joint_5",
        "left_arm_target_joint_6",
        # right arm
        "right_arm_target_joint_1",
        "right_arm_target_joint_2",
        "right_arm_target_joint_3",
        "right_arm_target_joint_4",
        "right_arm_target_joint_5",
        "right_arm_target_joint_6",
    ]

    # gripper names allow not 1v1 assignment
    state_gripper_joint_mjcf_names: list[str] = [
        "left_gripper_finger_joint1",
        "left_gripper_finger_joint2",
        "right_gripper_finger_joint1",
        "right_gripper_finger_joint2",
    ]
    action_gripper_joint_mjcf_names = state_gripper_joint_mjcf_names

    state_gripper_lerobot_names: list[str] = ["left_gripper_position", "right_gripper_position"]
    action_gripper_lerobot_names: list[str] = [
        "left_gripper_target_position",
        "right_gripper_target_position",
    ]

    gripper_position_max = 1.75
    gripper_position_min = 0
    gripper_mjcf_joint_max = 0.05
    gripper_mjcf_joint_min = 0

    def get_mjcf_gripper_joint_data(self, lerobot_gripper_data: list[float]) -> list[float]:
        lflj_joint_data = (
            (self.gripper_mjcf_joint_max - self.gripper_mjcf_joint_min)
            * (lerobot_gripper_data[0] - self.gripper_position_min)
            / (self.gripper_position_max - self.gripper_position_min)
        )
        lfrj_joint_data = -lflj_joint_data
        rflj_joint_data = (
            (self.gripper_mjcf_joint_max - self.gripper_mjcf_joint_min)
            * (lerobot_gripper_data[1] - self.gripper_position_min)
            / (self.gripper_position_max - self.gripper_position_min)
        )
        rfrj_joint_data = -rflj_joint_data
        return [lflj_joint_data, lfrj_joint_data, rflj_joint_data, rfrj_joint_data]
