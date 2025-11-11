"""
RoboCoin Datasets Uploader

This script uploads datasets to the hub using a database-driven strategy.
All configs are set according to the config file, such as upload2ms.yml or upload2hf.yml in examples/configs/

KEY REQUIREMENTS:
- config: YAML config file containing hub_name, db_file_path, and other settings
- token: Authentication token (optional, can be provided via CLI, config, or interactive prompt)
- db_file_path: Path to SQLite database (optional, automatically read from config if not specified)

Usage:
python scripts/hub_upload/upload2hub.py --config configs/upload.yaml [--token <token>] [--db_file_path <path>]

Example (minimal, reads db_file_path from config):
python scripts/hub_upload/upload2hub.py --config examples/configs/upload2ms.yml

Example (explicit token):
python scripts/hub_upload/upload2hub.py --config examples/configs/upload2ms.yml --token YOUR_TOKEN
"""

import getpass
import sys

import draccus

from robocoin_dataset.hub_upload.lerobot.hub_upload_util import (
  LocalDsUploadConfig,
  LocalDsUploadUtil,
)


def prompt_for_token(config: LocalDsUploadConfig, token_from_cli: bool) -> str:

  config_token = config.token

  # Return CLI token if provided
  if config_token and config_token.upper() not in ["NULL", "NONE", ""] and token_from_cli:
    return config_token

  # Prompt for token
  token = getpass.getpass(f"🔑 {config.hub_name.value} token: ").strip()
  if token:
    return token

  # Fall back to config token with deprecation warning
  if config_token and config_token.upper() not in ["NULL", "NONE", ""]:
    response = input("⚠️  Use token from config? (y/n): ").strip().lower()
    if response in ["y", "yes"]:
      return config_token

  print("❌ No token")
  sys.exit(1)


if __name__ == "__main__":

  # Parse configuration from YAML file and command line arguments
  config = draccus.parse(LocalDsUploadConfig)

  # Detect if token was provided via command line argument
  token_from_cli = "--token" in sys.argv

  # Get or prompt for token with security warnings
  token = prompt_for_token(config, token_from_cli)
  config.token = token

  # Create uploader and run upload
  uploader = LocalDsUploadUtil(config)
  uploader.upload_datasets_from_db()
