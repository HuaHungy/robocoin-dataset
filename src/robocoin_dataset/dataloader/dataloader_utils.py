"""Dataset utilities for LeRobot datasets.

This module provides utilities for:
- Creating LeRobot datasets with auto backend selection
- Episode sampling with downsampling support
- Hardlink preparation for dataset structures
- Worker initialization for DataLoader
"""

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import torch  # type: ignore

# =============================
# LeRobot dataset/dataloader utilities (no DB)
# =============================
# Best-effort: auto-add vendored lerobot path for local runs without PYTHONPATH
try:
    _here_lr = Path(__file__).resolve()
    _repo_root_lr = _here_lr.parents[3]
    _vendored_lr = _repo_root_lr / "third_parties" / "robocoin-lerobot" / "src"
    if _vendored_lr.is_dir() and str(_vendored_lr) not in sys.path:
        sys.path.insert(0, str(_vendored_lr))
except Exception:
    pass

try:
    # Prefer the vendored lerobot package in third_parties if available on PYTHONPATH
    from lerobot.datasets.lerobot_dataset import LeRobotDataset  # type: ignore
except Exception:  # pragma: no cover
    LeRobotDataset = None  # type: ignore


class EpisodeSampler(torch.utils.data.Sampler):  # type: ignore
    """Episode sampler referencing lerobot's visualize_dataset logic.

    Selects the frame indices belonging to a given episode.

    Args:
        dataset: LeRobotDataset instance
        episode_index: Index of the episode to sample from
        sample_ratio: Ratio of frames to sample (0.0 to 1.0). Default is 1.0 (all frames).
                     Frames are evenly distributed across the episode when downsampling.
    """

    def __init__(self, dataset: "LeRobotDataset", episode_index: int, sample_ratio: float = 1.0) -> None:
        if not 0.0 <= sample_ratio <= 1.0:
            raise ValueError(f"sample_ratio must be between 0 and 1, got {sample_ratio}")

        from_idx = dataset.episode_data_index["from"][episode_index].item()
        to_idx = dataset.episode_data_index["to"][episode_index].item()
        total_frames = to_idx - from_idx

        if sample_ratio == 1.0:
            # Use all frames
            self.frame_ids = list(range(from_idx, to_idx))
        else:
            # Calculate number of frames to sample
            num_samples = max(1, int(total_frames * sample_ratio))

            # Select evenly distributed frames
            if num_samples == 1:
                # If only one sample, take the first frame
                self.frame_ids = [from_idx]
            else:
                # Evenly distribute samples across the range using linspace logic
                step = (total_frames - 1) / (num_samples - 1)
                self.frame_ids = [from_idx + int(i * step) for i in range(num_samples)]

    def __iter__(self) -> Iterator:
        return iter(self.frame_ids)

    def __len__(self) -> int:
        return len(self.frame_ids)


def _worker_init_suppress_output(worker_id: int) -> None:
    """Suppress stdout/stderr in DataLoader worker processes.

    This prevents print statements in third-party libraries (like lerobot's video_utils.py)
    from flooding the console when using num_workers > 0.

    Args:
        worker_id: Worker process ID (provided by PyTorch DataLoader)
    """
    import atexit

    # Close existing file objects if they exist
    if hasattr(sys.stdout, "close") and sys.stdout not in (sys.__stdout__,):
        try:
            sys.stdout.close()
        except Exception:
            pass
    if hasattr(sys.stderr, "close") and sys.stderr not in (sys.__stderr__,):
        try:
            sys.stderr.close()
        except Exception:
            pass

    # Open new file handles
    devnull_out = open(os.devnull, "w")
    devnull_err = open(os.devnull, "w")

    sys.stdout = devnull_out
    sys.stderr = devnull_err

    # Register cleanup to close handles when worker exits
    def cleanup() -> None:
        try:
            devnull_out.close()
        except Exception:
            pass
        try:
            devnull_err.close()
        except Exception:
            pass

    atexit.register(cleanup)


def create_episode_dataloader(
    dataset: "LeRobotDataset",
    episode_index: int,
    batch_size: int = 32,
    num_workers: int = 0,
    sample_ratio: float = 1.0,
) -> torch.utils.data.DataLoader:
    """Create a DataLoader for a specific episode with optional downsampling.

    Args:
        dataset: LeRobotDataset instance
        episode_index: Index of the episode to load
        batch_size: Batch size for the DataLoader
        num_workers: Number of worker processes
        sample_ratio: Ratio of frames to sample (0.0 to 1.0)

    Returns:
        Configured DataLoader for the episode
    """
    episode_sampler = EpisodeSampler(dataset, episode_index, sample_ratio)
    return torch.utils.data.DataLoader(
        dataset,
        num_workers=num_workers,
        batch_size=batch_size,
        sampler=episode_sampler,
        worker_init_fn=_worker_init_suppress_output if num_workers > 0 else None,
    )


