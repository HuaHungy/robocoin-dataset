"""Standalone dataloader detection CLI without database or task manager.

This script mirrors the logging UX of `dataloader_detect.py`, but it only
accepts the minimum required parameters plus a dataset directory. It performs
an on-demand dataloader load test against the given folder and skips all
database coordination and distributed execution concerns.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from robocoin_dataset.dataloader.dataloader_utils import _run_detection
from robocoin_dataset.utils.logger import setup_logger


def _create_log_dir_name(args: argparse.Namespace) -> str:
    """Create log directory name with key parameters."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dataset_name = args.dataset_path.name.replace(" ", "_")

    parts = [timestamp, f"manual_{dataset_name}"]

    if args.num_workers > 0:
        parts.append(f"w{args.num_workers}")

    if args.sample_ratio != 1.0:
        parts.append(f"sr{args.sample_ratio:.2f}")

    if args.batch_size != 32:
        parts.append(f"bs{args.batch_size}")

    if args.episodes != "all":
        ep_str = args.episodes.replace(",", "_").replace("-", "to")[:20]
        parts.append(f"ep{ep_str}")

    return "_".join(parts)


def _log_detection_parameters(dataset_path: Path, args: argparse.Namespace, sum_logger: logging.Logger) -> None:
    """Log the parameters used for the detection run."""
    sum_logger.info("=" * 80)
    sum_logger.info(f"Manual detection started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    sum_logger.info("Detection Parameters:")
    sum_logger.info(f"  dataset-path={dataset_path}")
    sum_logger.info(f"  episodes={args.episodes}")
    sum_logger.info(f"  sample-ratio={args.sample_ratio}")
    sum_logger.info(f"  batch-size={args.batch_size}")
    sum_logger.info(f"  num-workers={args.num_workers}")
    sum_logger.info("=" * 80)


def _print_detection_summary(result: dict, logger: logging.Logger, sum_logger: logging.Logger) -> int:
    """Log formatted summary of detection result."""
    dataset_path = result.get("dataset_path", "<unknown>")
    if result.get("success"):
        total_frames = result.get("total_frames_sampled", 0)
        total_time = result.get("total_time_s", 0.0)
        time_per_frame = result.get("time_per_frame_s", 0.0)
        episodes = result.get("episodes_tested", [])

        summary_lines = [
            "",
            f"✅ Detection succeeded for {dataset_path}",
            f"   Episodes tested: {episodes}",
            f"   Total frames: {total_frames}",
            f"   Total time: {total_time:.2f}s",
            f"   Avg time/frame: {time_per_frame * 1000:.1f}ms",
        ]
        formatted = "\n".join(summary_lines)
        logger.info(formatted)
        sum_logger.info(formatted)
        return 0

    error_message = result.get("error_message", "Unknown error")
    summary_lines = [
        "",
        f"❌ Detection failed for {dataset_path}",
        f"   Reason: {error_message}",
    ]
    formatted = "\n".join(summary_lines)
    logger.error(formatted)
    sum_logger.error(formatted)
    return 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a manual dataloader load test for a single dataset folder.",
    )
    parser.add_argument(
        "dataset_path",
        type=Path,
        help="Path to the dataset directory (LeRobot format).",
    )
    parser.add_argument(
        "--episodes",
        type=str,
        default="all",
        help='Episodes to test: "all" (default), "0", "0,1,2", or "0-5".',
    )
    parser.add_argument(
        "--sample-ratio",
        type=float,
        default=1.0,
        help="Sample ratio for detection (0.0-1.0, default: 1.0).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size for dataloader (default: 32).",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=0,
        help="Number of dataloader workers (default: 0).",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level for console and file output.",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("logs/dataloader"),
        help="Base log directory (default: logs/dataloader).",
    )

    return parser.parse_args(argv)


def _validate_dataset_path(dataset_path: Path, logger: logging.Logger) -> Path:
    """Ensure the dataset path exists and is a directory."""
    resolved = dataset_path.expanduser().absolute()

    if not resolved.exists():
        logger.error(f"❌ Dataset path not found: {resolved}")
        raise SystemExit(2)
    if not resolved.is_dir():
        logger.error(f"❌ Dataset path is not a directory: {resolved}")
        raise SystemExit(2)

    return resolved


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    log_dir_name = _create_log_dir_name(args)
    log_base_dir = args.log_dir.expanduser().absolute() / log_dir_name
    log_base_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logger(
        name="dataloader_manual",
        log_dir=log_base_dir,
        level=getattr(logging, args.log_level, logging.INFO),
        console_output=True,
    )

    sum_logger = setup_logger(
        name="dataloader_manual_summary",
        log_dir=log_base_dir,
        level=logging.INFO,
        console_output=True,
    )

    dataset_path = _validate_dataset_path(args.dataset_path, logger)
    _log_detection_parameters(dataset_path, args, sum_logger)

    result = _run_detection(
        repo_path=dataset_path,
        episode_indices=args.episodes,
        sample_ratio=args.sample_ratio,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        logger=logger,
    )

    return _print_detection_summary(result, logger, sum_logger)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
