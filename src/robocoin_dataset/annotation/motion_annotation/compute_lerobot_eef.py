import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .mujoco_fk import MujocoFK


class LerobotFkSolverConfig:
    state_lejoint_mjcfjoints_dict: dict[str, str] | None = None
    left_arm_state_eefpos_list: list[str] | None = None
    right_arm_state_eefpos_list: list[str] | None = None
    left_arm_state_eefeuler_list: list[str] | None = None
    right_arm_state_eefeuler_list: list[str] | None = None

    action_lejoint_mjcfjoints_dict: dict[str, str] | None = None
    left_arm_action_eefpos_list: list[str] | None = None
    right_arm_action_eefpos_list: list[str] | None = None
    left_arm_action_eefeuler_list: list[str] | None = None
    right_arm_action_eefeuler_list: list[str] | None = None

    mjcf_path: str | Path | None = None

    left_eef_mjcf_site_name: str = "left_eef_site"
    right_eef_mjcf_site_name: str = "right_eef_site"

    view_frequency: int = 30


class LerobotFkSolver:
    def __init__(self, config: LerobotFkSolverConfig, repo_path: str | Path) -> None:
        self.mjcf_path = Path(config.mjcf_path).expanduser().resolve()
        self.repo_path = Path(repo_path).expanduser().resolve()

        self.state_lejoint_mjcfjoints_dict = config.state_lejoint_mjcfjoints_dict
        self.left_arm_state_eefpos_list = config.left_arm_state_eefpos_list
        self.right_arm_state_eefpos_list = config.right_arm_state_eefpos_list
        self.left_arm_state_eefeuler_list = config.left_arm_state_eefeuler_list
        self.right_arm_state_eefeuler_list = config.right_arm_state_eefeuler_list

        self.action_lejoint_mjcfjoints_dict = config.action_lejoint_mjcfjoints_dict
        self.left_arm_action_eefpos_list = config.left_arm_action_eefpos_list
        self.right_arm_action_eefpos_list = config.right_arm_action_eefpos_list
        self.left_arm_action_eefeuler_list = config.left_arm_action_eefeuler_list
        self.right_arm_action_eefeuler_list = config.right_arm_action_eefeuler_list

        self.left_eef_mjcf_site_name = config.left_eef_mjcf_site_name
        self.right_eef_mjcf_site_name = config.right_eef_mjcf_site_name

        self.view_frequency = config.view_frequency

        if not self.mjcf_path.exists():
            raise Exception(f"MJCF file {self.mjcf_path} does not exist.")

        try:
            self.mujoco_fk_solver = MujocoFK(
                mjcf_file_path=self.mjcf_path,
                site_names=[self.left_eef_mjcf_site_name, self.right_eef_mjcf_site_name],
            )
        except Exception as e:
            raise Exception("Error loading MJCF model") from e

        self._validate_config()

        self._preprocess_qpos_dict()

        self._collect_parquet_files()

    def _validate_config(self) -> None:
        if not self.repo_path.exists():
            raise Exception(f"Lerobot repo path {self.repo_path} does not exist.")

        if not self.mjcf_path.exists():
            raise Exception(f"MJCF file {self.mjcf_path} does not exist.")

        meta_info_path = self.repo_path / "meta/info.json"

        with open(meta_info_path) as f:
            json_data = json.load(f)
            features = json_data.get("features", None)
            if features is None:
                raise Exception("No features found in info.json")

            value = features.get("observation.state", None)
            if value is None:
                raise Exception("No states found in info.json")
            state_names = value.get("names", None)
            if state_names is None:
                raise Exception("No states found in info.json")

            value = features.get("action", None)
            if value is None:
                raise Exception("No actions found in info.json")

            action_names = value.get("names", None)
            if action_names is None:
                raise Exception("No actions found in info.json")

        mjcf_joints = self.mujoco_fk_solver.get_joint_names()

        for state_name, mjcf_joint_name in self.state_lejoint_mjcfjoints_dict.items():
            if mjcf_joint_name not in mjcf_joints:
                raise Exception(
                    f"State {state_name} has mjcf joint {mjcf_joint_name} which is not in the mjcf file."
                )

            if state_name not in state_names:
                raise Exception(f"State {state_name} not found in info.json")

        for action_name, mjcf_joint_name in self.action_lejoint_mjcfjoints_dict.items():
            if mjcf_joint_name not in mjcf_joints:
                raise Exception(
                    f"Action {action_name} has mjcf joint {mjcf_joint_name} which is not in the mjcf file."
                )

            if action_name not in action_names:
                raise Exception(f"Action {action_name} not found in info.json")

    def _preprocess_qpos_dict(self) -> None:
        meta_info_path = self.repo_path / "meta/info.json"

        with open(meta_info_path) as f:
            json_data = json.load(f)
            state_names: list[str] = json_data["features"]["observation.state"]["names"]
            action_names: list[str] = json_data["features"]["action"]["names"]

        self.state_lejointid_mjcfjointid_dict = {}
        for state_name, mjcf_joint_name in self.state_lejoint_mjcfjoints_dict.items():
            state_id = state_names.index(state_name)
            mjcf_joint_id = self.mujoco_fk_solver.get_joint_id(mjcf_joint_name)
            self.state_lejointid_mjcfjointid_dict[state_id] = mjcf_joint_id

        self.action_lejointid_mjcfjointid_dict = {}
        for action_name, mjcf_joint_name in self.action_lejoint_mjcfjoints_dict.items():
            action_id = action_names.index(action_name)
            mjcf_joint_id = self.mujoco_fk_solver.get_joint_id(mjcf_joint_name)
            self.action_lejointid_mjcfjointid_dict[action_id] = mjcf_joint_id

        self.left_arm_state_eefposid_list = [
            state_names.index(name) for name in self.left_arm_state_eefpos_list
        ]

        self.right_arm_state_eefposid_list = [
            state_names.index(name) for name in self.right_arm_state_eefpos_list
        ]

        self.left_arm_state_eefeulerid_list = [
            state_names.index(name) for name in self.left_arm_state_eefeuler_list
        ]

        self.right_arm_state_eefeulerid_list = [
            state_names.index(name) for name in self.right_arm_state_eefeuler_list
        ]

        self.left_arm_action_eefposid_list = [
            action_names.index(name) for name in self.left_arm_action_eefpos_list
        ]
        self.left_arm_action_eefeulerid_list = [
            action_names.index(name) for name in self.left_arm_action_eefeuler_list
        ]
        self.right_arm_action_eefposid_list = [
            action_names.index(name) for name in self.right_arm_action_eefpos_list
        ]

        self.right_arm_action_eefeulerid_list = [
            action_names.index(name) for name in self.right_arm_action_eefeuler_list
        ]

    def _collect_parquet_files(self) -> list[Path]:
        pattern = "episode_[0-9][0-9][0-9][0-9][0-9][0-9].parquet"
        parquet_files = list(self.repo_path.rglob(pattern))
        self.sorted_parquet_files = sorted(parquet_files, key=lambda x: int(x.stem.split("_")[-1]))

    def start_viewer(self) -> None:
        self.mujoco_fk_solver.start_viewer()

    def close_viewer(self) -> None:
        self.mujoco_fk_solver.close_viewer()

    def _sync_viewer(self) -> None:
        if self.mujoco_fk_solver.viewer is None:
            return
        self.mujoco_fk_solver.viewer.sync()
        time.sleep(1.0 / self.view_frequency)

    def get_episode_num(self) -> int:
        return len(self.sorted_parquet_files)

    def get_episode_eefpos_and_eefeuler(
        self, episode_idx: int, is_state: bool = True
    ) -> tuple[list[np.ndarray]]:
        if episode_idx >= len(self.sorted_parquet_files):
            raise Exception(f"Episode index {episode_idx} is out of range.")

        parquet_file_path = self.sorted_parquet_files[episode_idx]
        df = pd.read_parquet(parquet_file_path)

        if is_state:
            left_arm_eefposeid_list = self.left_arm_state_eefposid_list
            right_arm_eefposeid_list = self.right_arm_state_eefposid_list
            left_arm_eefeulerid_list = self.left_arm_state_eefeulerid_list
            right_arm_eefeulerid_list = self.right_arm_state_eefeulerid_list
            parquet_data = df["observation.state"]

        else:
            left_arm_eefposeid_list = self.left_arm_action_eefposid_list
            right_arm_eefposeid_list = self.right_arm_action_eefposid_list
            left_arm_eefeulerid_list = self.left_arm_action_eefeulerid_list
            right_arm_eefeulerid_list = self.right_arm_action_eefeulerid_list
            parquet_data = df["action"]

        eef_id_list = (
            left_arm_eefposeid_list
            + left_arm_eefeulerid_list
            + right_arm_eefposeid_list
            + right_arm_eefeulerid_list
        )

        eef_data_result = []
        for frame_data in parquet_data:
            eef_data = np.array([frame_data[eef_id] for eef_id in eef_id_list], dtype=np.float32)
            eef_data_result.append(eef_data)

        return eef_data_result

    def episode_fk(
        self,
        episode_idx: int,
        is_state: bool = True,
    ) -> tuple[list[np.ndarray]]:
        if episode_idx >= len(self.sorted_parquet_files):
            raise Exception(f"Episode index {episode_idx} is out of range.")

        parquet_file_path = self.sorted_parquet_files[episode_idx]
        df = pd.read_parquet(parquet_file_path)

        if is_state:
            lejointid_mjcfjointid_dict = self.state_lejointid_mjcfjointid_dict
            parquet_data = df["observation.state"]
        else:
            lejointid_mjcfjointid_dict = self.action_lejointid_mjcfjointid_dict
            parquet_data = df["action"]

        lejointid_mjcfjointid_dict

        fk_results = []
        for frame_data in parquet_data:
            joint_qpos: dict[int, float] = {}
            for lejoint_id, mjcfjoint_id in lejointid_mjcfjointid_dict.items():
                joint_qpos[mjcfjoint_id] = frame_data[lejoint_id]
            frame_result = self.mujoco_fk_solver.fk(joint_qpos)
            fk_results.append(frame_result)
            self._sync_viewer()
            # input("Press Enter to continue")

        return fk_results
