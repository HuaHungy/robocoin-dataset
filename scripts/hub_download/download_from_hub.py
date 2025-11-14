#!/usr/bin/env python3
"""
Primary CLI for the hub download helper.

This script owns argparse handling and executes the reusable download helpers from
`src/robocoin_dataset/hub_download/hub_download.py`.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from robocoin_dataset.hub_download.hub_download import (
    DEFAULT_MAX_RETRY_TIME,
    DEFAULT_NAMESPACE,
    LOGGER,
    _read_dataset_names,
    download_datasets,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download datasets from HuggingFace or ModelScope.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--hub", required=True, choices=["huggingface", "modelscope"])
    parser.add_argument("--ds_lists", nargs="+", help="Dataset names provided on the CLI.")
    parser.add_argument("--ds_file", help="Optional text file with one dataset per line.")
    parser.add_argument("--namespace", help="Hub namespace/owner.", default=None)
    parser.add_argument(
        "--output_dir",
        "--target-dir",
        dest="output_dir",
        default=".",
        help="Where datasets should be stored.",
    )
    parser.add_argument("--token", help="Authentication token (else env vars are used).")
    parser.add_argument("--max_workers", type=int, default=1, help="Only used for HuggingFace downloads.")
    parser.add_argument("--max_retry_time", type=int, default=DEFAULT_MAX_RETRY_TIME, help="Maximum retries per dataset.")
    parser.add_argument("--dry_run", action="store_true", help="Print plan and exit.")
    return parser


def _resolve_output_dir(path: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        dataset_names = _read_dataset_names(args.ds_lists, args.ds_file)
    except FileNotFoundError as exc:
        parser.error(str(exc))

    if not dataset_names:
        parser.error("No datasets supplied. Use --ds_lists and/or --ds_file.")

    output_dir = _resolve_output_dir(args.output_dir)

    if args.dry_run:
        LOGGER.info("Dry run")
        LOGGER.info("  Hub: %s", args.hub)
        LOGGER.info("  Namespace: %s", args.namespace or DEFAULT_NAMESPACE)
        LOGGER.info("  Output: %s", output_dir)
        LOGGER.info("  Datasets (%d): %s", len(dataset_names), ", ".join(dataset_names))
        LOGGER.info("  Max retries: %d", args.max_retry_time)
        LOGGER.info("  Token: %s", "provided" if args.token else "not provided")
        return 0

    failures = download_datasets(
        hub=args.hub,
        dataset_names=dataset_names,
        output_dir=output_dir,
        namespace=args.namespace,
        token=args.token,
        max_workers=max(1, args.max_workers),
        max_retries=int(args.max_retry_time),
    )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
