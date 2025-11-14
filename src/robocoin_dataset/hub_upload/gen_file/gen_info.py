"""
RoboCoin Datasets Generate Dataset Readme.md from readme_template/readme.j2 template
usage:
python -m robocoin.datasets.gen_readme --config configs/upload.yaml
"""

import logging
import traceback
from pathlib import Path

import draccus
import yaml
from tqdm import tqdm

from robocoin_dataset.hub_upload.lerobot.constant import DATASET_INFO_FILE
from robocoin_dataset.hub_upload.lerobot.dataset_info_util import LocalDsInfoConfig, LocalDsInfoUtil


def gen_info(hardlink_path: Path, output_path: Path, logger: logging.Logger | None = None) -> tuple[bool, str]:
  """
  Generate dataset info YAML for a single dataset.

  Args:
      hardlink_path: Path to the hardlink directory
      output_path: Output path for the YAML file
      logger: Optional logger instance

  Returns:
      tuple[bool, str]: (success status, error message if failed or empty string if success)
  """
  try:
    # Temporarily change root_path to hardlink's parent
    temp_root = hardlink_path.parent
    ds_name = hardlink_path.name

    # Create info generator with temporary config
    info_config = LocalDsInfoConfig(
      root_path=str(temp_root),
      output_path=str(output_path),
      task_tags_yamls_dir=""
    )
    info_generator = LocalDsInfoUtil(info_config)

    # Generate info for this specific dataset
    ds_info = info_generator._generate_info(ds_name)

    # Write YAML file
    ds_info_file = output_path.joinpath(ds_name, DATASET_INFO_FILE)
    ds_info_file.parent.mkdir(parents=True, exist_ok=True)

    with open(ds_info_file, "w+", encoding="utf-8") as f:
      yaml.safe_dump(ds_info, f, allow_unicode=True, sort_keys=False)

    # Console output with path
    tqdm.write(f"      ✅ YAML: {ds_info_file}")
    if logger:
      logger.debug(f"{ds_name}: Generated YAML at {ds_info_file}")
    return True, ""

  except Exception as e:
    tb = traceback.format_exc()
    error_msg = f"YAML generation failed: {e}\n\nFull traceback:\n{tb}"
    tqdm.write(f"      ❌ YAML generation failed: {e}")
    if logger:
      logger.error(f"{hardlink_path.name}: {error_msg}")
    return False, error_msg


if __name__ == "__main__":
  """
    Main entry point for the dataset info generator.

    Parses command line configuration and runs the info generation process.
    """
  config = draccus.parse(LocalDsInfoConfig)
  generator = LocalDsInfoUtil(config)
  generator.generate_infos()
  pass
