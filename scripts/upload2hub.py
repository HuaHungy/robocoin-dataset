"""
RoboCoin Datasets Uploader

This script is for uploading datasets to the hub, is a script rather than a module.
All the configs are set according to the config file, such as upload2ms.yml or upload2hf.yml in examples/configs/
All uploading process needs KEY ITEMS:
token(to identify the target account and the admission to upload),
root_path(the folder path that contains all the subfolder to be uploaded)

Usage:
python scripts/upload2hub.py --config configs/upload.yaml

Example:
python scripts/upload2hub.py --config configs/upload2ms.yml
python scripts/upload2hub.py --config configs/upload2hf.yml
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
