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
    print("\n" + "=" * 70)
    print("AUTHENTICATION TOKEN DETECTED")
    print("=" * 70)
    print(f"Target Hub: {config.hub_name}")
    print("✓ Token received from command line argument (--token)")
    print(f"   Token: {'*' * min(len(config_token), 8)}... (hidden for security)\n")
    return config_token

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
  print("⚠️  It is STRONGLY RECOMMENDED to provide the token via prompt or --token argument.\n")

  # Check if token exists in config file
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
    print("   → Use the --token argument or prompt method for token input in the future\n")

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
    print("\nPlease run the script again and provide your token via --token argument or prompt.")
    sys.exit(1)


if __name__ == "__main__":
  """
  Main entry point for the dataset uploader.

  Parses command line configuration, prompts for authentication token,
  and runs the upload process.

  If db_file_path is provided, uses database-driven batch upload to unified repository.
  Otherwise, uses traditional directory-based upload.

  Supports three methods for providing authentication token:
  1. Command line argument: --token YOUR_TOKEN (recommended)
  2. Interactive prompt: Enter token when prompted
  3. Config file: token field in YAML (not recommended for security)
  """
  # Parse configuration from YAML file and command line arguments
  config = draccus.parse(LocalDsUploadConfig)

  # Detect if token was provided via command line argument
  # If token is not NULL/NONE/empty and we have CLI args, it likely came from --token
  token_from_cli = False
  if "--token" in sys.argv:
    token_from_cli = True

  # Get or prompt for token with security warnings
  token = prompt_for_token(config, token_from_cli)

  # Override config token with the obtained token
  config.token = token

  # Detect which upload mode was explicitly specified via command line
  db_path_specified = "--db_file_path" in sys.argv or "--db-file-path" in sys.argv
  root_path_specified = "--root_path" in sys.argv or "--root-path" in sys.argv

  # Check for mutually exclusive options
  if db_path_specified and root_path_specified:
    print("\n" + "❌ " * 35)
    print("ERROR: Conflicting upload modes specified")
    print("❌ " * 35)
    print("\nYou cannot specify both --db_file_path and --root_path simultaneously.")
    print("These options are mutually exclusive:")
    print("  • --db_file_path: Upload datasets from database (recommended)")
    print("  • --root_path: Upload datasets from directory structure (legacy)")
    print("\nPlease choose only one upload mode.\n")
    sys.exit(1)

  # Require explicit mode selection
  if not db_path_specified and not root_path_specified:
    print("\n" + "⚠️ " * 35)
    print("WARNING: No upload mode specified")
    print("⚠️ " * 35)
    print("\nYou MUST explicitly specify the upload mode via command line.")
    print("Choose one of the following:")
    print("  • --db_file_path <path>     : Database-driven upload (recommended)")
    print("  • --db_file_path default    : Use db_file_path from YAML config")
    print("  • --root_path <path>        : Directory-based upload (legacy)")
    print("  • --root_path default       : Use root_path from YAML config")
    print("\nExamples:")
    print("  # Database mode with explicit path:")
    print("  python scripts/hub_upload/upload2hub.py \\")
    print("    --config examples/configs/upload2hf.yml \\")
    print("    --db_file_path /path/to/datasets.db \\")
    print("    --token YOUR_TOKEN\n")
    print("  # Database mode with path from YAML:")
    print("  python scripts/hub_upload/upload2hub.py \\")
    print("    --config examples/configs/upload2hf.yml \\")
    print("    --db_file_path default \\")
    print("    --token YOUR_TOKEN\n")
    print("  # Directory mode with explicit path:")
    print("  python scripts/hub_upload/upload2hub.py \\")
    print("    --config examples/configs/upload2hf.yml \\")
    print("    --root_path /path/to/datasets \\")
    print("    --token YOUR_TOKEN\n")
    sys.exit(1)

  # Handle "default" keyword to read from YAML config
  if db_path_specified:
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
            print(f"ℹ️  Using db_file_path from YAML config: {yaml_db_path}")
          else:
            print("\n❌ ERROR: 'default' specified but no valid db_file_path found in YAML config")
            print(f"   Config file: {config_file}")
            print(f"   db_file_path in YAML: '{yaml_db_path}'")
            print("\nPlease specify a valid path in the YAML config or provide an explicit path.\n")
            sys.exit(1)
      else:
        print("\n❌ ERROR: Cannot read default value - config file not found")
        print("   Please provide an explicit --db_file_path value.\n")
        sys.exit(1)

  if root_path_specified:
    if str(config.root_path).lower() in ["default", "", "null", "none", "."]:
      # Read from YAML config file
      config_file = None
      for i, arg in enumerate(sys.argv):
        if arg in ["--config", "-c"] and i + 1 < len(sys.argv):
          config_file = sys.argv[i + 1]
          break

      if config_file and Path(config_file).exists():
        with open(config_file) as f:
          yaml_config = yaml.safe_load(f)
          yaml_root_path = yaml_config.get('root_path', '')
          if yaml_root_path and str(yaml_root_path).lower() not in ["", "null", "none", "."]:
            config.root_path = Path(yaml_root_path)
            print(f"ℹ️  Using root_path from YAML config: {yaml_root_path}")
          else:
            print("\n❌ ERROR: 'default' specified but no valid root_path found in YAML config")
            print(f"   Config file: {config_file}")
            print(f"   root_path in YAML: '{yaml_root_path}'")
            print("\nPlease specify a valid path in the YAML config or provide an explicit path.\n")
            sys.exit(1)
      else:
        print("\n❌ ERROR: Cannot read default value - config file not found")
        print("   Please provide an explicit --root_path value.\n")
        sys.exit(1)

  # Validate that the chosen mode has a valid path
  if db_path_specified:
    if not config.db_file_path or config.db_file_path.strip() in ["", "null", "none"]:
      print("\n❌ ERROR: --db_file_path specified but no valid path provided")
      print("   Provide either a path or 'default' to read from YAML config.\n")
      sys.exit(1)

  # Initialize uploader
  uploader = LocalDsUploadUtil(config)

  # Choose upload method based on which mode was explicitly specified
  if db_path_specified:
    print(f"\n{'='*70}")
    print("📊 DATABASE-DRIVEN UPLOAD MODE")
    print(f"{'='*70}")
    print(f"Database: {config.db_file_path}")
    print(f"{'='*70}\n")
    # Database-driven upload
    uploader.upload_datasets_from_db()
  else:
    # root_path_specified must be True here (due to validation above)
    print(f"\n{'='*70}")
    print("📁 DIRECTORY-BASED UPLOAD MODE (Legacy)")
    print(f"{'='*70}")
    print(f"Root Path: {config.root_path}")
    print(f"{'='*70}\n")
    # Traditional directory-based upload
    uploader.upload_datasets()
  pass
