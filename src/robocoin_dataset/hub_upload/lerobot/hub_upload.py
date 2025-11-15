"""
RoboCoin Datasets Hub Upload - Business Logic Functions

This module provides reusable business logic functions for:
- Generating dataset info YAML files from metadata
- Generating README.md files from templates
- Uploading datasets to remote hubs (HuggingFace or ModelScope)

These functions can be imported and used by CLI scripts or other modules.

Example:
    from robocoin_dataset.hub_upload.lerobot.hub_upload import (
        generate_dataset_info,
        generate_dataset_readmes,
        upload_datasets,
    )
"""

import logging

from robocoin_dataset.readmes.dataset_readme_util import LocalDsReadmeConfig, LocalDsReadmeUtil

from .dataset_info_util import LocalDsInfoConfig, LocalDsInfoUtil
from .hub_upload_util import LocalDsUploadConfig, LocalDsUploadUtil


def generate_dataset_info(
    root_path: str,
    output_path: str | None = None,
    logger: logging.Logger | None = None
) -> str:
    """
    Generate dataset info YAML files for all datasets.

    All information is extracted from the dataset metadata (meta/info.json, meta/tasks.jsonl, etc.)
    in the dataset directories.

    Args:
        root_path: Root path containing dataset directories
        output_path: Output path for generated info files. If None, defaults to "./dataset_info"
        logger: Logger instance (optional)

    Returns:
        str: The output path used (resolved to default if None was passed)
    """
    _logger = logger or logging.getLogger(__name__)

    # Set default output path if not provided
    if output_path is None:
        output_path = "./dataset_info"
        _logger.debug(f"Using default info output path: {output_path}")

    try:
        _logger.debug(f"📝 Generating dataset info YAML files to: {output_path}")

        # Create info generator config (no task_tags_yamls_dir needed)
        info_config = LocalDsInfoConfig(
            root_path=root_path,
            output_path=output_path,
            task_tags_yamls_dir=""  # Not used - all info from dataset metadata
        )

        # Generate info files
        info_generator = LocalDsInfoUtil(info_config)
        info_generator.generate_infos()

        _logger.info("✅ Dataset info files generated successfully")

        return output_path

    except Exception as e:
        _logger.error(f"❌ Failed to generate dataset info files: {e}", exc_info=True)
        raise


def generate_dataset_readmes(
    root_path: str,
    dataset_info_root_path: str | None = None,
    logger: logging.Logger | None = None
) -> None:
    """
    Generate README.md files for all datasets.

    Args:
        root_path: Root path containing dataset directories
        dataset_info_root_path: Path containing dataset info YAML files. If None, defaults to "./dataset_info"
        logger: Logger instance (optional)
    """
    _logger = logger or logging.getLogger(__name__)

    # Set default dataset info path if not provided
    if dataset_info_root_path is None:
        dataset_info_root_path = "./dataset_info"
        _logger.debug(f"Using default dataset info path: {dataset_info_root_path}")

    try:
        _logger.debug(f"📝 Generating dataset README files from: {dataset_info_root_path}")

        # Create readme generator config
        readme_config = LocalDsReadmeConfig(
            root_path=root_path,
            dataset_info_root_path=dataset_info_root_path
        )

        # Generate readme files
        readme_generator = LocalDsReadmeUtil(readme_config)
        readme_generator.generate_readmes()

        _logger.info("✅ Dataset README files generated successfully")

    except Exception as e:
        _logger.error(f"❌ Failed to generate dataset README files: {e}", exc_info=True)
        raise


def upload_datasets_main(config: LocalDsUploadConfig, logger: logging.Logger | None = None) -> None:
    """
    Upload datasets to remote hub using database management.

    This is the main business logic function that orchestrates the upload process.

    Args:
        config: Upload configuration
        logger: Logger instance (optional)
    """
    from tqdm import tqdm

    _logger = logger or logging.getLogger(__name__)

    try:
        # Initialize uploader
        _logger.debug("Initializing uploader...")
        uploader = LocalDsUploadUtil(config)

        # Start upload process
        _logger.info("Starting upload process...")
        uploader._upload_datasets_from_database()

        _logger.info("✅ Upload process completed successfully")
        tqdm.write("\n✅ Upload process completed successfully")

    except KeyboardInterrupt:
        _logger.warning("\n⚠️  Upload interrupted by user")
        tqdm.write("\n⚠️  Upload interrupted by user")
        raise
    except Exception as e:
        _logger.error(f"❌ Upload failed: {e}", exc_info=True)
        tqdm.write(f"\n❌ Upload failed: {e}")
        raise
