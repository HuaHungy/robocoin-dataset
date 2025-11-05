"""Dataloader utilities and validation for LeRobot datasets.

This module provides a unified interface for:
- Dataset creation and loading
- Episode sampling and dataloader creation
- Local and distributed validation workflows
- Server/client architecture for distributed processing

All functionality is now organized into focused submodules:
- dataset_utils: Dataset creation, sampling, hardlink preparation
- task_manager: Database task management
- detection: Validation and detection logic
- server: Server-side components
- client: Client-side components and multi-client support
"""

# Re-export all public APIs for backward compatibility
from robocoin_dataset.dataloader.client import (
    DataloaderDbClient,
    client_process_main,
    run_client_async,
    run_multi_client,
)
from robocoin_dataset.dataloader.dataset_utils import (
    EpisodeSampler,
    LeRobotDataset,
    create_episode_dataloader,
    create_lerobot_dataset,
)
from robocoin_dataset.dataloader.detection import (
    _run_dataloader_detection,
    run_local_batch_detection,
)
from robocoin_dataset.dataloader.server import DataloaderDbProcess, DataloaderDbServer
from robocoin_dataset.dataloader.task_manager import DEFAULT_DB_FILE, TASK_CATEGORY

__all__ = [
    # Dataset utilities
    "LeRobotDataset",
    "EpisodeSampler",
    "create_lerobot_dataset",
    "create_episode_dataloader",
    # Task management
    "TASK_CATEGORY",
    "DEFAULT_DB_FILE",
    # Detection and validation
    "_run_dataloader_detection",
    "run_local_batch_detection",
    # Server components
    "DataloaderDbProcess",
    "DataloaderDbServer",
    # Client components
    "DataloaderDbClient",
    "run_client_async",
    "client_process_main",
    "run_multi_client",
]
