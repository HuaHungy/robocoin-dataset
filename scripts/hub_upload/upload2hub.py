"""
RoboCoin Datasets Uploader - Main CLI Entry Point

This script uploads datasets to the hub using a database-driven strategy.
It generates dataset info YAML files and README.md files ON-DEMAND for each dataset
right before uploading, using the hardlink paths from the database.

KEY FEATURES:
- On-demand generation of dataset info YAML files from metadata (per dataset)
- On-demand generation of README.md files from templates (per dataset)
- Upload datasets to HuggingFace or ModelScope
- Database-driven upload tracking
- Works with hardlinks at any location (not restricted to single root_path)

WORKFLOW:
    For each dataset in the database:
    1. Generate dataset_info.yml file from metadata
    2. Generate README.md file from template
    3. Upload dataset to hub

Usage:
    # Basic upload
    python scripts/hub_upload/upload2hub.py --config configs/upload.yaml

    # With authentication token
    python scripts/hub_upload/upload2hub.py \\
        --config configs/upload.yaml \\
        --token YOUR_TOKEN

    # With custom namespace
    python scripts/hub_upload/upload2hub.py \\
        --config configs/upload.yaml \\
        --name-space YourUsername

    # With custom database path
    python scripts/hub_upload/upload2hub.py \\
        --config configs/upload.yaml \\
        --db-file-path /path/to/datasets_new.db
"""

import argparse
import getpass
import logging
import sys
from datetime import datetime
from pathlib import Path

from robocoin_dataset.hub_upload.lerobot.hub_upload import (
    upload_datasets,
)
from robocoin_dataset.hub_upload.lerobot.hub_upload_util import (
    create_upload_config,
    load_config_from_yaml,
)


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """
    Set up logging configuration for CLI.

    File: Contains all detailed logs at the specified level
    Console: Only shows critical errors (all task info shown via tqdm.write)

    Args:
        log_level: Logging level for file output (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Logger instance
    """
    # Create logs directory
    log_dir = Path("logs/hub_upload")
    log_dir.mkdir(parents=True, exist_ok=True)

    # Generate timestamped log filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"upload_{timestamp}.log"

    # Configure root logger
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Remove any existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # File handler - detailed logs at specified level
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(getattr(logging, log_level.upper()))
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    root_logger.addHandler(file_handler)

    # Console handler - only CRITICAL errors (task info via tqdm.write)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.CRITICAL)  # Only show critical errors
    console_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    root_logger.addHandler(console_handler)

    # Reduce verbosity of HTTP request logs
    logging.getLogger("httpx").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    # Log to file, print to console using tqdm.write
    logger.info(f"📝 Logging to: {log_file}")
    from tqdm import tqdm
    tqdm.write(f"📝 Logging to: {log_file}")

    return logger


