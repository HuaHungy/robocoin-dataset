import json
import logging
from pathlib import Path

from robocoin_dataset.annotation.subtask_annotion.constant import (
    DS_API_KEY,
    SUBTASK_ANNOTATION_SOURCE_FILE_PATH,
    SUBTASK_ANNOTATION_TARGET_FILE_NAME,
    SUBTASK_ANNOTATION_TARGET_FILE_PATH,
)
from robocoin_dataset.distribution_computation.task_client import TaskClient

from .subtask_annotation import (
    build_mapping,
    extract_labels,
    get_video_labels_dict,
    modify_frame_idx,
    process_batch_labels,
    transform_labels,
)


class SubtaskAnnotationTaskClient(TaskClient):
    def __init__(
        self,
        server_uri: str,
        heartbeat_interval: float = 10.0,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(
            server_uri=server_uri,
            heartbeat_interval=heartbeat_interval,
            logger=logger,
        )

    def get_task_category(self) -> str:
        return "subtask_annotation"

    def generate_task_request_desc(self) -> dict:
        """客户端可自定义任务请求参数"""
        return {}

    def _sync_process_task(self, task_content: dict) -> dict:
        try:
            subtask_annotation_source_file_path = task_content.get(
                SUBTASK_ANNOTATION_SOURCE_FILE_PATH
            )
            ds_api_key = task_content.get(DS_API_KEY)
            if not Path(subtask_annotation_source_file_path).exists():
                raise FileNotFoundError(f"{subtask_annotation_source_file_path} does not exists")
            with open(subtask_annotation_source_file_path) as f:
                data = json.load(f)
                video_labels_dict = get_video_labels_dict(data)
                labels = extract_labels(video_labels_dict)

                en_labels = process_batch_labels(labels, ds_api_key=ds_api_key)

                mapping = build_mapping(labels, en_labels)

                transformed_labels = transform_labels(video_labels_dict, mapping)
                frame_modifed_labels = modify_frame_idx(transformed_labels)

                subtask_annotation_target_file_path = (
                    Path(subtask_annotation_source_file_path).parent
                    / SUBTASK_ANNOTATION_TARGET_FILE_NAME
                )
                subtask_annotation_target_file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(subtask_annotation_target_file_path, "w") as anno_file:
                    json.dump(frame_modifed_labels, anno_file)
                return {
                    SUBTASK_ANNOTATION_TARGET_FILE_PATH: str(subtask_annotation_target_file_path),
                }

        except Exception as e:
            raise RuntimeError(
                f"convert subtask annotation file {subtask_annotation_source_file_path} failed"
            ) from e
