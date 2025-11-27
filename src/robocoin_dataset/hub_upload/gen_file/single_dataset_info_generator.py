"""
Single Dataset Info Generator - For On-Demand Generation During Upload

This module provides a class for generating dataset info YAML files for individual datasets
without requiring root_path manipulation. Designed for single-file generation during upload.

现在这个脚本已经不再使用，请使用metadata_collect.py脚本代替，这个脚本将会在未来的某个版本被删除。
"""

import json
import logging
from functools import cached_property
from pathlib import Path

import yaml

from robocoin_dataset.hub_upload.lerobot.constant import (
    ANNOTATIONS_DIR,
    DATASET_INFO_FILE,
    LEROBOT_META_INFO_FILE,
    LEROBOT_META_TASKS_FILE,
)


class SingleDatasetInfoGenerator:
    """
    Generator for creating dataset info YAML files for individual datasets.

    This class works directly with hardlink paths without requiring root_path setup,
    making it ideal for on-demand generation during upload operations.

    Attributes:
        dataset_path (Path): Direct path to the dataset directory (hardlink)
        output_path (Path): Directory where the YAML file will be saved
        task_tags_yamls_dir (Path | None): Optional directory containing task tag YAML files
        logger (logging.Logger | None): Optional logger instance
    """

    def __init__(
        self,
        dataset_path: Path,
        output_path: Path,
        task_tags_yamls_dir: Path | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """
        Initialize the single dataset info generator.

        Args:
            dataset_path: Direct path to the dataset directory (hardlink path)
            output_path: Directory where the YAML file will be saved
            task_tags_yamls_dir: Optional directory containing task tag YAML files
            logger: Optional logger instance
        """
        self.dataset_path = Path(dataset_path)
        self.output_path = Path(output_path)
        self.task_tags_yamls_dir = Path(task_tags_yamls_dir) if task_tags_yamls_dir else None
        self.logger = logger

        if not self.dataset_path.exists():
            raise FileNotFoundError(f"Dataset path does not exist: {self.dataset_path}")
        if not self.dataset_path.is_dir():
            raise NotADirectoryError(f"Dataset path is not a directory: {self.dataset_path}")

    @cached_property
    def info_template_file(self) -> Path:
        """
        Get the path to the dataset info template file with validation.

        Returns:
            Path: Absolute path to the info template file.

        Raises:
            FileNotFoundError: If the info template file does not exist.
        """
        # Template is in the prepare_metadata/readmes module
        path = Path(__file__).parent.parent.parent.joinpath(
            "prepare_metadata",
            "readmes",
            "templates",
            "dataset_info.yml",
        )
        if not path.exists():
            raise FileNotFoundError(f"Info template file {path} does not exist")
        return path

    @property
    def dataset_name(self) -> str:
        """Get the dataset name from the path."""
        return self.dataset_path.name

    def _get_info_from_lerobot_meta(self) -> tuple[int, int, str]:
        """
        Extract information from LeRobot metadata files.

        Reads from:
        - meta/info.json: for total_episodes, total_frames
        - meta/tasks.jsonl: for task descriptions

        Returns:
            tuple[int, int, str]: Episodes count, frames count, and tasks list as string.

        Raises:
            FileNotFoundError: If metadata files do not exist.
        """
        info_file = self.dataset_path / LEROBOT_META_INFO_FILE
        tasks_file = self.dataset_path / LEROBOT_META_TASKS_FILE

        if not info_file.exists():
            raise FileNotFoundError(f"Dataset meta info file {info_file} does not exist")
        if not tasks_file.exists():
            raise FileNotFoundError(f"Dataset meta tasks file {tasks_file} does not exist")

        episodes_num = 0
        frames_num = 0
        tasks_list: list[str] = []

        # Read episode and frame counts from meta/info.json
        try:
            with open(info_file, encoding="utf-8") as f:
                data = json.load(f)
                episodes_num = data.get("total_episodes", 0)
                frames_num = data.get("total_frames", 0)
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to read meta info file {info_file}: {e}")
            raise

        # Read tasks from meta/tasks.jsonl
        try:
            with open(tasks_file, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        task_data = json.loads(line)
                        tasks_list.append(task_data.get("task", ""))
                    except json.JSONDecodeError:
                        if self.logger:
                            self.logger.error(f"Failed to decode JSON from line: {line.strip()}")
                        raise
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to read tasks file {tasks_file}: {e}")
            raise

        tasks = "\n".join(tasks_list)
        return episodes_num, frames_num, tasks

    def _get_subtasks_from_annotation(self) -> list[str]:
        """
        Extract subtasks from dataset annotation files.

        Reads from: annotations/subtask_annotations.jsonl

        Returns:
            list[str]: List of unique subtasks.
        """
        annotations_dir = self.dataset_path / ANNOTATIONS_DIR

        if not annotations_dir.exists():
            if self.logger:
                self.logger.warning(
                    f"{self.dataset_name}: annotations directory '{ANNOTATIONS_DIR}' not found. "
                    "Subtasks will be empty."
                )
            return ""

        subtask_file = annotations_dir / "subtask_annotations.jsonl"

        if not subtask_file.exists():
            if self.logger:
                self.logger.warning(
                    f"{self.dataset_name}: subtask_annotations.jsonl not found. Subtasks will be empty."
                )
            return ""

        # Extract unique subtasks (case-insensitive)
        # Filter out invalid/placeholder subtasks
        invalid_subtasks = {}

        subtasks_dict = {}
        try:
            with open(subtask_file, encoding='utf-8') as f:
                for line in f:
                    if line := line.strip():
                        data = json.loads(line)
                        if "subtask" in data:
                            subtask = data["subtask"]
                            subtask_lower = subtask.lower()
                            # Skip invalid/placeholder subtasks
                            if subtask_lower not in invalid_subtasks and subtask_lower not in subtasks_dict:
                                subtasks_dict[subtask_lower] = subtask

            # Sort and return as list
            sorted_subtasks = [subtasks_dict[key] for key in sorted(subtasks_dict.keys())]

            if self.logger:
                self.logger.info(f"{self.dataset_name}: extracted {len(sorted_subtasks)} unique subtasks")
            return sorted_subtasks

        except Exception as e:
            if self.logger:
                self.logger.error(f"{self.dataset_name}: error reading subtask_annotations.jsonl: {e}")
            return []

    def _generate_size_label(self, size: int) -> str:
        """
        Generate size category label based on frame count.

        Args:
            size: Number of frames.

        Returns:
            str: Size category label (e.g., "<1K", "1K-10K", etc.).
        """
        if size < 1000:
            return "<1K"
        if size < 10000:
            return "1K-10K"
        if size < 100000:
            return "10K-100K"
        if size < 1000000:
            return "100K-1M"
        if size < 10000000:
            return "1M-10M"
        if size < 100000000:
            return "10M-100M"
        if size < 1000000000:
            return "100M-1B"
        if size < 10000000000:
            return "1B-10B"
        if size < 100000000000:
            return "10B-100B"
        if size < 1000000000000:
            return "100B-1T"
        return ">1T"

    def _generate_tags(self) -> list[str]:
        """
        Generate tags for the dataset from YAML tag files (optional).

        Returns:
            list[str]: List of tags for the dataset. Empty list if no tags directory configured.
        """
        if not self.task_tags_yamls_dir:
            return []

        tags_file_path = self.task_tags_yamls_dir / f"{self.dataset_name}.yml"
        if not tags_file_path.exists():
            return []

        with open(tags_file_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _extract_info_from_meta_json(self) -> dict:
        """
        Extract comprehensive information from meta/info.json file.

        Reads only from: meta/info.json

        Returns:
            dict: Dictionary containing extracted information from info.json.
        """
        info_file = self.dataset_path / LEROBOT_META_INFO_FILE
        if not info_file.exists():
            if self.logger:
                self.logger.warning(f"{self.dataset_name}: info.json not found")
            return {}

        try:
            with open(info_file, encoding="utf-8") as f:
                meta_info = json.load(f)
        except Exception as e:
            if self.logger:
                self.logger.error(f"{self.dataset_name}: failed to read info.json: {e}")
            return {}

        # Extract all relevant fields
        extracted = {}

        # Robot information
        if "robot_type" in meta_info:
            extracted["robot_type"] = meta_info["robot_type"]
        if "codebase_version" in meta_info:
            extracted["codebase_version"] = meta_info["codebase_version"]

        # Statistics
        statistics = {}
        if "total_episodes" in meta_info:
            statistics["total_episodes"] = meta_info["total_episodes"]
        if "total_frames" in meta_info:
            statistics["total_frames"] = meta_info["total_frames"]
        if "total_tasks" in meta_info:
            statistics["total_tasks"] = meta_info["total_tasks"]
        if "total_videos" in meta_info:
            statistics["total_videos"] = meta_info["total_videos"]
        if "total_chunks" in meta_info:
            statistics["total_chunks"] = meta_info["total_chunks"]
        if "chunks_size" in meta_info:
            statistics["chunks_size"] = meta_info["chunks_size"]
        if "fps" in meta_info:
            statistics["fps"] = meta_info["fps"]

        if statistics:
            extracted["statistics"] = statistics

        # Data organization
        if "splits" in meta_info:
            extracted["splits"] = meta_info["splits"]
        if "data_path" in meta_info:
            extracted["data_path"] = meta_info["data_path"]
        if "video_path" in meta_info:
            extracted["video_path"] = meta_info["video_path"]

        # Features
        if "features" in meta_info:
            extracted["features"] = meta_info["features"]

            # Check for depth cameras
            features = meta_info["features"]
            depth_enabled = False
            for key, value in features.items():
                if key.startswith("observation.images.") and isinstance(value, dict):
                    info = value.get("info", {})
                    if info.get("video.is_depth_map", False):
                        depth_enabled = True
                        break
            extracted["depth_enabled"] = depth_enabled

        return extracted

    def _get_auto_generate_info(self) -> dict:
        """
        Automatically generate dataset information from dataset files.

        Returns:
            dict: Dictionary containing auto-generated dataset information.
        """
        # Extract comprehensive information from info.json
        extracted_info = self._extract_info_from_meta_json()

        # Get legacy fields for backward compatibility
        episodes_num, frames_num, tasks = self._get_info_from_lerobot_meta()
        sub_tasks = self._get_subtasks_from_annotation()
        size_category = self._generate_size_label(frames_num)
        tags = self._generate_tags()

        # Merge all information
        auto_info = {
            "size_categories": size_category,
            "tasks": tasks,
            "sub_tasks": sub_tasks,
        }

        # Add custom tags if provided
        if tags:
            auto_info["dataset_tags"] = tags

        # Merge extracted info (this will override any conflicts)
        auto_info.update(extracted_info)

        return auto_info

    def generate_info(self) -> dict:
        """
        Generate complete dataset information by combining template and auto-generated data.

        Returns:
            dict: Complete dataset information dictionary.
        """
        if not self.info_template_file.exists():
            if self.logger:
                self.logger.error(f"{self.dataset_name}: info template file does not exist")
            return {}

        auto_generated_info: dict = self._get_auto_generate_info()
        info: dict = yaml.safe_load(self.info_template_file.read_text(encoding="utf-8"))
        info.update(auto_generated_info)

        return info

    def generate_and_save(self) -> tuple[bool, str]:
        """
        Generate dataset info and save to YAML file.

        Returns:
            tuple[bool, str]: (success status, error message if failed or empty string if success)
        """
        try:
            # Generate info
            ds_info = self.generate_info()

            # Prepare output file path
            ds_info_file = self.output_path / self.dataset_name / DATASET_INFO_FILE
            ds_info_file.parent.mkdir(parents=True, exist_ok=True)

            # Write YAML file
            with open(ds_info_file, "w+", encoding="utf-8") as f:
                yaml.safe_dump(ds_info, f, allow_unicode=True, sort_keys=False)

            if self.logger:
                self.logger.debug(f"{self.dataset_name}: Generated YAML at {ds_info_file}")

            return True, ""

        except Exception as e:
            error_msg = f"YAML generation failed: {e}"
            if self.logger:
                self.logger.error(f"{self.dataset_name}: {error_msg}")
            return False, error_msg
