"""
RoboCoin Datasets Uploader

This script uploads datasets to the hub using a database-driven strategy.
All configs are set according to the config file, such as upload2ms.yml or upload2hf.yml in examples/configs/

KEY REQUIREMENTS:
- token: Authentication token to identify the target account and upload permission
- db_file_path: Path to the SQLite database file that tracks dataset upload status

Usage:
python scripts/hub_upload/upload2hub.py --config configs/upload.yaml --db_file_path <path> --token <token>

Example:
python scripts/hub_upload/upload2hub.py \
--config examples/configs/upload2ms.yml \
--db_file_path db/datasets_new.db \
--token YOUR_TOKEN
"""

import getpass
import sys
from pathlib import Path

import draccus
import yaml

from robocoin_dataset.hub_upload.lerobot.hub_upload_util import (
  LocalDsUploadConfig,
  LocalDsUploadUtil,
)


def prompt_for_token(config: LocalDsUploadConfig, token_from_cli: bool) -> str:
  """
  Prompt user to input authentication token with security warnings.

  Args:
      config: The parsed configuration object
      token_from_cli: Whether token was provided via command line argument

  Returns:
      str: The authentication token (from CLI argument, user input, or config file)
  """
  # Check if token was provided via command line argument (--token)
  config_token = config.token
  if config_token and config_token.upper() not in ["NULL", "NONE", ""] and token_from_cli:
    print("✓ Token received from --token argument")
    return config_token

  print(f"\n🔑 Authentication required for {config.hub_name}")
  token = getpass.getpass("Enter token (or press Enter to use config): ").strip()

  if token:
    print("✓ Token received from user input.")
    return token

  # User did not provide token, check config file
  if config_token and config_token.upper() not in ["NULL", "NONE", ""]:
    print("⚠️  Using token from config file (not recommended for security)")
    response = input("Continue? (y/n): ").strip().lower()
    if response in ["yes", "y"]:
      return config_token
    print("✗ Upload cancelled")
    sys.exit(1)
  else:
    print("✗ No token provided. Use --token argument or enter at prompt.")
    sys.exit(1)


if __name__ == "__main__":
  """
  Main entry point for the dataset uploader.

  This script uses a database-driven upload strategy exclusively.
  Parses command line configuration, prompts for authentication token,
  and runs the database-driven upload process.

  Supports three methods for providing authentication token:
  1. Command line argument: --token YOUR_TOKEN (recommended)
  2. Interactive prompt: Enter token when prompted
  3. Config file: token field in YAML (not recommended for security)
  """
  # Parse configuration from YAML file and command line arguments
  config = draccus.parse(LocalDsUploadConfig)

  # Detect if token was provided via command line argument
  token_from_cli = "--token" in sys.argv

  # Get or prompt for token with security warnings
  token = prompt_for_token(config, token_from_cli)

  # Override config token with the obtained token
  config.token = token

  # Check if db_file_path was specified via command line
  db_path_specified = "--db_file_path" in sys.argv or "--db-file-path" in sys.argv

  # Require db_file_path to be specified
  if not db_path_specified:
    print("\n❌ --db_file_path is required")
    print("Usage: --db_file_path <path> or --db_file_path default")
    print("Example: python scripts/hub_upload/upload2hub.py --config examples/configs/upload2hf.yml --db_file_path /path/to/db --token TOKEN\n")
    sys.exit(1)

  # Handle "default" keyword to read from YAML config
  if config.db_file_path.lower() in ["default", "", "null", "none"]:
    # Read from YAML config file - need to parse it again
    # Find the config file path from sys.argv
    config_file = None
    for i, arg in enumerate(sys.argv):
      if arg in ["--config", "-c"] and i + 1 < len(sys.argv):
        config_file = sys.argv[i + 1]
        break

    if config_file and Path(config_file).exists():
      with open(config_file) as f:
        yaml_config = yaml.safe_load(f)
        yaml_db_path = yaml_config.get('db_file_path', '')
        if yaml_db_path and yaml_db_path.lower() not in ["", "null", "none"]:
          config.db_file_path = yaml_db_path
          print(f"ℹ️  Using db_file_path from config: {yaml_db_path}")
        else:
          print(f"❌ No valid db_file_path in YAML config: {config_file}")
          sys.exit(1)
    else:
      print("❌ Config file not found. Provide explicit --db_file_path")
      sys.exit(1)

  # Validate that db_file_path has a valid value
  if not config.db_file_path or config.db_file_path.strip() in ["", "null", "none"]:
    print("❌ Invalid db_file_path. Provide a path or 'default'")
    sys.exit(1)

  # Database-driven upload - create uploader instance and call upload method
  uploader = LocalDsUploadUtil(config)
  uploader.upload_datasets_from_db()
