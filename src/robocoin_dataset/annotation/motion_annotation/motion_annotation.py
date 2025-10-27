from pathlib import Path

from robocoin_dataset.sim_replay.configs.lerobot_sim_replay_config import (
    LerobotSimReplayConfig,
)
from robocoin_dataset.sim_replay.lerobot_sim_replayer import LerobotSimReplayer
from robocoin_dataset.utils.parquet_paths import get_parquet_paths


class MotionAnnotationConfig:
    left_gripper_open_state_name: str = "left_gripper_open"
    right_gripper_open_state_name: str = "right_gripper_open"

    left_gripper_open_max_value = 1000
    left_gripper_open_min_value = 0
    right_gripper_open_max_value = 1000
    right_gripper_open_min_value = 0

    sim_replay_config_class: type[LerobotSimReplayConfig]


class MotionAnnotation:
    def __init__(
        self,
        repo_path: str | Path,
        annotation_config_class: type[MotionAnnotationConfig],
        slice_window_size: int = 3,
    ) -> None:
        self.repo_path = Path(repo_path).expanduser().absolute()
        self.annotation_config_class = annotation_config_class
        self.annotation_config = annotation_config_class()
        self.simmulator = LerobotSimReplayer(
            replay_config=self.annotation_config.sim_replay_config_class,
            repo_path=self.repo_path,
        )

    def _annotation_eef(self) -> None:
        self.simmulator.replay_episode(episode_index=0)
        parquet_paths, _ = get_parquet_paths(self.repo_path, "state_action")
        ep_num = len(parquet_paths)
        for ep_idx in range(ep_num):
            self.simmulator.replay_episode(episode_index=ep_idx)
