import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm

from robocoin_dataset.utils.parquet_paths import get_parquet_paths


class DataPostProcessorBase:
    def __init__(
        self,
        convert_path: str | Path,
        data_post_process_type: str,
        data_feature_keys: set[str],
    ) -> None:
        self.convert_path: Path = Path(convert_path)
        if not self.convert_path.exists():
            raise FileNotFoundError(f"{self.convert_path} does not exist")

        if not (self.convert_path / "meta/info.json").exists():
            raise FileNotFoundError(f"{convert_path}/meta/info.json does not exist")

        with open(self.convert_path / "meta/info.json") as f:
            info_json: dict = json.load(f)
            features = info_json.get("features", None)
            if not features:
                raise ValueError(f"{convert_path}/meta/info.json does not contain features")
            for feature in data_feature_keys:
                if feature not in features:
                    raise ValueError(f"{feature} not found in features")

        self.parquet_files, self.new_parquet_files = get_parquet_paths(
            root_dir=self.convert_path, new_parquet_type=data_post_process_type
        )
        self.data_features = data_feature_keys
        self.new_info_file_path = self.convert_path / "meta" / f"{data_post_process_type}_info.json"
        self.info_file_path = self.convert_path / "meta/info.json"

    # 将处理episode数据的准备工作放在这里
    def prepare_processing(self) -> None:
        pass

    # 该方法将ori_data进行后处理，返回结果为后处理后的数据
    def process_episode_data(self, ori_data: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        return ori_data.copy()

    # 该方法返回处理后的state数据名称
    def get_modified_feature_names(self) -> dict[str, dict[str, str]]:
        return {}

    def get_ori_episode_data(self, episode_idx: int) -> dict[str, np.ndarray | None]:
        if episode_idx >= len(self.parquet_files):
            raise ValueError(f"episode_idx {episode_idx} out of range")

        results = {}

        df = pd.read_parquet(self.parquet_files[episode_idx])

        for feature in self.data_features:
            if feature not in df:
                results[feature] = None
            else:
                results[feature] = np.array(df[feature].tolist())

        return results

    def write_new_episode_file(self, new_data: dict[str, np.ndarray], episode_idx: int) -> None:
        if episode_idx >= len(self.new_parquet_files):
            raise ValueError(f"episode_idx {episode_idx} out of range")

        data = {key: value.tolist() for key, value in new_data.items()}
        df = pd.DataFrame(data)
        table = pa.Table.from_pandas(df)
        self.new_parquet_files[episode_idx].parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, self.new_parquet_files[episode_idx])

    def write_new_info_file(self) -> None:
        json_dict = {}
        json_dict["features"] = {}
        for feature_key, names in self.get_modified_feature_names().items():
            if len(names) != len(set(names)):
                raise ValueError(f"given feature names contain duplicated names: {names}")
            json_dict["features"][feature_key] = {}
            json_dict["features"][feature_key]["names"] = names

        with open(self.new_info_file_path, "w") as f:
            json.dump(json_dict, f)

    def process(self) -> None:
        self.write_new_info_file()
        for episode_idx in tqdm(
            range(len(self.parquet_files)), desc="Processing episodes", unit="episode"
        ):
            self.prepare_processing()
            ori_data = self.get_ori_episode_data(episode_idx)
            new_datas: dict[str, np.ndarray] = self.process_episode_data(ori_data)

            for key, arr in new_datas.items():
                if isinstance(arr, np.ndarray) and np.issubdtype(arr.dtype, np.floating):
                    new_datas[key] = arr.astype(np.float32)  # 就地转为 float32
            if new_datas.keys() != self.data_features:
                raise ValueError(
                    f"new_datas keys {new_datas.keys()} != self.data_features {self.data_features}"
                )

            for feature_key, data in ori_data.items():
                if data.shape[0] != new_datas[feature_key].shape[0]:
                    raise ValueError(
                        f"ori_data shape {data.shape}[0] != new_datas shape {new_datas[feature_key].shape}[0]"
                    )

            self.write_new_episode_file(new_datas, episode_idx)