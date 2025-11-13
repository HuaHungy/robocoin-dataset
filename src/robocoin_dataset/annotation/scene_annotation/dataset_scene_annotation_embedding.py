import json
from pathlib import Path

import numpy as np

from robocoin_dataset.data_post_process import DataPostProcessorBase
from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB


class SceneAnnotationDataPostProcessor(DataPostProcessorBase):
    def __init__(
        self,
        convert_path: str | Path,
        scene_annotations: list[str],
        episode_scene_indices: list[np.ndarray],
    ) -> None:
        self.feature_key = "scene_annotation"
        super().__init__(
            convert_path=convert_path,
            data_post_process_type=self.feature_key,
            data_feature_keys=[self.feature_key], # type: ignore
        )

        self.scene_annotations = scene_annotations
        self.episode_scene_indices = episode_scene_indices

    def prepare_processing(self) -> None:
        self.write_scene_jsonl_file()

    def process_episode_data(self, ori_data: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        ep_idx = self.episode_idx

        if ep_idx >= len(self.episode_scene_indices): # type: ignore
            raise ValueError(
                f"ep_idx: {ep_idx} >= len(self.episode_scene_indices): {len(self.episode_scene_indices)}"
            )

        return {self.feature_key: self.episode_scene_indices[ep_idx]} # type: ignore

    def get_modified_feature_names(self) -> dict[str, list[str]]:
        return {self.feature_key: None} # type: ignore

    def write_scene_jsonl_file(self) -> None:
        if  (self.convert_path / "annotations/scene_annotation.jsonl").exists():
            # delete old file
            (self.convert_path / "annotations/scene_annotation.jsonl").unlink()

        scene_jsonl_file_path = self.convert_path / "annotations/scene_annotations.jsonl"
        scene_jsonl_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(scene_jsonl_file_path, "w") as f:
            for i, annotation in enumerate(self.scene_annotations):
                annotation = (
                    annotation
                    .replace('\\', ' ')  # 处理反斜杠
                    .replace('\t', ' ')  # 制表符
                    .replace('\b', ' ')  # 退格符
                    .replace('\f', ' ')  # 换页符
                    .replace('\r', ' ')  # 回车符
                    .replace('\n', ' ')  # 换行符
                    .replace('"', ' ')   # 双引号
                    .replace("'", ' ')   # 单引号
                )
                f.write(f'{{"scene_index": {i}, "scene": "{annotation}"}}\n')


class SceneAnnotationEmbedding:
    def __init__(
        self,
        database_file: str | Path,
    ) -> None:
        self.database_file = database_file
        self.database = DatasetDatabase(database_file) # type: ignore

    def dataset_scene_embedding(self, dataset_uuid: str, scene_annotations: list[str]) -> None:
        with self.database.with_session() as session:
            dataset = (
                session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
            )
            if dataset is None:
                raise ValueError(f"dataset_uuid: {dataset_uuid} not found")
            # get dataset path
            dataset_path = dataset.convert_path
            dataset_path = Path(dataset_path) # type: ignore
            if dataset_path is None:
                raise ValueError(f"dataset_uuid: {dataset_uuid} dataset_path is None")
            # 找到meta文件夹下的episodes.jsonl，annotation[episode_index]值为length行episode_index
            annotation = []
            meta_path = dataset_path / "meta"
            if not meta_path.exists():
                raise ValueError(f"dataset_uuid: {dataset_uuid} meta_path: {meta_path} not exists")
            episodes_jsonl_path = meta_path / "episodes.jsonl"
            if not episodes_jsonl_path.exists():
                raise ValueError(
                    f"dataset_uuid: {dataset_uuid} episodes_jsonl_path: {episodes_jsonl_path} not exists"
                )
            with open(episodes_jsonl_path) as f:
                for line in f:
                    line = line.strip()
                    if line == "":
                        continue
                    episode = json.loads(line)
                    episode_index = episode["episode_index"]
                    length = episode["length"]
                    # 确保annotation列表足够长
                    while len(annotation) <= episode_index:
                        annotation.append(None)
                    # annotation[episode_index]包含length行的episode_index，转换为NumPy数组
                    annotation[episode_index] = np.full((length, 1), episode_index, dtype=np.int32)
            processor = SceneAnnotationDataPostProcessor(
                convert_path=dataset_path,
                scene_annotations=scene_annotations,
                episode_scene_indices=annotation,
            )
            processor.process()
            session.commit()
