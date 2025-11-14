#!/usr/bin/env python3
"""
Helpers that implement resilient dataset downloads for HuggingFace and ModelScope.

The functions defined here are intentionally free of CLI / argparse so they can be
reused from multiple entry points (e.g. automation, tests, or convenience scripts).
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Literal

DEFAULT_NAMESPACE = "robocoin-dataset"
DEFAULT_MAX_RETRIES = 5
# Backwards compatibility: some callers may still reference the legacy constant name.
DEFAULT_MAX_RETRY_TIME = DEFAULT_MAX_RETRIES
DEFAULT_SLEEP_SECONDS = 5
MAX_SLEEP_SECONDS = 120

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
LOGGER = logging.getLogger("hub-download")


# --------------------------------------------------------------------------- #
# Public helpers
# --------------------------------------------------------------------------- #
def _read_dataset_names(cli_values: Iterable[str] | None, file_path: str | None) -> list[str]:
    names: list[str] = []

    if cli_values:
        names.extend(cli_values)

    if file_path:
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Dataset list not found: {path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            item = line.strip()
            if item and not item.startswith("#"):
                names.append(item)

    ordered_unique: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name not in seen:
            ordered_unique.append(name)
            seen.add(name)
    return ordered_unique


def _retry_loop(label: str, max_retries: int, fn: Callable[[], Path]) -> Path:
    sleep_time = DEFAULT_SLEEP_SECONDS
    last_exc: Exception | None = None

    for attempt in range(1, max(1, max_retries) + 1):
        try:
            LOGGER.info(f"{label}: attempt {attempt}")
            return fn()
        except Exception as exc:  # noqa: PERF203
            last_exc = exc
            remaining_attempts = max_retries - attempt
            if remaining_attempts <= 0:
                break
            wait = sleep_time
            LOGGER.warning(
                "%s: failed (%s); retrying in %ds (%d attempt(s) left)",
                label,
                exc,
                int(wait),
                remaining_attempts,
            )
            time.sleep(wait)
            sleep_time = min(sleep_time * 2, MAX_SLEEP_SECONDS)

    raise RuntimeError(f"{label}: download timeout after {max_retries} attempt(s)") from last_exc


def _resolve_token(hub: Literal["huggingface", "modelscope"], explicit: str | None) -> str | None:
    if explicit:
        return explicit
    if hub == "huggingface":
        return os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    return os.environ.get("MODELSCOPE_TOKEN") or os.environ.get("MODELSCOPE_API_TOKEN")


# --------------------------------------------------------------------------- #
# Hub specific downloaders
# --------------------------------------------------------------------------- #
def _download_from_hf(repo_id: str, target_dir: Path, token: str | None, max_workers: int) -> Path:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:  # pragma: no cover - dependency error
        raise RuntimeError("huggingface_hub is missing: pip install huggingface_hub") from exc

    def _run() -> Path:
        path = snapshot_download(
            repo_id=repo_id,
            repo_type="dataset",
            local_dir=str(target_dir),
            token=token,
            resume_download=True,
            max_workers=max_workers,
        )
        return Path(path)

    return _run()


def _download_from_modelscope(repo_id: str, target_dir: Path, token: str | None) -> Path:
    try:
        from modelscope.hub.api import HubApi
    except ImportError as exc:  # pragma: no cover - dependency error
        raise RuntimeError("modelscope is missing: pip install modelscope") from exc

    def _run() -> Path:
        if token:
            HubApi().login(token)
        # MsDataset.load returns a dataset object; the actual files are in cache_dir
        return target_dir

    return _run()


def download_dataset(
    hub: Literal["huggingface", "modelscope"],
    dataset_name: str,
    output_dir: Path,
    namespace: str | None,
    token: str | None,
    max_workers: int,
    max_retries: int,
) -> Path:
    namespace = namespace or DEFAULT_NAMESPACE
    repo_id = f"{namespace}/{dataset_name}"
    dataset_path = output_dir / dataset_name
    dataset_path.mkdir(parents=True, exist_ok=True)

    def _perform_download() -> Path:
        if hub == "huggingface":
            return _download_from_hf(repo_id, dataset_path, token, max_workers)
        if hub == "modelscope":
            return _download_from_modelscope(repo_id, dataset_path, token)
        raise ValueError(f"Unsupported hub: {hub}")

    return _retry_loop(f"{hub}:{repo_id}", max_retries, _perform_download)


def download_datasets(
    hub: Literal["huggingface", "modelscope"],
    dataset_names: Iterable[str],
    output_dir: Path | str,
    namespace: str | None = None,
    token: str | None = None,
    max_workers: int = 1,
    max_retries: int = DEFAULT_MAX_RETRY_TIME,
) -> list[str]:
    """
    Download multiple datasets, returning a list of failures (if any).

    Args:
        hub: Target hub name.
        dataset_names: Iterable of dataset identifiers (unique entries recommended).
        output_dir: Directory where dataset folders will be stored.
        namespace: Optional namespace override.
        token: Optional authentication token, falling back to env vars when None.
        max_workers: Parallel worker hint for HuggingFace.
        max_retries: Maximum attempts per dataset (including the first try).
    """
    datasets = list(dataset_names)
    if not datasets:
        raise ValueError("No datasets provided.")

    out_dir = Path(output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    resolved_token = _resolve_token(hub, token)

    LOGGER.info("Hub: %s", hub)
    LOGGER.info("Namespace: %s", namespace or DEFAULT_NAMESPACE)
    LOGGER.info("Output: %s", out_dir)
    LOGGER.info("Datasets: %s", ", ".join(datasets))
    LOGGER.info("Retry budget: %d attempt(s) per dataset", int(max_retries))
    LOGGER.info("Token: %s", "provided" if resolved_token else "not provided")

    failures: list[str] = []
    for idx, name in enumerate(datasets, 1):
        LOGGER.info("[%d/%d] %s", idx, len(datasets), name)
        try:
            path = download_dataset(
                hub=hub,
                dataset_name=name,
                output_dir=out_dir,
                namespace=namespace,
                token=resolved_token,
                max_workers=max(1, max_workers),
                max_retries=int(max_retries),
            )
            LOGGER.info("Completed: %s --> %s", name, path)
        except Exception as exc:  # noqa: PERF203
            LOGGER.error("Failed: %s (%s)", name, exc)
            failures.append(name)

    if failures:
        LOGGER.error("Failed datasets: %s", ", ".join(failures))
    else:
        LOGGER.info("All datasets downloaded successfully.")

    return failures