def _prepare_hardlinks(
    source_path: str | Path,
    target_dir: Path | None = None,
    relative: bool = True,
    skip_missing: bool = False,
) -> Path:
    """Create hardlink structure for dataset and return the path to test.

    This function wraps create_lerobot_hardlink_structure and can be used by both
    local mode and distributed client mode.

    Args:
        source_path: Source dataset directory (convert_path)
        target_dir: Target directory for hardlinks (default: {source}_hardlink)
        relative: Unused for hard links (kept for compatibility)
        skip_missing: Skip missing files during hardlink creation (default: False)

    Returns:
        Path to the hardlink directory (the path to test with dataloader)

    Raises:
        Exception: If hardlink creation fails
    """
    from robocoin_dataset.hardlink.make_hardlink import (
        create_lerobot_hardlink_structure,
    )

    source = Path(source_path)
    target = target_dir if target_dir is not None else source.parent / f"{source.name}_hardlink"

    create_lerobot_hardlink_structure(
        source_dir=source,
        target_dir=target,
        relative=relative,
        skip_missing=skip_missing,
    )

    return target


def create_lerobot_dataset(
    repo_id: str,
    root: str | Path | None = None,
    episodes: list[int] | None = None,
    image_transforms: "callable | None" = None,
    delta_timestamps: dict[list[float]] | None = None,
    tolerance_s: float = 0.001,
    revision: str | None = None,
    force_cache_sync: bool = False,
    download_videos: bool = True,
    video_backend: str = "auto",
    batch_encoding_size: int = 1,
) -> "LeRobotDataset":
    """Create a LeRobotDataset with optional auto backend fallback.

    Args:
        repo_id: Dataset identifier. For local datasets, use the dataset folder name.
                 For remote datasets, use the HuggingFace repo ID (e.g., "username/dataset").
        root: Filesystem path to the dataset. For local datasets, this should be the full path.
              For remote datasets, this is where files will be downloaded/cached.
              If None, defaults to ~/.cache/huggingface/lerobot/{repo_id}.
        episodes: List of episode indices to load (None = all episodes).
        image_transforms: Optional callable for image transformations.
        delta_timestamps: Optional dict of delta timestamps.
        tolerance_s: Tolerance in seconds for timestamp synchronization.
        revision: Git revision for remote datasets.
        force_cache_sync: Force sync with remote even if files exist locally.
        download_videos: Whether to download video files.
        video_backend: Video decoding backend ("auto", "torchcodec", or "pyav").
        batch_encoding_size: Number of episodes to accumulate before batch encoding.

    Returns:
        LeRobotDataset instance with auto-selected video backend.
    """
    if LeRobotDataset is None:
        raise RuntimeError(
            "LeRobotDataset is not available. Ensure third_parties/robocoin-lerobot is on PYTHONPATH."
        )

    # Helper to build dataset with a specific backend
    def _build(backend: str) -> "LeRobotDataset":
        return LeRobotDataset(
            repo_id=repo_id,
            root=Path(root) if root is not None else None,
            episodes=episodes,
            image_transforms=image_transforms,
            delta_timestamps=delta_timestamps,
            tolerance_s=tolerance_s,
            revision=revision,
            force_cache_sync=force_cache_sync,
            download_videos=download_videos,
            video_backend=backend,
            batch_encoding_size=batch_encoding_size,
        )

    if video_backend != "auto":
        ds = _build(video_backend)
        # Attach chosen backend metadata for downstream UIs/CLIs
        try:
            setattr(ds, "robocoin_video_backend", video_backend)
            setattr(ds, "robocoin_video_backend_reason", "user_selected")
        except Exception:
            pass
        return ds

    # Auto: prefer torchcodec, then fallback to pyav on failure
    try:
        ds = _build("torchcodec")
        # Probe a single item to trigger video decoding if any video keys exist
        if len(ds.meta.video_keys) > 0 and ds.num_frames > 0:
            _ = ds[0]
        try:
            setattr(ds, "robocoin_video_backend", "torchcodec")
            setattr(ds, "robocoin_video_backend_reason", "ok")
        except Exception:
            pass
        return ds
    except Exception as e:
        # Fallback to pyav
        ds = _build("pyav")
        try:
            setattr(ds, "robocoin_video_backend", "pyav")
            setattr(ds, "robocoin_video_backend_reason", f"torchcodec failed: {repr(e)}")
        except Exception:
            pass
        return ds
