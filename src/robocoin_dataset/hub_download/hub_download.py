#!/usr/bin/env python3
"""
Simple and reliable script to download datasets from HuggingFace or ModelScope hub.

Usage:
    python hub_download.py --hub modelscope --ds_lists dataset1 dataset2 dataset3
    python hub_download.py --hub huggingface --ds_lists dataset1 dataset2
    python hub_download.py --hub modelscope --ds_lists dataset1 --namespace your_namespace
    python hub_download.py --hub huggingface --ds_lists dataset1 --output_dir ./downloads
"""

import argparse
import logging
import os
import sys
import time
import warnings
from pathlib import Path
from typing import Literal

warnings.filterwarnings("ignore", message="pkg_resources is deprecated as an API")
warnings.filterwarnings("ignore", message=".*resume_download.*deprecated.*")
warnings.filterwarnings("ignore", message=".*local_dir_use_symlinks.*deprecated.*")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Reduce verbosity of external libraries
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
logging.getLogger("modelscope").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


def download_from_huggingface(
    dataset_name: str,
    output_dir: Path,
    namespace: str | None = None,
    token: str | None = None,
    max_workers: int = 1,
    max_retries: int = 5
) -> Path:
    """
    Download a dataset from Hugging Face Hub with rate limit handling.

    Args:
        dataset_name: Name of the dataset to download
        output_dir: Directory to save the downloaded dataset
        namespace: Optional namespace/username (defaults to 'robocoin-dataset')
        token: Optional authentication token
        max_workers: Maximum number of concurrent download threads (default: 1 to avoid rate limits)
        max_retries: Maximum number of retry attempts for rate limit errors (default: 5)

    Returns:
        Path to the downloaded dataset directory

    Raises:
        Exception: If download fails after all retries
    """
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        logger.error("huggingface_hub is not installed. Please install it: pip install huggingface_hub")
        raise

    # Construct repo_id
    namespace = namespace or "robocoin-dataset"
    repo_id = f"{namespace}/{dataset_name}"

    logger.info(f"Downloading from HuggingFace: {repo_id} (max_workers={max_workers})")

    # Determine download path
    dataset_path = output_dir / dataset_name

    # Retry loop for handling rate limits
    last_exception = None
    for attempt in range(max_retries):
        try:
            # Download the entire repository with reduced parallelism
            downloaded_path = snapshot_download(
                repo_id=repo_id,
                repo_type="dataset",
                local_dir=str(dataset_path),
                local_dir_use_symlinks=False,  # Create actual files instead of symlinks
                token=token,
                resume_download=True,  # Support resuming interrupted downloads
                max_workers=max_workers,  # Limit concurrent requests to avoid rate limits
            )

            logger.info(f"✓ Successfully downloaded {repo_id} to {downloaded_path}")
            return Path(downloaded_path)

        except Exception as e:  # noqa: PERF203  # Intentional: retry logic requires exception handling in loop
            last_exception = e
            error_msg = str(e)

            # Check if this is a rate limit error (429)
            is_rate_limit = (
                "429" in error_msg or
                "Too Many Requests" in error_msg or
                "rate limit" in error_msg.lower()
            )

            if is_rate_limit and attempt < max_retries - 1:
                # Calculate exponential backoff with jitter
                wait_time = min(300, (2 ** attempt) * 30)  # Max 5 minutes
                logger.warning(
                    f"⚠ Rate limit hit for {repo_id}. "
                    f"Waiting {wait_time}s before retry {attempt + 1}/{max_retries - 1}..."
                )
                time.sleep(wait_time)
                continue
            # Not a rate limit error, or out of retries
            logger.error(f"❌ Failed to download {repo_id}: {e}")
            raise

    # Should not reach here, but just in case
    if last_exception:
        raise last_exception
    raise Exception(f"Failed to download {repo_id} after {max_retries} attempts")


def download_from_modelscope(
    dataset_name: str,
    output_dir: Path,
    namespace: str | None = None,
    token: str | None = None
) -> Path:
    """
    Download a dataset from ModelScope Hub.

    Args:
        dataset_name: Name of the dataset to download
        output_dir: Directory to save the downloaded dataset
        namespace: Optional namespace/username (defaults to 'robocoin-dataset')
        token: Optional authentication token

    Returns:
        Path to the downloaded dataset directory

    Raises:
        Exception: If download fails
    """
    try:
        from modelscope.hub.api import HubApi
        from modelscope.hub.snapshot_download import snapshot_download
    except ImportError:
        logger.error("modelscope is not installed. Please install it: pip install modelscope")
        raise

    # Construct repo_id
    namespace = namespace or "robocoin-dataset"
    repo_id = f"{namespace}/{dataset_name}"

    logger.debug(f"Downloading from ModelScope: {repo_id}")

    # Determine download path
    dataset_path = output_dir / dataset_name

    try:
        # Initialize HubApi with token if provided
        if token:
            hub_api = HubApi()
            hub_api.login(token)

        # Download the entire repository
        downloaded_path = snapshot_download(
            model_id=repo_id,
            cache_dir=str(output_dir),
            local_dir=str(dataset_path),
            local_dir_use_symlinks=False,  # Create actual files instead of symlinks
        )

        logger.debug(f"Successfully downloaded {repo_id} to {downloaded_path}")
        return Path(downloaded_path)

    except Exception as e:
        logger.error(f"❌ Failed to download {repo_id}: {e}")
        raise


