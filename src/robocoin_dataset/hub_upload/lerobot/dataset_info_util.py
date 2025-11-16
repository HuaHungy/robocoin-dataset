"""
RoboCoin Datasets Generate Dataset Readme.md from readme_template/readme.j2 template
usage:
python -m robocoin.datasets.gen_readme --config configs/upload.yaml
"""

import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import draccus
import yaml

from .constant import (
    ANNOTATIONS_DIR,
    DATASET_INFO_FILE,
    LEROBOT_META_INFO_FILE,
    LEROBOT_META_TASKS_FILE,
)
from .local_datasets_util import LocalDsConfig, LocalDsUtil


@dataclass
class LocalDsInfoConfig(LocalDsConfig):
    """
    Configuration class for local dataset information generation.

    Attributes:
        task_tags_yamls_dir (str): Directory path containing task tags YAML files. Defaults to empty string.
        output_path (str): Path to the output directory for generated dataset info files. Defaults to empty string.
    """

    task_tags_yamls_dir: str = ""
    output_path: str = ""


class LocalDsInfoUtil(LocalDsUtil):
    """
    Utility class for generating dataset information files.

    This class generates dataset information files by extracting metadata from
    dataset files and combining it with template information.

    Attributes:
        config (LocalDsInfoConfig): Configuration object for the info generator.
        logger: Logger instance for the info generator.
    """

    def __init__(self, config: LocalDsInfoConfig) -> None:
        """
        Initialize the info generator with configuration.

        Args:
            config (LocalDsInfoConfig): Configuration object for the info generator.
        """
        super().__init__(config)
        self.config = config

        self.logger = self.setup_logger(logger_name="GEN_DATASET_INFO")

    @cached_property
    def info_template_file(self) -> Path:
        """
        Get the path to the dataset info template file with validation.

        Returns:
            Path: Absolute path to the info template file.

        Raises:
            FileNotFoundError: If the info template file does not exist.
        """
        # Template is in the readmes module, go up to hub_upload, then to readmes
        path = Path(__file__).parent.parent.parent.joinpath("readmes", "templates", "dataset_info.yml")
        if not path.exists():
            raise FileNotFoundError(f"info template file {path} does not exists")
        return path

    @cached_property
    def output_path(self) -> Path:
        """
        Get the output path for generated info files with validation.

        Returns:
            Path: Absolute path to the output directory.

        Raises:
            ValueError: If output_path is not set in configuration.
        """
        if not self.config.output_path:
            raise ValueError("Output path is not set.")
        output_path = Path(self.config.output_path).expanduser().absolute()
        if not output_path.exists():
            output_path.mkdir(parents=True, exist_ok=True)
        return output_path

    def _get_info_from_lerobot_meta(self, ds_name: str) -> tuple[int, int, str]:
        """
        Extract information from LeRobot metadata files.

        IMPORTANT: This method reads from TWO specific files ONLY:
        - meta/info.json: for total_episodes, total_frames
        - meta/tasks.jsonl: for task descriptions
        It does NOT read from any other files.

        Args:
            ds_name (str): Name of the dataset.

        Returns:
            tuple[int, int, str]: Episodes count, frames count, and tasks list as string.

        Raises:
            FileNotFoundError: If metadata files do not exist.
            Exception: If there are errors reading the files.
        """
        info_file = self.root_path.joinpath(ds_name, LEROBOT_META_INFO_FILE)
        tasks_file = self.root_path.joinpath(ds_name, LEROBOT_META_TASKS_FILE)
        if not info_file.exists():
            raise FileNotFoundError(f"dataset meta info file {info_file} does not exists")

        if not tasks_file.exists():
            raise FileNotFoundError(f"dataset meta tasks file {tasks_file} does not exists")

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
            self.logger.error(f"Failed to read meta info file {info_file}: {e}")
            raise e

        # Read tasks from meta/tasks.jsonl
        try:
            with open(tasks_file, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        task_data = json.loads(line)
                        tasks_list.append(task_data.get("task", ""))
                    except json.JSONDecodeError as e:
                        self.logger.error(f"Failed to decode JSON from line: {line.strip()}")
                        raise e
        except Exception as e:
            self.logger.error(f"Failed to read tasks file {tasks_file}: {e}")
            raise e

        tasks = "\n".join(tasks_list)
        return episodes_num, frames_num, tasks

    def _get_subtasks_from_annotation(self, ds_name: str) -> list[str]:
        """
        Extract subtasks from dataset annotation files (new structure).

        IMPORTANT: This method ONLY reads from annotations/subtask_annotations.jsonl.
        It does NOT read from any other files (info.json, tasks.jsonl, etc.)

        Args:
            ds_name (str): Name of the dataset.

        Returns:
            list[str]: List of unique subtasks.

        Note:
            Reads subtask_annotations.jsonl from the annotations directory and extracts
            unique subtask values from the "subtask" field. Deduplication is case-insensitive,
            keeping the first occurrence of each unique subtask.
        """
        annotations_dir = self.root_path.joinpath(ds_name, ANNOTATIONS_DIR)

        if not annotations_dir.exists():
            self.logger.warning(
                f"dataset {ds_name}: annotations directory '{ANNOTATIONS_DIR}' not found. "
                "Subtasks will be empty."
            )
            return ""

        subtask_file = annotations_dir / "subtask_annotations.jsonl"

        if not subtask_file.exists():
            self.logger.warning(
                f"dataset {ds_name}: subtask_annotations.jsonl not found in '{ANNOTATIONS_DIR}'. "
                "Subtasks will be empty."
            )
            return ""

        # Extract unique subtasks from the JSONL file (case-insensitive)
        # Use a dict to preserve the first occurrence of each unique subtask
        subtasks_dict = {}
        try:
            with open(subtask_file, encoding='utf-8') as f:
                for line in f:
                    if line := line.strip():
                        data = json.loads(line)
                        if "subtask" in data:
                            subtask = data["subtask"]
                            # Use lowercase as key for case-insensitive comparison
                            # but store the original value
                            subtask_lower = subtask.lower()
                            if subtask_lower not in subtasks_dict:
                                subtasks_dict[subtask_lower] = subtask

            # Sort by the lowercase key and return as list
            sorted_subtasks = [subtasks_dict[key] for key in sorted(subtasks_dict.keys())]

            self.logger.info(f"dataset {ds_name}: extracted {len(sorted_subtasks)} unique subtasks from annotations.")
            return sorted_subtasks

        except Exception as e:
            self.logger.error(
                f"dataset {ds_name}: error reading subtask_annotations.jsonl: {e}. "
                "Subtasks will be empty."
            )
            return []

    def _generate_size_label(self, size: int) -> str:
        """
        Generate size category label based on frame count.

        Args:
            size (int): Number of frames.

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

    def _generate_tags(self, ds_name: str) -> list[str]:
        """
        Generate tags for a dataset from YAML tag files (optional).

        Args:
            ds_name (str): Name of the dataset.

        Returns:
            list[str]: List of tags for the dataset. Empty list if no tags directory configured.
        """
        if not self.config.task_tags_yamls_dir:
            # This is optional - just return empty list without warning
            return []
        tags_file_path = Path(self.config.task_tags_yamls_dir).joinpath(f"{ds_name}.yml")
        if not tags_file_path.exists():
            # Tag file doesn't exist for this dataset - that's ok
            return []
        with open(tags_file_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _extract_info_from_meta_json(self, ds_name: str) -> dict:
        """
        Extract comprehensive information from meta/info.json file.

        IMPORTANT: This method ONLY reads from meta/info.json.
        It does NOT read from any other files (tasks.jsonl, subtask_annotations.jsonl, etc.)

        Args:
            ds_name (str): Name of the dataset.

        Returns:
            dict: Dictionary containing extracted information from info.json.
        """
        info_file = self.root_path.joinpath(ds_name, LEROBOT_META_INFO_FILE)
        if not info_file.exists():
            self.logger.warning(f"dataset {ds_name}: info.json not found")
            return {}

        try:
            with open(info_file, encoding="utf-8") as f:
                meta_info = json.load(f)
        except Exception as e:
            self.logger.error(f"dataset {ds_name}: failed to read info.json: {e}")
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

    def _get_auto_generate_info(self, ds_name: str) -> dict:
        """
        Automatically generate dataset information from dataset files.

        Args:
            ds_name (str): Name of the dataset.

        Returns:
            dict: Dictionary containing auto-generated dataset information.
        """
        log_prefix = f"dataset {ds_name}:"
        try:
            self.check_dataset_dir_valid(ds_name=ds_name)
        except Exception as e:
            self.logger.error(f"{log_prefix} dataset {ds_name} is not valid: {e}")
            return {}

        # Extract comprehensive information from info.json
        extracted_info = self._extract_info_from_meta_json(ds_name)

        # Get legacy fields for backward compatibility
        episodes_num, frames_num, tasks = self._get_info_from_lerobot_meta(ds_name)
        sub_tasks = self._get_subtasks_from_annotation(ds_name)
        size_category = self._generate_size_label(frames_num)
        tags = self._generate_tags(ds_name)

        # Merge all information
        auto_info = {
            "size_categories": size_category,
            "tasks": tasks,
            "sub_tasks": sub_tasks,
        }

        # Add custom tags if provided
        if tags:
            if "tags" not in auto_info:
                auto_info["tags"] = []
            # Extend existing tags from template with custom tags
            auto_info["dataset_tags"] = tags

        # Merge extracted info (this will override any conflicts)
        auto_info.update(extracted_info)

        return auto_info

    def _generate_info(self, ds_name: str) -> dict:
        """
        Generate complete dataset information by combining template and auto-generated data.

        Args:
            ds_name (str): Name of the dataset.

        Returns:
            dict: Complete dataset information dictionary.
        """
        if not self.info_template_file.exists():
            self.logger.error(
                f"dataset {ds_name}: info template file {self.info_template_file} does not exist"
            )
            return {}
        auto_generated_info: dict = self._get_auto_generate_info(ds_name=ds_name)
        info: dict = yaml.safe_load(self.info_template_file.read_text(encoding="utf-8"))
        info.update(auto_generated_info)

        return info

    def generate_infos(self) -> None:
        """
        Generate information files for all valid datasets in the root path.

        This method validates datasets, generates information for each one,
        and saves the information to YAML files in the output directory.
        """
        self.check_root_path_valid()

        if not self.info_template_file.exists():
            raise FileNotFoundError(f"info template file {self.info_template_file} not found")

        ds_names = self.get_root_path_subdirs()
        for ds_name in ds_names:
            log_prefix = f"dataset {ds_name}:"
            try:
                self.check_dataset_dir_valid(ds_name=ds_name)
            except Exception as e:
                self.logger.info(f"dataset {ds_name} is not a valid dataset: {e}")
                continue

            ds_info_file = self.output_path.joinpath(ds_name, DATASET_INFO_FILE)
            try:
                ds_info_file.parent.mkdir(parents=True, exist_ok=True)
                with open(
                    ds_info_file,
                    "w+",
                    encoding="utf-8",
                ) as f:
                    yaml.safe_dump(
                        self._generate_info(ds_name=ds_name),
                        f,
                        allow_unicode=True,
                        sort_keys=False,
                    )
                    self.logger.info(f"Generated info for '{ds_name}' at {ds_info_file}")
            except Exception as e:
                self.logger.error(f"{log_prefix} generate {DATASET_INFO_FILE} failed, {e}")

    pass


if __name__ == "__main__":
    """
    Main entry point for the dataset info generator.

    Parses command line configuration and runs the info generation process.
    """
    config = draccus.parse(LocalDsInfoConfig)
    generator = LocalDsInfoUtil(config)
    generator.generate_infos()
    pass
