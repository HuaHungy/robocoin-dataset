from pathlib import Path

import numpy as np

from .eef_sim_data_post_processor_base import EefSimDataPostProcessorBase
from robocoin_dataset.sim_replay.configs.lerobot_sim_replay_config import (
    LerobotSimReplayConfig,
)


class RealmanRmcAidalProcessor(EefSimDataPostProcessorBase):
    def __init__(
        self, 
        convert_path: str | Path,
        sim_replay_config: LerobotSimReplayConfig,
    ) -> None:
        super().__init__(
            convert_path=convert_path,
            sim_replay_config=sim_replay_config,
            has_gripper=True,
            gripper_value_max=1000.0,  # 设置夹爪最大值（根据实际情况调整）
            gripper_value_min=0.0,  # 设置夹爪最小值（根据实际情况调整）
        )

    def prepare_processing(self) -> None:
        pass
        
    def get_modified_state_feature_names(self) -> list[str]:
        return self.get_modified_state_or_action_feature_names()

    def get_modified_action_feature_names(self) -> list[str]:
        return self.get_modified_state_or_action_feature_names()


    # 该方法返回处理后的state数据名称
    def get_modified_feature_names(self):
        return super().get_modified_feature_names()

    def get_modified_info_state_names(self) -> dict[str, str]:
        return {}

    # 该方法返回处理后的action数据名称
    def get_modified_info_action_names(self) -> dict[str, str]:
        return {}

