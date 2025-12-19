"""
简单工具：将指定命名空间下的全部 Hugging Face 数据集加入同一 Collection。

本模块提供了一个核心函数 `add_all_datasets_to_collection`，用于批量将 Hugging Face Hub 上
某个命名空间（namespace/organization）下的所有数据集添加到指定的 Collection 中。

主要功能：
    - 自动列举指定命名空间下的所有数据集
    - 批量将数据集添加到目标 Collection（支持分批处理以避免 API 限制）
    - 提供详细的日志记录以便追踪操作进度

使用场景：
    - 需要将某个组织下的所有数据集统一管理到一个 Collection
    - 批量维护数据集的组织结构
    - 自动化数据集分类和归档

注意事项：
    - 需要提供有效的 Hugging Face 访问令牌（token），且该令牌需要有写入权限
    - 批量大小（batch_size）受 Hugging Face API 限制，最大为 100
    - 操作会跳过重复的数据集（基于数据集 ID 去重）
    - 操作会报出409错误，表示数据集已存在，会跳过。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from huggingface_hub import HfApi, add_collection_item
from huggingface_hub.utils import HfHubHTTPError

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 100


def _chunked(items: list[str], chunk_size: int) -> Iterable[list[str]]:
    """Yield chunks of at most `chunk_size` items."""
    for idx in range(0, len(items), chunk_size):
        yield items[idx : idx + chunk_size]


def add_all_datasets_to_collection(
    token: str,
    namespace: str,
    collection_slug: str,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """
    Add every dataset under `namespace` into `collection_slug`.

    Args:
        token: Hugging Face token with write permission.
        namespace: Target namespace/organization on the Hub.
        collection_slug: Target collection slug (e.g. "org/my-collection").
        batch_size: Max number of datasets per API call (<=100 per HF API).

    Returns:
        Number of datasets processed (total count, regardless of success/failure).
        Detailed logging shows individual outcomes for each dataset.
    """
    if not token:
        raise ValueError("token is required")
    if not namespace:
        raise ValueError("namespace is required")
    if not collection_slug:
        raise ValueError("collection is required")
    if batch_size <= 0 or batch_size > 100:
        raise ValueError("batch_size must be between 1 and 100 (HF API limit)")

    api = HfApi(token=token)
    logger.info("Listing all datasets under namespace %s...", namespace)
    datasets = api.list_datasets(author=namespace, limit=10_000)
    repo_ids = list(dict.fromkeys(repo.id for repo in datasets))

    if not repo_ids:
        logger.info("No datasets found under namespace %s, skipping collection update.", namespace)
        return 0

    logger.info("Preparing to add %d datasets to collection %s.", len(repo_ids), collection_slug)
    processed = 0
    added = 0
    skipped = 0
    failed = 0

    for chunk in _chunked(repo_ids, batch_size):
        for repo_id in chunk:
            logger.info("[START] %s", repo_id)
            try:
                add_collection_item(
                    collection_slug=collection_slug,
                    item_id=repo_id,
                    item_type="dataset",
                    token=token,
                    exists_ok=True  # Skip if already in collection
                )
                logger.info("[SUCCESS] %s", repo_id)
                added += 1
            except HfHubHTTPError as e:
                if e.response.status_code == 409:
                    logger.info("[SKIP] Dataset already exists in collection: %s", repo_id)
                    skipped += 1
                else:
                    logger.error("[FAILED] %s: %s", repo_id, str(e))
                    failed += 1
            except Exception as e:
                logger.error("[ERROR] %s: %s", repo_id, str(e))
                failed += 1

        processed += len(chunk)
        logger.debug("Processed %d/%d datasets (Added: %d, Skipped: %d, Failed: %d).",
                    processed, len(repo_ids), added, skipped, failed)

    logger.info("Collection update completed. Total processed: %d, Added: %d, Skipped: %d, Failed: %d",
                processed, added, skipped, failed)
    return processed
