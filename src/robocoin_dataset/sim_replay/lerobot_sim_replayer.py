import json
import time
from collections.abc import Iterator
from pathlib import Path

import mujoco
import mujoco.viewer
import numpy as np
import pandas as pd
import torch
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from scipy.spatial.transform import Rotation as R

from robocoin_dataset.sim_replay.configs.lerobot_sim_replay_config import (
    LerobotSimReplayConfig,
)


class EpisodeSampler(torch.utils.data.Sampler):
    def __init__(self, dataset: LeRobotDataset, episode_index: int) -> None:
        from_idx = dataset.episode_data_index["from"][episode_index].item()
        to_idx = dataset.episode_data_index["to"][episode_index].item()
        self.frame_ids = range(from_idx, to_idx)

    def __iter__(self) -> Iterator:
        return iter(self.frame_ids)

    def __len__(self) -> int:
        return len(self.frame_ids)


class LerobotSimReplayer:
    def __init__(
        self,
        replay_config: LerobotSimReplayConfig,
        repo_path: str | Path,
    ) -> None:
        self.mjcf_file_path = Path(replay_config.mjcf_path).expanduser().resolve()
        self.repo_path = Path(repo_path).expanduser().absolute()
        self.get_mjcf_gripper_joint_data = replay_config.get_mjcf_gripper_joint_data
        self.mjcf_site_names = replay_config.mjcf_site_names

        if not self.mjcf_file_path.exists():
            raise FileNotFoundError(f"MJCF file not found: {self.mjcf_file_path}")
        if not self.repo_path.exists():
            raise ValueError(f"Lerobot Repo Path does not exist: {self.repo_path}")

        try:
            self.mjcf_model = mujoco.MjModel.from_xml_path(str(self.mjcf_file_path))
            self.mjcf_data = mujoco.MjData(self.mjcf_model)
            self.mjcf_site_ids = [self.mjcf_model.site(name).id for name in self.mjcf_site_names]
            self.mjcf_viewer = None
        except Exception as e:
            raise Exception(f"Error loading MJCF model: {e}")

        self.state_arm_joint_mjcf_names = replay_config.state_arm_joint_mjcf_names
        self.state_arm_joint_lerobot_names = replay_config.state_arm_joint_lerobot_names

        self.action_arm_joint_mjcf_names = replay_config.action_arm_joint_mjcf_names
        self.action_arm_joint_lerobot_names = replay_config.action_arm_joint_lerobot_names

        self.state_gripper_joint_mjcf_names = replay_config.state_gripper_joint_mjcf_names
        self.state_gripper_lerobot_names = replay_config.state_gripper_lerobot_names

        self.action_gripper_joint_mjcf_names = replay_config.action_gripper_joint_mjcf_names
        self.action_gripper_lerobot_names = replay_config.action_gripper_lerobot_names

        mjcf_joint_names = self._get_mjcf_joint_names()

        exist_flags = [
            mjcf_joint_name in mjcf_joint_names
            for mjcf_joint_name in self.state_arm_joint_mjcf_names
        ]
        non_exist_names = [
            self.state_arm_joint_mjcf_names[i] for i, flag in enumerate(exist_flags) if not flag
        ]
        if not all(exist_flags):
            raise Exception(
                f"Given State MJCF arm joint name: {non_exist_names} not found in MJCF file, MJCF joints: {mjcf_joint_names}"
            )

        exist_flags = [
            mjcf_joint_name in mjcf_joint_names
            for mjcf_joint_name in self.action_arm_joint_mjcf_names
        ]
        non_exist_names = [
            self.action_arm_joint_mjcf_names[i] for i, flag in enumerate(exist_flags) if not flag
        ]
        if not all(exist_flags):
            raise Exception(
                f"Given Action MJCF arm joint name: {non_exist_names} not found in MJCF file, MJCF joints: {mjcf_joint_names}"
            )

        exist_flags = [
            mjcf_joint_name in mjcf_joint_names
            for mjcf_joint_name in self.state_gripper_joint_mjcf_names
        ]
        non_exist_names = [
            self.state_gripper_joint_mjcf_names[i] for i, flag in enumerate(exist_flags) if not flag
        ]
        if not all(exist_flags):
            raise Exception(
                f"Given State MJCF gripper joint name: {non_exist_names} not found in MJCF file, MJCF joints: {mjcf_joint_names}"
            )

        exist_flags = [
            mjcf_joint_name in mjcf_joint_names
            for mjcf_joint_name in self.action_gripper_joint_mjcf_names
        ]
        non_exist_names = [
            self.action_gripper_joint_mjcf_names[i]
            for i, flag in enumerate(exist_flags)
            if not flag
        ]
        if not all(exist_flags):
            raise Exception(
                f"Given Action MJCF gripper joint name: {non_exist_names} not found in MJCF file, MJCF joints: {mjcf_joint_names}"
            )

        self.state_arm_joint_mjcf_addrs = [
            self._get_mjcf_joint_addr(mjcf_joint_name)
            for mjcf_joint_name in self.state_arm_joint_mjcf_names
        ]

        self.action_arm_joint_mjcf_addrs = [
            self._get_mjcf_joint_addr(mjcf_joint_name)
            for mjcf_joint_name in self.action_arm_joint_mjcf_names
        ]

        self.state_gripper_joint_mjcf_addrs = [
            self._get_mjcf_joint_addr(mjcf_joint_name)
            for mjcf_joint_name in self.state_gripper_joint_mjcf_names
        ]

        self.action_gripper_joint_mjcf_addrs = [
            self._get_mjcf_joint_addr(mjcf_joint_name)
            for mjcf_joint_name in self.action_gripper_joint_mjcf_names
        ]

        meta_file_path = self.repo_path / "meta/info.json"
        if not meta_file_path.exists():
            raise Exception(f"Meta file not found: {meta_file_path}")

        with open(meta_file_path) as f:
            json_data = json.load(f)
            features = json_data.get("features", None)
            if features is None:
                raise Exception("No features found in info.json")

            value = features.get("observation.state", None)
            if value is None:
                raise Exception("No states found in info.json")
            meta_state_names = value.get("names", None)
            if meta_state_names is None:
                raise Exception("No state names found in info.json")

            value = features.get("action", None)
            if value is None:
                raise Exception("No actions found in info.json")

            meta_action_names = value.get("names", None)
            if meta_action_names is None:
                raise Exception("No action names found in info.json")

        exist_flags = [
            state_name in meta_state_names for state_name in self.state_arm_joint_lerobot_names
        ]
        non_exist_names = [
            self.state_arm_joint_lerobot_names[i] for i, flag in enumerate(exist_flags) if not flag
        ]
        if not all(exist_flags):
            raise Exception(
                f"Given State Lerobot arm joint name: {non_exist_names} not found in info.json, State names: {meta_state_names}"
            )

        exist_flags = [
            action_name in meta_action_names for action_name in self.action_arm_joint_lerobot_names
        ]
        non_exist_names = [
            self.action_arm_joint_lerobot_names[i] for i, flag in enumerate(exist_flags) if not flag
        ]
        if not all(exist_flags):
            raise Exception(
                f"Given Action Lerobot arm joint name: {non_exist_names} not found in info.json, Action names: {meta_action_names}"
            )

        exist_flags = [
            state_name in meta_state_names for state_name in self.state_gripper_lerobot_names
        ]
        non_exist_names = [
            self.state_gripper_lerobot_names[i] for i, flag in enumerate(exist_flags) if not flag
        ]
        if not all(exist_flags):
            raise Exception(
                f"Given State Lerobot gripper joint name: {non_exist_names} not found in info.json, State names: {meta_state_names}"
            )

        exist_flags = [
            action_name in meta_action_names for action_name in self.action_gripper_lerobot_names
        ]
        non_exist_names = [
            self.action_gripper_lerobot_names[i] for i, flag in enumerate(exist_flags) if not flag
        ]
        if not all(exist_flags):
            raise Exception(
                f"Given Action Lerobot gripper joint name: {non_exist_names} not found in info.json, Action names: {meta_action_names}"
            )

        self.state_arm_joint_lerobot_ids = [
            meta_state_names.index(name) for name in self.state_arm_joint_lerobot_names
        ]

        self.action_arm_joint_lerobot_ids = [
            meta_action_names.index(name) for name in self.action_arm_joint_lerobot_names
        ]

        self.state_gripper_lerobot_ids = [
            meta_state_names.index(name) for name in self.state_gripper_lerobot_names
        ]

        self.action_gripper_lerobot_ids = [
            meta_action_names.index(name) for name in self.action_gripper_lerobot_names
        ]

    def _get_mjcf_joint_names(self) -> set[str]:
        return {self.mjcf_model.joint(i).name for i in range(self.mjcf_model.njnt)}

    def _get_mjcf_joint_addr(self, name: str) -> int:
        return self.mjcf_model.jnt_qposadr[self.mjcf_model.joint(name).id]

    # def load_dataset(self) -> LeRobotDataset:
    #     self.dataset = LeRobotDataset(repo_id="tmp/tmp", root=self.repo_path)

    def replay_episode(
        self, episode_index: int, is_state: bool = True, sleep_time_ms: int = 0
    ) -> None:
        if is_state:
            mjcf_arm_joint_addrs = self.state_arm_joint_mjcf_addrs
            mjcf_gripper_joint_addrs = self.state_gripper_joint_mjcf_addrs
            lerbot_arm_joint_ids = self.state_arm_joint_lerobot_ids
            leroot_gripper_ids = self.state_gripper_lerobot_ids
        else:
            mjcf_arm_joint_addrs = self.action_arm_joint_mjcf_addrs
            mjcf_gripper_joint_addrs = self.action_gripper_joint_mjcf_addrs
            lerbot_arm_joint_ids = self.action_arm_joint_lerobot_ids
            leroot_gripper_ids = self.action_gripper_lerobot_ids

        episode_eef_fk_results = []
        parquet_file_path = (
            self.repo_path / "ppp_data" / "chunk-000" / f"episode_{episode_index:06d}.parquet"
        )
        if not parquet_file_path.exists():
            raise Exception(f"Parquet file not found: {parquet_file_path}")

        df = pd.read_parquet(str(parquet_file_path))

        if is_state:
            data = df["observation.state"].to_list()
        else:
            data = df["action"].to_list()

        for i in range(len(data)):
            lerobot_arm_joint_values = data[i][lerbot_arm_joint_ids]
            lerobot_gripper_values = data[i][leroot_gripper_ids]
            for mjcf_addr, lerobot_value in zip(mjcf_arm_joint_addrs, lerobot_arm_joint_values):
                self.mjcf_data.qpos[mjcf_addr] = lerobot_value

            mjcf_gripper_joint_values = self.get_mjcf_gripper_joint_data(lerobot_gripper_values)
            for mjcf_addr, mjcf_data in zip(mjcf_gripper_joint_addrs, mjcf_gripper_joint_values):
                self.mjcf_data.qpos[mjcf_addr] = mjcf_data

            mujoco.mj_forward(self.mjcf_model, self.mjcf_data)
            for site_id in self.mjcf_site_ids:
                results = []
                site_pos = self.mjcf_data.site_xpos[site_id]
                site_rot = self.mjcf_data.site_xmat[site_id]
                site_rot_euler = R.from_matrix(site_rot.reshape(3, 3)).as_euler(
                    "xyz", degrees=False
                )
                results = np.concatenate([results, site_pos, site_rot_euler], axis=0)

            episode_eef_fk_results.append(results)
            self._sync_viewer()
            if sleep_time_ms > 0:
                time.sleep(sleep_time_ms / 1000)
        return episode_eef_fk_results

    def start_viewer(self) -> None:
        if self.mjcf_viewer is None:
            self.mjcf_viewer = mujoco.viewer.launch_passive(self.mjcf_model, self.mjcf_data)
            self.mjcf_viewer.sync()

    def _sync_viewer(self) -> None:
        if self.mjcf_viewer is not None:
            self.mjcf_viewer.sync()

    def close_viewer(self) -> None:
        if self.mjcf_viewer is not None:
            self.mjcf_viewer.close()
        self.mjcf_viewer = None
