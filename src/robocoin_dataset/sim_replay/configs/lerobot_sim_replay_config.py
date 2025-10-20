from pathlib import Path


class LerobotSimReplayConfig:
    mjcf_path: str | Path | None = None

    mjcf_site_names: list[str] = ["left_eef_site", "right_eef_site"]

    # joint_names should be 1 v 1 assignment
    state_arm_joint_mjcf_names: list[str] | None = None
    state_arm_joint_lerobot_names: list[str] | None = None

    action_arm_joint_mjcf_names: list[str] | None = None
    action_arm_joint_lerobot_names: list[str] | None = None

    # gripper names allow not 1v1 assignment
    state_gripper_joint_mjcf_names: list[str] | None = None
    state_gripper_lerobot_names: list[str] | None = None

    action_gripper_joint_mjcf_names: list[str] | None = None
    action_gripper_lerobot_names: list[str] | None = None

    def get_mjcf_gripper_joint_data(self, lerobot_gripper_data: list[float]) -> list[float]:
        raise NotImplementedError
