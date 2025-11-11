"""
RoboCoin Datasets Hub Upload - CLI Entry Point

This module provides the command-line interface for uploading RoboCoin datasets
to remote hubs (HuggingFace or ModelScope).

Usage:
    python -m robocoin_dataset.hub_upload.lerobot.hub_upload --config configs/upload.yaml
"""

import argparse
import logging
import sys

from .hub_upload_util import (
    create_upload_config,
    load_config_from_yaml,
    upload_datasets,
)


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """
    Set up logging configuration for CLI.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Logger instance
    """
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger(__name__)


def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Upload RoboCoin datasets to remote hubs (HuggingFace/ModelScope)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload using config file
  python -m robocoin_dataset.hub_upload.lerobot.hub_upload --config configs/upload.yaml

  # Upload with custom log level
  python -m robocoin_dataset.hub_upload.lerobot.hub_upload --config configs/upload.yaml --log-level DEBUG

  # Override skip_missing from command line
  python -m robocoin_dataset.hub_upload.lerobot.hub_upload --config configs/upload.yaml --skip-missing

  # Override database path
  python -m robocoin_dataset.hub_upload.lerobot.hub_upload --config configs/upload.yaml --db-file-path /path/to/db.db
        """
    )

    parser.add_argument(
        "--config", "-c",
        type=str,
        required=True,
        help="Path to YAML configuration file"
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
        "--db-file-path",
        type=str,
        help="Override database file path from config"
    )

    return parser.parse_args()


def main() -> None:
    """
    Main entry point for the hub upload CLI.
    """
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
        if args.db_file_path:
            config_dict["db_file_path"] = args.db_file_path

        # Create upload config
        config = create_upload_config(config_dict)

        # Validate required fields
        if not config.root_path:
            logger.error("❌ root_path is required in configuration")
            sys.exit(1)

        # Run upload
        upload_datasets(config, logger)

    except FileNotFoundError as e:
        logger.error(f"❌ File not found: {e}")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"❌ Configuration error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("\n⚠️  Upload interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