def download_dataset(
    hub: Literal["huggingface", "modelscope"],
    dataset_name: str,
    output_dir: Path,
    namespace: str | None = None,
    token: str | None = None,
    max_workers: int = 1,
    max_retries: int = 5
) -> Path:
    """
    Download a dataset from the specified hub.

    Args:
        hub: Which hub to download from ('huggingface' or 'modelscope')
        dataset_name: Name of the dataset to download
        output_dir: Directory to save the downloaded dataset
        namespace: Optional namespace/username
        token: Optional authentication token
        max_workers: Maximum number of concurrent download threads (default: 1)
        max_retries: Maximum number of retry attempts for rate limit errors (default: 5)

    Returns:
        Path to the downloaded dataset directory

    Raises:
        ValueError: If hub is not supported
        Exception: If download fails
    """
    if hub == "huggingface":
        return download_from_huggingface(
            dataset_name, output_dir, namespace, token, max_workers, max_retries
        )
    if hub == "modelscope":
        return download_from_modelscope(dataset_name, output_dir, namespace, token)
    raise ValueError(f"Unsupported hub: {hub}. Must be 'huggingface' or 'modelscope'")


def main() -> int:
    """
    Main entry point for the download script.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    parser = argparse.ArgumentParser(
        description="Download datasets from HuggingFace or ModelScope hub",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download from ModelScope
  python hub_download.py --hub modelscope --ds_lists galaxea_r1_lite_build_blocks

  # Download multiple datasets from HuggingFace (with rate limit protection)
  python hub_download.py --hub huggingface --ds_lists dataset1 dataset2 dataset3

  # Download with custom namespace and output directory
  python hub_download.py --hub modelscope --namespace my_org --ds_lists dataset1 --output_dir ./my_downloads

  # Download with authentication token
  python hub_download.py --hub huggingface --ds_lists private_dataset --token YOUR_TOKEN

  # Download with increased parallelism (may trigger rate limits)
  python hub_download.py --hub huggingface --ds_lists dataset1 --max_workers 4

  # Download with custom retry settings
  python hub_download.py --hub huggingface --ds_lists dataset1 --max_retries 10

Note: The default max_workers=1 avoids rate limits. Increase at your own risk.
        """
    )

    parser.add_argument(
        "--hub",
        type=str,
        required=True,
        choices=["huggingface", "modelscope"],
        help="Which hub to download from (huggingface or modelscope)"
    )

    parser.add_argument(
        "--ds_lists",
        type=str,
        nargs="+",
        required=True,
        help="List of dataset names to download"
    )

    parser.add_argument(
        "--namespace",
        type=str,
        default=None,
        help="Namespace/username on the hub platform (default: 'robocoin-dataset')"
    )

    parser.add_argument(
        "--output_dir",
        type=str,
        default=".",
        help="Output directory to save datasets (default: current directory)"
    )

    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="Authentication token for the hub (optional, can also use HF_TOKEN or MODELSCOPE_TOKEN env vars)"
    )

    parser.add_argument(
        "--max_workers",
        type=int,
        default=1,
        help="Maximum number of concurrent download threads (default: 1, use higher values at risk of rate limits)"
    )

    parser.add_argument(
        "--max_retries",
        type=int,
        default=5,
        help="Maximum number of retry attempts for rate limit errors (default: 5)"
    )

    args = parser.parse_args()

    # Setup output directory
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get token from args or environment variables
    token = args.token
    if not token:
        if args.hub == "huggingface":
            token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        elif args.hub == "modelscope":
            token = os.environ.get("MODELSCOPE_TOKEN") or os.environ.get("MODELSCOPE_API_TOKEN")

    # Log configuration
    logger.info("=" * 80)
    logger.info(f"Starting download from {args.hub.upper()}")
    logger.info(f"Downloading {len(args.ds_lists)} dataset(s) to: {output_dir}")
    logger.info(f"  Hub: {args.hub}")
    logger.info(f"  Namespace: {args.namespace or 'robocoin-dataset (default)'}")
    logger.info(f"  Datasets: {', '.join(args.ds_lists)}")
    logger.info(f"  Max workers: {args.max_workers} (concurrent downloads)")
    logger.info(f"  Max retries: {args.max_retries} (for rate limit errors)")
    logger.info(f"  Token: {'Provided' if token else 'Not provided (public access only)'}")
    logger.info("=" * 80)

    # Download each dataset
    success_count = 0
    failed_datasets = []

    for i, dataset_name in enumerate(args.ds_lists, 1):
        logger.info(f"[{i}/{len(args.ds_lists)}] Downloading: {dataset_name}")

        try:
            download_dataset(
                hub=args.hub,
                dataset_name=dataset_name,
                output_dir=output_dir,
                namespace=args.namespace,
                token=token,
                max_workers=args.max_workers,
                max_retries=args.max_retries
            )
            success_count += 1
            logger.info(f"✓ [{i}/{len(args.ds_lists)}] Completed: {dataset_name}")

        except Exception as e:
            logger.error(f"✗ [{i}/{len(args.ds_lists)}] Failed: {dataset_name}")
            logger.error(f"  Error: {str(e)}")
            failed_datasets.append(dataset_name)
            # Continue with next dataset instead of stopping
            continue

    # Print summary
    logger.info("=" * 80)
    logger.info(f"Summary: {success_count}/{len(args.ds_lists)} downloaded successfully")

    if failed_datasets:
        logger.warning(f"Failed datasets: {', '.join(failed_datasets)}")
        logger.info("=" * 80)
        return 1
    logger.info("All datasets downloaded successfully! 🎉")
    logger.info("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
