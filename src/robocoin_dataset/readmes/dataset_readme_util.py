"""
RoboCoin Datasets Generate Dataset Readme.md from readme_template/readme.j2 template
usage:
python -m robocoin.datasets.gen_readme --config configs/upload.yaml
"""

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import draccus
import yaml
from jinja2 import Environment, FileSystemLoader

from robocoin_dataset.hub_upload.lerobot.constant import (
  DATASET_INFO_FILE,
  LEROBOT_META_INFO_FILE,
  README_FILE,
)
from robocoin_dataset.hub_upload.lerobot.local_datasets_util import LocalDsConfig, LocalDsUtil


def generate_folder_structure(root_path: Path, max_files_per_dir: int = 5) -> str:
  """
  Generate a folder structure tree showing only leaf directories with limited files.

  This function traverses the directory tree and creates a visual representation where:
  - Only the deepest leaf directories are expanded
  - Each leaf directory shows at most max_files_per_dir files
  - Remaining files are represented as "(...)"

  Args:
      root_path (Path): Root directory path to generate structure from.
      max_files_per_dir (int): Maximum number of files to show per leaf directory. Defaults to 5.

  Returns:
      str: Formatted folder structure tree as a string.
  """

  def is_leaf_directory(path: Path) -> bool:
    """Check if a directory is a leaf (contains no subdirectories)."""
    try:
      return not any(item.is_dir() for item in path.iterdir())
    except (PermissionError, OSError):
      return True

  def get_sorted_items(path: Path) -> tuple[list[Path], list[Path]]:
    """Get sorted directories and files from a path."""
    try:
      items = list(path.iterdir())
      dirs = sorted([item for item in items if item.is_dir()], key=lambda x: x.name)
      files = sorted([item for item in items if item.is_file()], key=lambda x: x.name)
      return dirs, files
    except (PermissionError, OSError):
      return [], []

  def build_tree(path: Path, prefix: str = "", is_last: bool = True) -> list[str]:
    """Recursively build the tree structure."""
    lines = []

    if not path.exists():
      return lines

    # Add current directory
    connector = "└── " if is_last else "├── "
    if path == root_path:
      lines.append(f"{path.name}/")
    else:
      lines.append(f"{prefix}{connector}{path.name}/")

    # Get subdirectories and files
    dirs, files = get_sorted_items(path)

    # Determine the new prefix for children
    if path == root_path:
      new_prefix = ""
    else:
      new_prefix = prefix + ("    " if is_last else "│   ")

    # Check if this is a leaf directory
    if is_leaf_directory(path) and files:
      # Show only first max_files_per_dir files
      files_to_show = files[:max_files_per_dir]
      has_more = len(files) > max_files_per_dir

      for i, file in enumerate(files_to_show):
        is_last_file = (i == len(files_to_show) - 1) and not has_more
        file_connector = "└── " if is_last_file else "├── "
        lines.append(f"{new_prefix}{file_connector}{file.name}")

      if has_more:
        lines.append(f"{new_prefix}└── (...)")

    # Process subdirectories (but don't show their files unless they're leaf directories)
    for i, subdir in enumerate(dirs):
      is_last_dir = i == len(dirs) - 1
      lines.extend(build_tree(subdir, new_prefix, is_last_dir))

    return lines

  try:
    tree_lines = build_tree(root_path)
    return "\n".join(tree_lines)
  except Exception as e:
    return f"Error generating folder structure: {e}"


@dataclass
class LocalDsReadmeConfig(LocalDsConfig):
  """
  Configuration class for local dataset README generation.

  Attributes:
      dataset_info_root_path (str): Root path containing dataset info files. Defaults to empty string.
  """

  dataset_info_root_path: str = ""


