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

    def get_modified_feature_names(self) -> dict[str, list[str]]:
        return self.get_ori_state_action_feature_names()

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

    # 将处理episode数据的准备工作放在这里
    def prepare_processing(self) -> None:
        pass

    # 该方法将ori_state_data进行后处理，返回结果为后处理后的数据
    def process_episode_state_data(self, ori_state_data: np.ndarray) -> np.ndarray:
        return ori_state_data.copy()

    # 该方法将ori_action_data进行后处理，返回结果为后处理后的数据
    def process_episode_action_data(self, ori_action_data: np.ndarray) -> np.ndarray:
        return ori_action_data.copy()

    # # 该方法返回处理后的state数据名称
    # def get_modified_info_state_names(self) -> dict[str, str]:
    #     return {}

    # # 该方法返回处理后的action数据名称
    # def get_modified_info_action_names(self) -> dict[str, str]:
    #     return {}

    # def get_ori_episode_data(self, episode_idx: int) -> tuple[np.ndarray, np.ndarray]:
    #     if episode_idx >= len(self.parquet_files):
    #         raise ValueError(f"episode_idx {episode_idx} out of range")

    #     df = pd.read_parquet(self.parquet_files[episode_idx])

    #     try:
    #         state_data = np.array(df["observation.state"].tolist())
    #         action_data = np.array(df["action"].tolist())
    #     except Exception as e:
    #         raise ValueError(f"Error when processing episode {episode_idx}, {e}")

    #     return state_data, action_data

    # def write_new_episode_file(self, df: pd.DataFrame, episode_idx: int) -> None:
    #     if episode_idx >= len(self.new_parquet_files):
    #         raise ValueError(f"episode_idx {episode_idx} out of range")

    #     df.to_parquet(self.new_parquet_files[episode_idx])

    # def modify_info_file(self) -> None:
    #     ori_info_file_path = self.convert_path / "meta/ori_info.json"
    #     new_info_file_path = self.convert_path / "meta/info.json"
    #     if not ori_info_file_path.exists():
    #         raise ValueError(f"{new_info_file_path} does not exist")

    #     if not new_info_file_path.exists():
    #         raise ValueError(f"{new_info_file_path} does not exist")

    #     with open(new_info_file_path) as f:
    #         info_json: dict = json.load(f)

    #     ori_state_names: list[str] = info_json["features"]["observation.state"]["names"]
    #     new_state_names: list[str] = ori_state_names

    #     ori_action_names: list[str] = info_json["features"]["action"]["names"]
    #     new_action_names: list[str] = ori_action_names

    #     for ori_name, new_name in self.get_modified_info_state_names().items():
    #         if ori_name in ori_state_names:
    #             idx = ori_state_names.index(ori_name)
    #             new_state_names[idx] = new_name
    #         else:
    #             raise ValueError(
    #                 f"{ori_name} not found in ori_state_names, available state names: {ori_state_names}"
    #             )
    #     if len(set(new_state_names)) != len(new_state_names):
    #         raise ValueError(
    #             f"Found duplicate state names in new_state_names, new_state_names: {new_state_names}"
    #         )

    #     for ori_name, new_name in self.get_modified_info_action_names().items():
    #         if ori_name in ori_action_names:
    #             idx = ori_action_names.index(ori_name)
    #             new_action_names[idx] = new_name
    #         else:
    #             raise ValueError(
    #                 f"{ori_name} not found in ori_action_names, available action names: {ori_action_names}"
    #             )

    #     if len(set(new_action_names)) != len(new_action_names):
    #         raise ValueError(
    #             f"Found duplicate action names in new_action_names, new_action_names: {new_action_names}"
    #         )

    #     with open(new_info_file_path, "w") as f:
    #         json.dump(info_json, f, indent=4)

    # def process(self) -> None:
    #     self.modify_info_file()
    #     for episode_idx in tqdm(
    #         range(len(self.parquet_files)), desc="Processing episodes", unit="episode"
    #     ):
    #         self.prepare_processing()
    #         ori_state_data, ori_action_data = self.get_ori_episode_data(episode_idx)
    #         state_data: np.ndarray = self.process_episode_state_data(ori_state_data)
    #         action_data: np.ndarray = self.process_episode_action_data(ori_action_data)

    #         if state_data.shape != ori_state_data.shape:
    #             raise ValueError(
    #                 f"observation_state_list shape {state_data.shape} != ori_state_data shape {ori_state_data.shape}"
    #             )

    #         if action_data.shape != ori_action_data.shape:
    #             raise ValueError(
    #                 f"action_list shape {action_data.shape} != ori_action_data shape {ori_action_data.shape}"
    #             )

    #         df_new: pd.DataFrame = pd.DataFrame()

    #         df_new["observation.state"] = state_data.tolist()
    #         df_new["action"] = action_data.tolist()
    #         self.write_new_episode_file(df_new, episode_idx)
