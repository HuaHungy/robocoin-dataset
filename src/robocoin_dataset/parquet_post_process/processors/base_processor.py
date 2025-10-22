import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from natsort import natsorted
from tqdm import tqdm


class ParquetPostProcessor:
    def __init__(self, convert_path: str | Path) -> None:
        self.convert_path = Path(convert_path)
        if not self.convert_path.exists():
            raise ValueError(f"{self.convert_path} does not exist")

        self.ori_data_dir = self.convert_path / "ori_data"
        self.new_data_dir = self.convert_path / "data"
        if not self.ori_data_dir.exists():
            raise ValueError(f"{self.convert_path}/data_convert dir not exist")

        regex = re.compile(r"episode_(?P<idx>\d{6})\.parquet$")
        self.ori_parquet_files = []
        for file_path in self.ori_data_dir.rglob("episode_*.parquet"):
            match = regex.match(file_path.name)
            if match:
                self.ori_parquet_files.append(file_path)

        self.ori_parquet_files = natsorted(self.ori_parquet_files, key=lambda x: x.name)

        self.new_parquet_files = []
        for file_path in self.new_data_dir.rglob("episode_*.parquet"):
            match = regex.match(file_path.name)
            if match:
                self.new_parquet_files.append(file_path)
        self.new_parquet_files = natsorted(self.new_parquet_files, key=lambda x: x.name)

    # 将处理episode数据的准备工作放在这里
    def prepare_processing(self) -> None:
        pass

    # 该方法将ori_state_data进行后处理，返回结果为后处理后的数据
    def process_episode_state_data(self, ori_state_data: np.ndarray) -> np.ndarray:
        return ori_state_data.copy()

    # 该方法将ori_action_data进行后处理，返回结果为后处理后的数据
    def process_episode_action_data(self, ori_action_data: np.ndarray) -> np.ndarray:
        return ori_action_data.copy()

    # 该方法返回处理后的state数据名称
    def get_modified_info_state_names(self) -> dict[str, str]:
        return {}

    # 该方法返回处理后的action数据名称
    def get_modified_info_action_names(self) -> dict[str, str]:
        return {}

    def get_ori_episode_data(self, episode_idx: int) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
        if episode_idx >= len(self.ori_parquet_files):
            raise ValueError(f"episode_idx {episode_idx} out of range")

        df = pd.read_parquet(self.ori_parquet_files[episode_idx])

        try:
            state_data = np.array(df["observation.state"].tolist())
            action_data = np.array(df["action"].tolist())
        except Exception as e:
            raise ValueError(f"Error when processing episode {episode_idx}, {e}")

        return df, state_data, action_data

    def write_new_episode_file(self, df: pd.DataFrame, episode_idx: int) -> None:
        if episode_idx >= len(self.new_parquet_files):
            raise ValueError(f"episode_idx {episode_idx} out of range")

        df.to_parquet(self.new_parquet_files[episode_idx])

    def modify_info_file(self) -> None:
        ori_info_file_path = self.convert_path / "meta/ori_info.json"
        new_info_file_path = self.convert_path / "meta/info.json"
        if not ori_info_file_path.exists():
            raise ValueError(f"{new_info_file_path} does not exist")

        if not new_info_file_path.exists():
            raise ValueError(f"{new_info_file_path} does not exist")

        with open(new_info_file_path) as f:
            info_json: dict = json.load(f)

        ori_state_names: list[str] = info_json["features"]["observation.state"]["names"]
        new_state_names: list[str] = ori_state_names

        ori_action_names: list[str] = info_json["features"]["action"]["names"]
        new_action_names: list[str] = ori_action_names

        for ori_name, new_name in self.get_modified_info_state_names().items():
            if ori_name in ori_state_names:
                idx = ori_state_names.index(ori_name)
                new_state_names[idx] = new_name
            else:
                raise ValueError(
                    f"{ori_name} not found in ori_state_names, available state names: {ori_state_names}"
                )
        if len(set(new_state_names)) != len(new_state_names):
            raise ValueError(
                f"Found duplicate state names in new_state_names, new_state_names: {new_state_names}"
            )

        for ori_name, new_name in self.get_modified_info_action_names().items():
            if ori_name in ori_action_names:
                idx = ori_action_names.index(ori_name)
                new_action_names[idx] = new_name
            else:
                raise ValueError(
                    f"{ori_name} not found in ori_action_names, available action names: {ori_action_names}"
                )

        if len(set(new_action_names)) != len(new_action_names):
            raise ValueError(
                f"Found duplicate action names in new_action_names, new_action_names: {new_action_names}"
            )

        with open(new_info_file_path, "w") as f:
            json.dump(info_json, f, indent=4)

    def process(self) -> None:
        self.modify_info_file()
        for episode_idx in tqdm(
            range(len(self.ori_parquet_files)), desc="Processing episodes", unit="episode"
        ):
            self.prepare_processing()
            df, ori_state_data, ori_action_data = self.get_ori_episode_data(episode_idx)
            state_data: np.ndarray = self.process_episode_state_data(ori_state_data)
            action_data: np.ndarray = self.process_episode_action_data(ori_action_data)

            if state_data.shape != ori_state_data.shape:
                raise ValueError(
                    f"observation_state_list shape {state_data.shape} != ori_state_data shape {ori_state_data.shape}"
                )

            if action_data.shape != ori_action_data.shape:
                raise ValueError(
                    f"action_list shape {action_data.shape} != ori_action_data shape {ori_action_data.shape}"
                )

            df["observation.state"] = state_data.tolist()
            df["action"] = action_data.tolist()
            self.write_new_episode_file(df, episode_idx)