class LocalDsReadmeUtil(LocalDsUtil):
  """
  Utility class for generating dataset README files from Jinja2 templates.

  This class generates README.md files for datasets by combining dataset information
  with a Jinja2 template, producing formatted documentation for each dataset.

  Attributes:
      config (LocalDsReadmeConfig): Configuration object for the README generator.
      logger: Logger instance for the README generator.
  """

  def __init__(self, config: LocalDsReadmeConfig) -> None:
    """
    Initialize the README generator with configuration.

    Args:
        config (LocalDsReadmeConfig): Configuration object for the README generator.
    """
    super().__init__(config)
    self.config = config

    self.logger = self.setup_logger(logger_name="GEN_DATASET_README")

  @cached_property
  def readme_template_file(self) -> Path:
    """
    Get the path to the README template file with validation.

    Returns:
        Path: Absolute path to the README template file.

    Raises:
        FileNotFoundError: If the README template file does not exist.
    """
    path = Path(__file__).parent.resolve().joinpath("templates", "readme.j2")
    if not path.exists():
      raise FileNotFoundError(f"readme template file {path} does not exists")
    return path

  def _generate_readme(self, ds_name: str) -> None:
    """
    Generate README file for a specific dataset using Jinja2 template.

    IMPORTANT: This method ALWAYS OVERWRITES the existing README.md file.
    The file is opened in write mode ('w'), which truncates any existing content.

    Args:
        ds_name (str): Name of the dataset to generate README for.

    Raises:
        FileNotFoundError: If meta info file does not exist.
        RuntimeError: If there are errors during README generation.
    """

    def get_meta_info_content() -> str:
      """
      Get the content of the meta info file.

      Returns:
          str: Content of the meta info file.

      Raises:
          FileNotFoundError: If meta info file does not exist.
      """
      meta_info_file = self.root_path.joinpath(ds_name, LEROBOT_META_INFO_FILE)
      if not meta_info_file.exists():
        raise FileNotFoundError(f"Meta info file {meta_info_file} does not exist.")
      return meta_info_file.read_text(encoding="utf-8")

    def get_folder_structure() -> str:
      """
      Get the folder structure tree for the dataset.

      Returns:
          str: Formatted folder structure tree showing leaf directories with first 5 files.
      """
      ds_path = self.root_path.joinpath(ds_name)
      return generate_folder_structure(ds_path, max_files_per_dir=5)

    ds_info_file = (
      Path(self.config.dataset_info_root_path)
      .joinpath(ds_name, DATASET_INFO_FILE)
      .expanduser()
      .absolute()
    )
    ds_info: dict
    try:
      with open(ds_info_file) as f:
        ds_info = yaml.safe_load(f)
    except Exception as e:
      raise RuntimeError(e) from e

    # Auto-generate structure if not provided in ds_info
    if "structure" not in ds_info or ds_info.get("structure") == "auto_generated":
      ds_info["structure"] = get_folder_structure()

    try:
      env = Environment(loader=FileSystemLoader(self.readme_template_file.parent))
      env.globals["get_meta_info_content"] = get_meta_info_content
      ###########################################################################
      # Remove _qced_hardlink suffix from dataset_name for display in README.md #
      display_dataset_name = ds_name.removesuffix("_qced_hardlink")
      readme_content = env.get_template(self.readme_template_file.name).render(
        dataset_name=display_dataset_name, **ds_info
      )

      ds_path = self.root_path.joinpath(ds_name)
      readme_file = ds_path.joinpath("README.md")

      # Always overwrite the README.md file
      with open(readme_file, "w", encoding="utf-8") as f:
        f.write(readme_content)
    except Exception as e:
      raise RuntimeError(e) from e

  def generate_readmes(self) -> None:
    """
    Generate README files for all valid datasets in the root path.

    This method validates datasets and generates README.md files for each one
    using the Jinja2 template and dataset information files.
    """
    self.check_root_path_valid()
    ds_names = self.get_root_path_subdirs()

    for ds_name in ds_names:
      self.check_dataset_dir_valid(ds_name=ds_name)
      log_prefix = f"dataset {ds_name}:"

      try:
        self._generate_readme(ds_name=ds_name)
        self.logger.info(f"{log_prefix} generate {README_FILE} successfully")
      except Exception as e:
        self.logger.error(f"{log_prefix} generate {README_FILE} failed, {e}")

  pass


if __name__ == "__main__":
  """
    Main entry point for the README generator.

    Parses command line configuration and runs the README generation process.
    """
  config = draccus.parse(LocalDsReadmeConfig)
  generator = LocalDsReadmeUtil(config)
  generator.generate_readmes()
  pass
