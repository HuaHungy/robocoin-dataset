"""
RoboCoin Datasets Uploader
usage:
python -m scripts/upload2hub.py --config configs/upload.yaml
"""

import draccus

from robocoin_dataset.hub_upload.lerobot.hub_upload_util import (
  LocalDsUploadConfig,
  LocalDsUploadUtil,
)

if __name__ == "__main__":
  """
    Main entry point for the dataset uploader.

    Parses command line configuration and runs the upload process.
    """
  config = draccus.parse(LocalDsUploadConfig)
  uploader = LocalDsUploadUtil(config)
  uploader.upload_datasets()
  pass
