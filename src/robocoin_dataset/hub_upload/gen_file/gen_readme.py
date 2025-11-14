"""
RoboCoin Datasets Generate Dataset Readme.md from readme_template/readme.j2 template
usage:
python -m robocoin.datasets.gen_readme --config configs/upload.yaml
"""

import logging
import traceback
from pathlib import Path

import draccus
from tqdm import tqdm

from robocoin_dataset.readmes.dataset_readme_util import LocalDsReadmeConfig, LocalDsReadmeUtil


def gen_readme(hardlink_path: Path, dataset_info_root_path: Path, logger: logging.Logger | None = None) -> tuple[bool, str]:
  """
  Generate README.md for a single dataset.

  Args:
      hardlink_path: Path to the hardlink directory
      dataset_info_root_path: Path containing the dataset info YAML files
      logger: Optional logger instance

  Returns:
      tuple[bool, str]: (success status, error message if failed or empty string if success)
  """
  try:
    # Temporarily change root_path to hardlink's parent
    temp_root = hardlink_path.parent
    ds_name = hardlink_path.name

    # Create readme generator with temporary config
    readme_config = LocalDsReadmeConfig(
      root_path=str(temp_root),
      dataset_info_root_path=str(dataset_info_root_path)
    )
    readme_generator = LocalDsReadmeUtil(readme_config)

    # Generate README for this specific dataset
    readme_generator._generate_readme(ds_name)

    # Console output with path
    readme_path = hardlink_path / "README.md"
    tqdm.write(f"      ✅ README: {readme_path}")
    if logger:
      logger.debug(f"{ds_name}: Generated README at {readme_path}")
    return True, ""

  except Exception as e:
    tb = traceback.format_exc()
    error_msg = f"README generation failed: {e}\n\nFull traceback:\n{tb}"
    tqdm.write(f"      ❌ README generation failed: {e}")
    if logger:
      logger.error(f"{hardlink_path.name}: {error_msg}")
    return False, error_msg


if __name__ == "__main__":
  """
    Main entry point for the README generator.

    Parses command line configuration and runs the README generation process.
    """
  config = draccus.parse(LocalDsReadmeConfig)
  generator = LocalDsReadmeUtil(config)
  generator.generate_readmes()
  pass
