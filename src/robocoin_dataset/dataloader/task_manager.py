"""Task management for dataloader detection.

This module handles database operations for managing dataloader detection tasks:
- Syncing and queuing tasks
- Claiming tasks for processing
- Parsing episode specifications
"""

import logging
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import and_, or_

from robocoin_dataset.database.models import DatasetDB, TaskStatus

# =============================
# Task category for DB-backed dataloader detection
# =============================
TASK_CATEGORY = "dataloader_detection"

# =============================
# Default DB path
# =============================
try:
    _here = Path(__file__).resolve()
    _repo_root = _here.parents[3]
    DEFAULT_DB_FILE = (
        (_repo_root / "examples" / "dataloader_test" / "datasets_new.db").expanduser().absolute()
    )
except Exception:
    DEFAULT_DB_FILE = Path("examples/dataloader_test/datasets_new.db").expanduser().absolute()


def _sync_dataloader_detection_tasks(
    session: Session,
    logger: logging.Logger | None = None,
) -> None:
    """Mark datasets requiring dataloader detection as pending and align versions.

    ##############################################################################
    # HERE : version_ps = data_merge_version   version ++                        #
    ##############################################################################

    Trigger rules (STRICT REQUIREMENTS):
      - data_merge_status must be COMPLETED
      - convert_status must be COMPLETED
      - data_loader_detection_status is NULL (never tested), PENDING, or COMPLETED but outdated

    WARNING: NULL data_loader_detection_status is ILLEGAL but handled for robustness.
    """
    _logger = logger or logging.getLogger(__name__)

    query = session.query(DatasetDB).filter(
        and_(
            DatasetDB.data_merge_status == TaskStatus.COMPLETED,
            or_(
                # NEW: Match records that have never been tested (NULL status)
                DatasetDB.data_loader_detection_status == None,  # noqa: E711
                # Match records explicitly marked as PENDING
                DatasetDB.data_loader_detection_status == TaskStatus.PENDING,
                # Match records that were COMPLETED but are now outdated
                and_(
                    DatasetDB.data_loader_detection_status == TaskStatus.COMPLETED,
                    DatasetDB.data_loader_detection_version_ps < DatasetDB.data_merge_version,
                    # FIXED: dlder_ps < data_merge_version not dlder_ps < convert_version.
                ),
            ),
        )
    )

    items = query.all()
    if not items:
        return

    # Separate NULL status records and warn about them
    null_status_items = []
    valid_items = []

    for item in items:
        if item.data_loader_detection_status is None:
            null_status_items.append(item)
        else:
            valid_items.append(item)

        item.data_loader_detection_status = TaskStatus.PENDING
        item.data_loader_detection_version_ps = item.data_merge_version
        item.data_loader_detection_version = (item.data_loader_detection_version or 0) + 1

    # Log warnings for NULL status records
    if null_status_items:
        _logger.warning(
            f"⚠️  Found {len(null_status_items)} dataset(s) with NULL data_loader_detection_status. "
            f"This is ILLEGAL - status should be initialized. Treating as PENDING for robustness."
        )
        for item in null_status_items:
            _logger.warning(
                f"   ⚠️  Dataset {item.dataset_uuid} has NULL data_loader_detection_status "
                f"(convert_path: {item.convert_path})"
            )

    if valid_items:
        _logger.info(f"Marked {len(valid_items)} dataset(s) as PENDING for dataloader detection")

    session.commit()


def _gen_one_dataloader_detection_task(session: Session) -> tuple[str | None, str | None]:
    """Claim one pending dataset and transition it to PROCESSING.

    Returns (dataset_uuid, convert_path) or (None, None) if no task available.
    """
    item = (
        session.query(DatasetDB)
        .filter(DatasetDB.data_merge_status == TaskStatus.COMPLETED)
        .filter(DatasetDB.data_loader_detection_status == TaskStatus.PENDING)
        .first()
    )
    if not item:
        return None, None

    item.data_loader_detection_status = TaskStatus.PROCESSING
    session.commit()
    return item.dataset_uuid, item.convert_path


def _parse_episode_specification(
    episode_spec: str | int | list[int] | None,
    total_episodes: int,
) -> list[int]:
    """Parse episode specification into list of episode indices.

    Args:
        episode_spec: Episode specification in various formats:
            - None or "all": all episodes [0, 1, ..., total_episodes-1]
            - int: single episode (e.g., 0)
            - list[int]: specific episodes (e.g., [0, 1, 2])
            - str "0": single episode 0
            - str "0,1,2": comma-separated episodes
            - str "0-5": range (inclusive) [0, 1, 2, 3, 4, 5]
            - str "0-5,10,15-17": mixed notation
        total_episodes: Total number of episodes in dataset

    Returns:
        Sorted list of unique episode indices

    Raises:
        ValueError: If specification is invalid or episodes out of range
    """
    if episode_spec is None or (isinstance(episode_spec, str) and episode_spec.lower() == "all"):
        return list(range(total_episodes))

    if isinstance(episode_spec, int):
        if episode_spec < 0 or episode_spec >= total_episodes:
            raise ValueError(f"Episode {episode_spec} out of range [0, {total_episodes - 1}]")
        return [episode_spec]

    if isinstance(episode_spec, list):
        for ep in episode_spec:
            if not isinstance(ep, int) or ep < 0 or ep >= total_episodes:
                raise ValueError(f"Episode {ep} out of range [0, {total_episodes - 1}]")
        return sorted(set(episode_spec))

    if isinstance(episode_spec, str):
        # Parse string specification
        episodes = []
        parts = episode_spec.split(",")
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if "-" in part and not part.startswith("-"):
                # Range notation: "0-5"
                try:
                    start_str, end_str = part.split("-", 1)
                    start = int(start_str.strip())
                    end = int(end_str.strip())
                    if start > end:
                        raise ValueError(f"Invalid range: {part} (start > end)")
                    episodes.extend(range(start, end + 1))
                except ValueError as e:
                    raise ValueError(f"Invalid range specification: {part}") from e
            else:
                # Single episode
                try:
                    episodes.append(int(part))
                except ValueError as e:
                    raise ValueError(f"Invalid episode number: {part}") from e

        # Validate range
        for ep in episodes:
            if ep < 0 or ep >= total_episodes:
                raise ValueError(f"Episode {ep} out of range [0, {total_episodes - 1}]")

        return sorted(set(episodes))

    raise ValueError(f"Invalid episode specification type: {type(episode_spec)}")
