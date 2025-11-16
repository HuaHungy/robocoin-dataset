"""
RoboCoin Datasets Generate Dataset Info YAML for Single Datasets

This module provides a function for generating dataset info YAML files for individual
datasets during the upload process. It uses the SingleDatasetInfoGenerator which works
directly with hardlink paths without requiring root_path manipulation.

Usage:
  Called internally during upload process, or standalone with:
  python -m robocoin.datasets.gen_info --config configs/gen_info.yaml
"""

import logging
import traceback
from pathlib import Path

import draccus
from tqdm import tqdm

from robocoin_dataset.hub_upload.lerobot.dataset_info_util import LocalDsInfoConfig, LocalDsInfoUtil

from .single_dataset_info_generator import SingleDatasetInfoGenerator


def gen_info(hardlink_path: Path, output_path: Path, logger: logging.Logger | None = None) -> tuple[bool, str]:
    """
    Generate dataset info YAML for a single dataset using direct hardlink path.

    This function uses SingleDatasetInfoGenerator which reads directly from the
    hardlink path without requiring root_path setup, eliminating the need for
    temporary root_path manipulation.

    Args:
        hardlink_path: Path to the hardlink directory (full dataset path)
        output_path: Output path for the YAML file
        logger: Optional logger instance

    Returns:
        tuple[bool, str]: (success status, error message if failed or empty string if success)
    """
    try:
        # Use the new single-dataset generator (no root_path manipulation needed!)
        generator = SingleDatasetInfoGenerator(
            dataset_path=hardlink_path,
            output_path=output_path,
            task_tags_yamls_dir=None,  # Optional, can be added if needed
            logger=logger,
        )

        # Generate and save
        success, error = generator.generate_and_save()

        if success:
            ds_info_file = output_path / hardlink_path.name / "dataset_info.yml"
            tqdm.write(f"      ✅ YAML: {ds_info_file}")
            if logger:
                logger.debug(f"{hardlink_path.name}: Generated YAML at {ds_info_file}")
        else:
            tqdm.write(f"      ❌ YAML generation failed: {error}")

        return success, error

    except Exception as e:
        tb = traceback.format_exc()
        error_msg = f"YAML generation failed: {e}\n\nFull traceback:\n{tb}"
        tqdm.write(f"      ❌ YAML generation failed: {e}")
        if logger:
            logger.error(f"{hardlink_path.name}: {error_msg}")
        return False, error_msg


if __name__ == "__main__":
    """
    Main entry point for the batch dataset info generator.

    Parses command line configuration and runs the batch info generation process.
    This uses the original LocalDsInfoUtil class for batch generation.
    """
    config = draccus.parse(LocalDsInfoConfig)
    generator = LocalDsInfoUtil(config)
    generator.generate_infos()
    pass