def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Upload RoboCoin datasets to remote hubs (HuggingFace/ModelScope). "
                    "Always generates info YAML and README files before uploading.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic upload (uses default info output path: ./dataset_info)
  python scripts/hub_upload/upload2hub.py --config configs/upload.yaml

  # With custom info output path
  python scripts/hub_upload/upload2hub.py \\
      --config configs/upload.yaml \\
      --info-output-path ./outputs/dataset_infos

  # With authentication token
  python scripts/hub_upload/upload2hub.py \\
      --config configs/upload.yaml \\
      --token YOUR_TOKEN

  # With custom log level
  python scripts/hub_upload/upload2hub.py \\
      --config configs/upload.yaml \\
      --log-level DEBUG

  # Skip datasets with missing files
  python scripts/hub_upload/upload2hub.py \\
      --config configs/upload.yaml \\
      --skip-missing

  # Force overwrite existing repos without prompting
  python scripts/hub_upload/upload2hub.py \\
      --config configs/upload.yaml \\
      --force

  # Override database path
  python scripts/hub_upload/upload2hub.py \\
      --config configs/upload.yaml \\
      --db-file-path /path/to/db.db

  # Specify custom namespace
  python scripts/hub_upload/upload2hub.py \\
      --config configs/upload.yaml \\
      --name-space YourUsername

  # All options combined
  python scripts/hub_upload/upload2hub.py \\
      --config configs/upload.yaml \\
      --info-output-path ./outputs/infos \\
      --token YOUR_TOKEN \\
      --name-space YourUsername \\
      --db-file-path /path/to/db.db \\
      --log-level DEBUG \\
      --skip-missing \\
      --force
        """
    )

    parser.add_argument(
        "--config", "-c",
        type=str,
        required=True,
        help="Path to YAML configuration file"
    )

    parser.add_argument(
        "--token",
        type=str,
        help="Authentication token for the hub platform (if not provided, will prompt)"
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)"
    )

    parser.add_argument(
        "--skip-missing",
        action="store_true",
        help="Skip datasets with missing hardlinks instead of aborting"
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite existing repositories without prompting"
    )

    parser.add_argument(
        "--db-file-path",
        type=str,
        help="Override database file path from config"
    )

    parser.add_argument(
        "--info-output-path",
        type=str,
        default=None,
        help="Output path for generated dataset info files (default: ./dataset_info)"
    )

    parser.add_argument(
        "--name-space",
        type=str,
        help="Namespace (username) on the hub platform where datasets will be uploaded. "
             "If not provided, uses default value from constant.py (DS_PLATFORM_NAME)"
    )

    return parser.parse_args()


def prompt_for_token(hub_name: str, token_from_config: str = "") -> str:
    """
    Prompt user for authentication token.

    Args:
        hub_name: Name of the hub platform
        token_from_config: Token from config file (if any)

    Returns:
        Authentication token
    """
    # Prompt for token
    token = getpass.getpass(f"🔑 {hub_name} token: ").strip()
    if token:
        return token

    # Fall back to config token with confirmation
    if token_from_config and token_from_config.upper() not in ["NULL", "NONE", ""]:
        response = input("⚠️  Use token from config? (y/n): ").strip().lower()
        if response in ["y", "yes"]:
            return token_from_config

    print("❌ No valid token provided")
    sys.exit(1)


def main() -> None:
    """
    Main entry point for the hub upload CLI.
    """
    import time

    from tqdm import tqdm

    # Start timing
    script_start_time = time.time()

    # Parse arguments
    args = parse_arguments()

    # Setup logging
    logger = setup_logging(args.log_level)

    try:
        # Load configuration
        logger.info(f"Loading configuration from: {args.config}")

        config_dict = load_config_from_yaml(args.config)

        # Override config with command line arguments if provided
        if args.skip_missing:
            config_dict["skip_missing"] = True
        if args.force:
            config_dict["force_overwrite"] = True
        if args.db_file_path:
            config_dict["db_file_path"] = args.db_file_path
        if args.name_space:
            config_dict["namespace"] = args.name_space

        # Handle token (from CLI, config, or prompt)
        if args.token:
            config_dict["token"] = args.token
        elif not config_dict.get("token") or config_dict["token"].upper() in ["NULL", "NONE", ""]:
            hub_name = config_dict.get("hub_name", "hub")
            config_dict["token"] = prompt_for_token(hub_name, config_dict.get("token", ""))

        # Create upload config
        config = create_upload_config(config_dict)

        # Validate required fields
        if not config.root_path:
            logger.error("❌ root_path is required in configuration")
            tqdm.write("❌ root_path is required in configuration")
            sys.exit(1)

        # NOTE: Steps 1 & 2 are now performed on-demand during upload
        # Each dataset will have its YAML and README generated right before upload
        # based on the hardlink path from the database
        logger.info("=" * 80)
        logger.info("📝 YAML and README files will be generated on-demand for each dataset")
        logger.info("=" * 80)
        tqdm.write("=" * 80)
        tqdm.write("📝 YAML and README files will be generated on-demand for each dataset")
        tqdm.write("=" * 80)

        # Upload datasets to hub (with on-demand file generation)
        logger.info("=" * 80)
        logger.info("🚀 Starting upload process with on-demand file generation")
        logger.info("=" * 80)
        tqdm.write("🚀 Starting upload process with on-demand file generation")
        tqdm.write("=" * 80)
        upload_datasets(config, logger)

        # Calculate total script execution time
        script_elapsed = time.time() - script_start_time
        hours, remainder = divmod(int(script_elapsed), 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            time_str = f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            time_str = f"{minutes}m {seconds}s"
        else:
            time_str = f"{seconds}s"

        logger.info("=" * 80)
        logger.info(f"✅ Script completed successfully in {time_str}")
        logger.info(f"Total execution time: {script_elapsed:.2f}s")
        logger.info("=" * 80)
        tqdm.write("=" * 80)
        tqdm.write(f"✅ Script completed successfully in {time_str}")
        tqdm.write("=" * 80)

    except FileNotFoundError as e:
        script_elapsed = time.time() - script_start_time
        logger.error(f"❌ File not found: {e} (after {script_elapsed:.2f}s)")
        tqdm.write(f"❌ File not found: {e}")
        sys.exit(1)
    except ValueError as e:
        script_elapsed = time.time() - script_start_time
        logger.error(f"❌ Configuration error: {e} (after {script_elapsed:.2f}s)")
        tqdm.write(f"❌ Configuration error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        script_elapsed = time.time() - script_start_time
        logger.warning(f"\n⚠️  Upload interrupted by user (after {script_elapsed:.2f}s)")
        tqdm.write("\n⚠️  Upload interrupted by user")
        sys.exit(1)
    except Exception as e:
        script_elapsed = time.time() - script_start_time
        logger.error(f"❌ Unexpected error: {e} (after {script_elapsed:.2f}s)", exc_info=True)
        tqdm.write(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
