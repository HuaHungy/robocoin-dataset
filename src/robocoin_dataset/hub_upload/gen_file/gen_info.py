"""
RoboCoin Datasets Generate Dataset Info Files

Generates dataset info YAML files by extracting metadata from dataset files
and combining it with template information.

Usage:
    python -m robocoin_dataset.hub_upload.gen_file.gen_info --config configs/upload.yaml
"""

import draccus

from robocoin_dataset.hub_upload.lerobot.dataset_info_util import LocalDsInfoConfig, LocalDsInfoUtil

if __name__ == "__main__":
    """
    Main entry point for the dataset info generator.

    Parses command line configuration and runs the info generation process.
    """
    config = draccus.parse(LocalDsInfoConfig)
    generator = LocalDsInfoUtil(config)
    generator.generate_infos()
