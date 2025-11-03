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

import getpass
import sys

import draccus

from robocoin_dataset.hub_upload.lerobot.hub_upload_util import (
  LocalDsUploadConfig,
  LocalDsUploadUtil,
)


def prompt_for_token(config: LocalDsUploadConfig) -> str:
  """
  Prompt user to input authentication token with security warnings.

  Args:
      config: The parsed configuration object

  Returns:
      str: The authentication token (from user input or config file)
  """
  print("\n" + "=" * 70)
  print("AUTHENTICATION TOKEN REQUIRED")
  print("=" * 70)
  print(f"Target Hub: {config.hub_name}")
  print("\nFor security reasons, please provide your authentication token.")
  print("The token will not be echoed to the screen.\n")

  # Prompt for token
  token = getpass.getpass("Enter your authentication token (or press Enter to skip): ").strip()

  if token:
    print("✓ Token received from user input.")
    return token

  # User did not provide token, check config file
  print("\n" + "!" * 70)
  print("WARNING: No token provided via prompt")
  print("!" * 70)
  print("\n⚠️  Token is a REQUIRED parameter for uploading datasets.")
  print("⚠️  It is STRONGLY RECOMMENDED to provide the token via prompt.\n")

  # Check if token exists in config file
  config_token = config.token
  if config_token and config_token.upper() not in ["NULL", "NONE", ""]:
    print("🔍 Searching for token in configuration file...")
    print("   Location: Configuration field 'token'")
    print(f"   Found: {'*' * min(len(config_token), 8)}... (hidden for security)\n")

    print("⛔ SECURITY WARNING:")
    print("   ━" * 35)
    print("   • Storing tokens in configuration files is NOT RECOMMENDED")
    print("   • This practice may trigger Git secret detection checks")
    print("   • Git may BLOCK your push if a token is detected")
    print("   • Exposed tokens pose a SECURITY RISK to your account")
    print("   ━" * 35)
    print("\n⚠️  ACTION REQUIRED:")
    print("   → Remove the token from your configuration file immediately")
    print("   → Ensure all commits do not contain the token value")
    print("   → Use the prompt method for token input in the future\n")

    # Ask for confirmation
    response = input("Continue with token from config file? (yes/no): ").strip().lower()
    if response in ["yes", "y"]:
      print("✓ Proceeding with token from configuration file...\n")
      return config_token
    print("✗ Upload cancelled by user.")
    sys.exit(1)
  else:
    print("✗ No valid token found in configuration file.")
    print("✗ Cannot proceed without authentication token.")
    print("\nPlease run the script again and provide your token when prompted.")
    sys.exit(1)


if __name__ == "__main__":
  """
  Main entry point for the dataset uploader.

  Parses command line configuration, prompts for authentication token,
  and runs the upload process.

  If db_file_path is provided, uses database-driven batch upload to unified repository.
  Otherwise, uses traditional directory-based upload.
  """
  # Parse configuration from YAML file
  config = draccus.parse(LocalDsUploadConfig)

  # Prompt user for token with security warnings
  token = prompt_for_token(config)

  # Override config token with the obtained token
  config.token = token

  # Initialize uploader
  uploader = LocalDsUploadUtil(config)

  # Choose upload method based on configuration
  if config.db_file_path:
    # Database-driven upload to unified repository
    uploader.upload_datasets_from_db()
  else:
    # Traditional directory-based upload
    uploader.upload_datasets()
  pass
