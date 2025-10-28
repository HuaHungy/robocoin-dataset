import json
from pathlib import Path

import numpy as np

from robocoin_dataset.data_post_process import DataPostProcessorBase


class StateActionDataPostProcessorBase(DataPostProcessorBase):
    def __init__(self, convert_path: str | Path) -> None:
        super().__init__(
            convert_path=convert_path,
            data_post_process_type="state_action",
            data_feature_keys={
                "observation.state",
                "action",
            },
        )
        self.convert_path = Path(convert_path)
        if not self.convert_path.exists():
            raise ValueError(f"{self.convert_path} does not exist")

    # def get_modified_feature_names(self) -> dict[str, list[str]]:
    #     return self.get_ori_state_action_feature_names()

    def get_ori_state_action_feature_names(self) -> dict[str, list[str]]:
        if not self.info_file_path.exists():
            raise ValueError(f"{self.info_file_path} does not exist")
        with open(self.info_file_path) as f:
            json_dict = json.load(f)

        if "features" not in json_dict:
            raise ValueError(f"{self.info_file_path} does not contain features")

        if "observation.state" not in json_dict["features"]:
            raise ValueError(f"{self.info_file_path} does not contain observation.state")

        if "action" not in json_dict["features"]:
            raise ValueError(f"{self.info_file_path} does not contain action")

        if not isinstance(json_dict["features"]["observation.state"]["names"], list):
            raise ValueError("value of observation.state.names is not list[str]")

        if not isinstance(json_dict["features"]["action"]["names"], list):
            raise ValueError("value of action.names is not list[str]")

        return {
            "observation.state": json_dict["features"]["observation.state"]["names"],
            "action": json_dict["features"]["action"]["names"],
        }

    def process_episode_data(self, ori_data: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        return {
            "observation.state": self.process_episode_state_data(ori_data["observation.state"]),
            "action": self.process_episode_action_data(ori_data["action"]),
        }

    def get_modified_feature_names(self) -> dict[str, list[str]]:
        state_names = self.get_modified_state_feature_names()
        action_names = self.get_modified_action_feature_names()

        return {
            "observation.state": state_names,
            "action": action_names,
        }

    # 在这里填入修改后的state特征名称列表，如果没有修改，则不需要重写函数
    def get_modified_state_feature_names(self) -> list[str]:
        return self.get_ori_state_action_feature_names()["observation.state"]

    # 在这里填入修改后的action特征名称列表，如果没有修改，则不需要重写函数
    def get_modified_action_feature_names(self) -> list[str]:
        return self.get_ori_state_action_feature_names()["action"]

    # 将处理episode数据的准备工作放在这里
    def prepare_processing(self) -> None:
        pass

    # 该方法将ori_state_data进行后处理，返回结果为后处理后的数据
    def process_episode_state_data(self, ori_state_data: np.ndarray) -> np.ndarray:
        return ori_state_data.copy()

    # 该方法将ori_action_data进行后处理，返回结果为后处理后的数据
    def process_episode_action_data(self, ori_action_data: np.ndarray) -> np.ndarray:
        return ori_action_data.copy()
