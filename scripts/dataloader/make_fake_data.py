#!/usr/bin/env python3
"""
Script to generate fake data for testing the symlink creation script.
prints the actual structure of the generated data on the CLI.


USAGE:
  # Create test data in default location (examples/dataloader_test/fake_ori_data_001/):
  python scripts/dataloader/make_fake_data.py

  # Run again - auto-increments to fake_ori_data_002 if fake_ori_data_001 exists:
  python scripts/dataloader/make_fake_data.py

  # Create test data with custom dataset name:
  python make_fake_data.py --dataset-name fake_ori_data_002

  # Create test data in custom location:
  python make_fake_data.py --output /path/to/test/data
  python make_fake_data.py -o /path/to/test/data

NOTE: If the dataset name already exists, it will automatically increment the version
      number (e.g., fake_ori_data_001 -> fake_ori_data_002 -> fake_ori_data_003, etc.)

This creates a directory with the pipeline-produced structure containing:
- annotations/                  >>> folder with subtask_annotations.jsonl
- data/                         >>> folder with episode chunks (parquet files, max 1000 episodes per chunk)
- eef_sim_data/                 >>> folder with episode chunks (parquet files)
- merged_data/                  >>> folder with episode chunks (parquet files, max 1000 episodes per chunk)
- state_action_data/            >>> folder with episode chunks (parquet files)
- subtask_annotation_data/      >>> folder with episode chunks (parquet files)
- meta/                         >>> folder with all metadata files (eef_sim_info.json, episodes.jsonl, episodes_stats.jsonl,
                                        info.json, merged_info.json, merged_episodes_stats.jsonl, state_action_info.json, subtask_annotation_info.json, tasks.jsonl)
- videos/                       >>> folder organized by chunks and camera subdirectories

The data is generated in a structure like:
  examples/dataloader_test/fake_ori_data_001/
    ├── annotations/
    │   └── subtask_annotations.jsonl
    ├── data/
    │   └── chunk-000/
    ├── eef_sim_data/
    │   └── chunk-000/
    ├── merged_data/
    │   └── chunk-000/
    ├── state_action_data/
    │   └── chunk-000/
    ├── subtask_annotation_data/
    │   └── chunk-000/
    ├── meta/
    │   ├── eef_sim_info.json
    │   ├── episodes.jsonl
    │   ├── episodes_stats.jsonl
    │   ├── info.json
    │   ├── merged_info.json
    │   ├── state_action_info.json
    │   ├── subtask_annotation_info.json
    │   └── tasks.jsonl
    └── videos/
        └── chunk-000/
            ├── observation.images.cam_high_rgb/
            ├── observation.images.cam_left_wrist_rgb/
            └── observation.images.cam_right_wrist_rgb/
"""

import argparse
import json
import random
import re
import shutil
import subprocess
import sys
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from sqlalchemy import text

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import TaskStatus
from robocoin_dataset.dataloader.make_symlink import create_lerobot_symlink_structure

# Try to import pandas and pyarrow for parquet file generation
try:
    import pandas as pd
    import pyarrow.parquet as pq
    PARQUET_AVAILABLE = True
except ImportError:
    PARQUET_AVAILABLE = False
    print("⚠️  Warning: pandas or pyarrow not available. Will create minimal parquet files.")

FPS = 30


def _get_parquet_num_rows(file_path: Path) -> int:
    """Return number of rows in a parquet file or 0 on error/unavailable deps."""
    try:
        if PARQUET_AVAILABLE and file_path.exists():
            pf = pq.ParquetFile(file_path)
            return int(pf.metadata.num_rows)
    except Exception:
        pass
    return 0


def _sanitize_or_truncate_data_parquet(file_path: Path, episode_num: int, target_len: int | None = None) -> int:
    """Ensure a 'data' parquet has uniform timestamps at FPS and optional truncation.

    Rewrites columns 'timestamp', 'frame_index', 'episode_index', 'index', 'task_index'.
    Returns resulting number of rows (0 on failure/unavailable deps).
    """
    if not PARQUET_AVAILABLE:
        return _get_parquet_num_rows(file_path)
    try:
        import numpy as np
        import pandas as pd  # type: ignore

        df = pd.read_parquet(file_path)
        if target_len is not None:
            df = df.iloc[: int(target_len)].copy()
        n = int(len(df))
        if n <= 0:
            return 0

        # Rebuild timing/indices to guarantee sync
        df["timestamp"] = (np.arange(n, dtype=np.float32) / float(FPS)).astype(np.float32)
        df["frame_index"] = np.arange(n, dtype=np.int64)
        df["episode_index"] = np.full(n, int(episode_num), dtype=np.int64)
        df["index"] = np.arange(int(episode_num) * 1000, int(episode_num) * 1000 + n, dtype=np.int64)
        if "task_index" not in df.columns:
            df["task_index"] = 0
        else:
            df["task_index"] = np.zeros(n, dtype=np.int64)

        df.to_parquet(file_path, engine="pyarrow")
        return n
    except Exception:
        return _get_parquet_num_rows(file_path)


def _truncate_parquet_to_length(file_path: Path, target_len: int) -> int:
    """Truncate any parquet file to target_len rows. Returns resulting row count.

    Safe no-op if deps unavailable or errors occur.
    """
    if not PARQUET_AVAILABLE:
        return _get_parquet_num_rows(file_path)
    try:
        import pandas as pd  # type: ignore

        if not file_path.exists():
            return 0
        df = pd.read_parquet(file_path)
        if len(df) > target_len:
            df = df.iloc[: int(target_len)].copy()
            df.to_parquet(file_path, engine="pyarrow")
        return int(len(df))
    except Exception:
        return _get_parquet_num_rows(file_path)


def create_fake_parquet_file(file_path: Path, episode_num: int, data_type: str = "data", project_root: Path | None = None, reference_root: Path | None = None) -> int:
    """Create or copy a parquet file for an episode based on data type and return its row count.

    Preference order:
    1) Copy from provided reference dataset if available
    2) Copy a random sample from examples/dataloader_test/ref_parquet[/<data_type>]
    3) Generate a synthetic parquet with minimal required schema
    """
    # Prefer generation for all parquet files (no copying)
    if PARQUET_AVAILABLE:
        import numpy as np
        rng = np.random.default_rng(episode_num)

        # Variable length per episode (between 600-750 frames)
        num_frames = 600 + (episode_num * 53) % 150

        if data_type == "data":
            # Full data with all fields
            df = pd.DataFrame({
                'observation.state': [
                    rng.uniform(-3.0, 3.0, 28).astype(np.float32)
                    for _ in range(num_frames)
                ],
                'action': [
                    rng.uniform(-3.0, 3.0, 28).astype(np.float32)
                    for _ in range(num_frames)
                ],
                'timestamp': (np.arange(num_frames, dtype=np.float32) / 30.0).astype(np.float32),
                'frame_index': np.arange(num_frames, dtype=np.int64),
                'episode_index': np.full(num_frames, episode_num, dtype=np.int64),
                'index': np.arange(episode_num * 1000, episode_num * 1000 + num_frames, dtype=np.int64),
                'task_index': np.zeros(num_frames, dtype=np.int64),
            })
        elif data_type == "merged_data" or data_type == "state_action_data":
            # Ensure merged/state_action parquet files contain the same required columns as 'data'
            df = pd.DataFrame({
                'observation.state': [
                    rng.uniform(-3.0, 3.0, 28).astype(np.float32)
                    for _ in range(num_frames)
                ],
                'action': [
                    rng.uniform(-3.0, 3.0, 28).astype(np.float32)
                    for _ in range(num_frames)
                ],
                'timestamp': (np.arange(num_frames, dtype=np.float32) / 30.0).astype(np.float32),
                'frame_index': np.arange(num_frames, dtype=np.int64),
                'episode_index': np.full(num_frames, episode_num, dtype=np.int64),
                'index': np.arange(episode_num * 1000, episode_num * 1000 + num_frames, dtype=np.int64),
                'task_index': np.zeros(num_frames, dtype=np.int64),
            })
        elif data_type == "eef_sim_data":
            # EEF sim data with 14 dimensions
            df = pd.DataFrame({
                'eef_sim.state': [
                    rng.uniform(-3.0, 3.0, 14).astype(np.float32)
                    for _ in range(num_frames)
                ],
                'action': [
                    rng.uniform(-3.0, 3.0, 14).astype(np.float32)
                    for _ in range(num_frames)
                ],
            })
        elif data_type == "subtask_annotation_data":
            # Subtask annotation - keep same length as videos
            df = pd.DataFrame({
                'subtask_annotation': [
                    np.array([rng.integers(0, 5)] + [-1] * 4, dtype=np.int32)
                    for _ in range(num_frames)
                ],
            })

        df.to_parquet(file_path, engine='pyarrow')
        return int(num_frames)
    # Create a minimal parquet file manually
    file_path.parent.mkdir(parents=True, exist_ok=True)
    # Just create an empty file as placeholder
    file_path.touch()
    return 0


def _try_copy_random_ref_video(target_path: Path, project_root: Path) -> bool:
    """Try to copy a random reference video into target_path. Returns True on success."""
    try:
        ref_dir = project_root / "examples" / "dataloader_test" / "ref_videos"
        if not ref_dir.exists():
            return False
        candidates = sorted(ref_dir.glob("*.mp4"))
        if not candidates:
            return False
        chosen = random.choice(candidates)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"      [video] copy from ref_videos: {chosen.name} -> {target_path}")
        shutil.copyfile(chosen, target_path)
        return True
    except Exception:
        return False


def _try_copy_random_ref_parquet(target_path: Path, project_root: Path, data_type: str) -> bool:
    """Try to copy a random reference parquet into target_path. Returns True on success.

    Looks under examples/dataloader_test/ref_parquet first in a subdir matching
    the data_type (e.g., 'data', 'merged_data', 'state_action_data', 'eef_sim_data',
    'subtask_annotation_data'). Falls back to the base ref_parquet directory.
    """
    try:
        # If we can't read parquet metadata later, avoid copying and fallback to generation
        if not PARQUET_AVAILABLE:
            return False
        ref_base = project_root / "examples" / "dataloader_test" / "ref_parquet"
        candidates: list[Path] = []
        type_dir = ref_base / data_type
        if type_dir.exists():
            candidates = sorted(type_dir.glob("*.parquet"))
        if not candidates and ref_base.exists():
            candidates = sorted(ref_base.glob("*.parquet"))
        if not candidates:
            return False
        chosen = random.choice(candidates)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(chosen, target_path)
        return True
    except Exception:
        return False


def _episode_chunk_dir(episode_num: int, chunk_size: int = 1000) -> str:
    """Return chunk directory name for given episode index."""
    return f"chunk-{episode_num // chunk_size:03d}"


def _try_copy_reference_video(target_path: Path, reference_root: Path, episode_num: int, camera_name: str) -> bool:
    """Try copying video from a reference dataset for the same episode and camera.

    Falls back to searching any matching episode file within the videos tree.
    """
    try:
        # Preferred path: videos/chunk-XXX/<camera_name>/episode_XXXXXX.mp4
        preferred = reference_root / "videos" / _episode_chunk_dir(episode_num) / camera_name / f"episode_{episode_num:06d}.mp4"
        if preferred.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            print(f"      [video] copy from reference_data: {preferred} -> {target_path}")
            shutil.copyfile(preferred, target_path)
            return True
        # Fallback: search anywhere in videos for this episode file
        videos_root = reference_root / "videos"
        if videos_root.exists():
            candidates = list(videos_root.glob(f"**/episode_{episode_num:06d}.mp4"))
            if candidates:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                print(f"      [video] copy from reference_data: {candidates[0]} -> {target_path}")
                shutil.copyfile(candidates[0], target_path)
                return True
    except Exception:
        return False
    return False


def _try_copy_reference_parquet(target_path: Path, reference_root: Path, data_type: str, episode_num: int) -> bool:
    """Try copying parquet from a reference dataset for the same episode and data_type.

    Falls back to searching any matching episode file within the data_type tree.
    """
    try:
        # Preferred path: <data_type>/chunk-XXX/episode_XXXXXX.parquet
        preferred = reference_root / data_type / _episode_chunk_dir(episode_num) / f"episode_{episode_num:06d}.parquet"
        if preferred.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(preferred, target_path)
            return True
        # Fallback: search anywhere in the data_type directory for this episode file
        type_root = reference_root / data_type
        if type_root.exists():
            candidates = list(type_root.glob(f"**/episode_{episode_num:06d}.parquet"))
            if candidates:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(candidates[0], target_path)
                return True
    except Exception:
        return False
    return False

def _try_generate_decodable_video(target_path: Path, width: int = 640, height: int = 480, fps: int = 30, frames: int = 30) -> bool:
    """Try to synthesize a small, decodable MP4 video. Returns True on success."""
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Attempt with OpenCV first
    try:
        import cv2  # type: ignore
        import numpy as np

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(target_path), fourcc, float(fps), (width, height))
        if not writer.isOpened():
            writer.release()
            raise RuntimeError("cv2.VideoWriter failed to open")

        for i in range(frames):
            # simple moving gradient pattern
            x = np.linspace(0, 255, width, dtype=np.uint8)
            y = np.linspace(0, 255, height, dtype=np.uint8)
            xv, yv = np.meshgrid(x, y)
            r = ((xv + 3 * i) % 256).astype(np.uint8)
            g = ((yv + 5 * i) % 256).astype(np.uint8)
            b = (((xv // 2 + yv // 2) + 7 * i) % 256).astype(np.uint8)
            frame = np.dstack([b, g, r])  # BGR for OpenCV
            writer.write(frame)
        writer.release()
        return True
    except Exception:
        pass

    # Fallback to imageio
    try:
        import imageio.v3 as iio  # type: ignore
        import numpy as np

        frames_buf = []
        for i in range(frames):
            x = np.linspace(0, 255, width, dtype=np.uint8)
            y = np.linspace(0, 255, height, dtype=np.uint8)
            xv, yv = np.meshgrid(x, y)
            r = ((xv + 3 * i) % 256).astype(np.uint8)
            g = ((yv + 5 * i) % 256).astype(np.uint8)
            b = (((xv // 2 + yv // 2) + 7 * i) % 256).astype(np.uint8)
            frame_rgb = np.dstack([r, g, b])  # RGB for imageio
            frames_buf.append(frame_rgb)

        # imageio decides encoder via extension; mp4 typically uses ffmpeg
        iio.imwrite(target_path, frames_buf, fps=fps)
        return True
    except Exception:
        pass

    # As a last resort, create an empty placeholder to not crash file creation
    try:
        target_path.touch()
    except Exception:
        return False
    return False


def _get_video_num_frames_and_fps(video_path: Path) -> tuple[int, float]:
    """Probe number of frames and fps of a video file. Returns (frames, fps)."""
    # Try ffprobe first (most reliable)
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=nb_frames,r_frame_rate",
                "-of",
                "default=noprint_wrappers=1:nokey=0",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        out = result.stdout
        nb_frames = 0
        fps_val = float(FPS)
        for line in out.splitlines():
            if line.startswith("nb_frames="):
                val = line.split("=", 1)[1].strip()
                if val.isdigit():
                    nb_frames = int(val)
            elif line.startswith("r_frame_rate="):
                val = line.split("=", 1)[1].strip()
                if "/" in val:
                    num, den = val.split("/", 1)
                    try:
                        num_f = float(num)
                        den_f = float(den)
                        if den_f > 0:
                            fps_val = num_f / den_f
                    except Exception:
                        pass
        if nb_frames > 0:
            return nb_frames, fps_val
    except Exception:
        pass

    # Try OpenCV next
    try:
        import cv2  # type: ignore

        cap = cv2.VideoCapture(str(video_path))
        if cap.isOpened():
            frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps_val = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            cap.release()
            return max(frames, 0), (fps_val if fps_val > 0 else float(FPS))
    except Exception:
        pass

    # Fallback to imageio
    try:
        import imageio.v3 as iio  # type: ignore

        meta = iio.immeta(video_path)
        fps_val = float(meta.get("fps", FPS)) if isinstance(meta, dict) else float(FPS)
        # Counting frames can be slow; try count_frames else iterate up to a cap
        try:
            # imageio v3 does not expose count_frames directly; iterate
            frame_iter = iio.imiter(video_path)
            frames = 0
            for _ in frame_iter:
                frames += 1
            return frames, fps_val
        except Exception:
            return 0, fps_val
    except Exception:
        pass

    return 0, float(FPS)


def _clip_video_to_frames_inplace(video_path: Path, target_frames: int, fps: float = float(FPS)) -> bool:
    """Rewrite the video to contain exactly target_frames frames at given fps."""
    if target_frames <= 0:
        return False
    tmp_path = video_path.with_suffix(".tmp.mp4")

    # Prefer ffmpeg for robust decoding/encoding
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(video_path),
            "-r",
            str(int(fps)),
            "-frames:v",
            str(int(target_frames)),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(tmp_path),
        ]
        subprocess.run(cmd, check=True)
        shutil.move(str(tmp_path), str(video_path))
        return True
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)  # type: ignore
        except Exception:
            pass

    # Try OpenCV first
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            cap.release()
            raise RuntimeError("cv2.VideoCapture failed to open")

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(tmp_path), fourcc, float(fps), (width, height))
        if not writer.isOpened():
            writer.release()
            cap.release()
            raise RuntimeError("cv2.VideoWriter failed to open")

        frames_written = 0
        while frames_written < target_frames:
            ok, frame = cap.read()
            if not ok:
                # If source shorter, pad black frames
                frame = np.zeros((height, width, 3), dtype=np.uint8)
            writer.write(frame)
            frames_written += 1

        writer.release()
        cap.release()

        shutil.move(str(tmp_path), str(video_path))
        return True
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)  # type: ignore
        except Exception:
            pass

    # Fallback to imageio
    try:
        import imageio.v3 as iio  # type: ignore
        import numpy as np  # type: ignore

        frames_buf = []
        try:
            src_iter = iio.imiter(video_path)
            for i in range(target_frames):
                try:
                    frame = next(src_iter)
                except StopIteration:
                    # pad black frame if needed
                    # Attempt to probe size from first buffered frame or default
                    if frames_buf:
                        h, w = frames_buf[0].shape[:2]
                    else:
                        h, w = 480, 640
                    frame = np.zeros((h, w, 3), dtype=np.uint8)
                frames_buf.append(frame)
        except Exception:
            # If cannot read, synthesize
            h, w = 480, 640
            frames_buf.extend([np.zeros((h, w, 3), dtype=np.uint8) for _ in range(target_frames)])

        iio.imwrite(tmp_path, frames_buf, fps=fps)
        shutil.move(str(tmp_path), str(video_path))
        return True
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)  # type: ignore
        except Exception:
            pass
    return False


def _probe_codec_with_ffprobe(video_path: Path) -> str | None:
    """Return codec_name via ffprobe or None on failure."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        codec = result.stdout.strip()
        return codec if codec else None
    except Exception:
        return None


def _reencode_video_to_h264_inplace(video_path: Path, fps: float = float(FPS)) -> bool:
    """Force re-encode to H.264 yuv420p at specified fps (if ffmpeg available)."""
    tmp_path = video_path.with_suffix(".reenc.mp4")
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(video_path),
            "-r",
            str(int(fps)),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(tmp_path),
        ]
        subprocess.run(cmd, check=True)
        shutil.move(str(tmp_path), str(video_path))
        return True
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)  # type: ignore
        except Exception:
            pass
    return False


def create_fake_video_file(file_path: Path, episode_num: int, camera_name: str = "camera", project_root: Path | None = None, reference_root: Path | None = None) -> None:
    """Create or copy a video file for testing.

    Preference order:
    1) Copy a random sample from examples/dataloader_test/ref_videos
    2) Copy from provided reference dataset if available
    3) Synthesize a small, decodable MP4 via OpenCV or imageio
    4) Create an empty placeholder (least preferred)
    """
    # Try copy from ref_videos first, if project_root provided
    if project_root is not None:
        # Prefer copying from ref_videos
        if _try_copy_random_ref_video(file_path, project_root):
            return
    # Try copy from reference dataset after
    if reference_root is not None:
        if _try_copy_reference_video(file_path, reference_root, episode_num, camera_name):
            return

    # Fallback: generate a tiny synthetic video
    print(f"      [video] generate synthetic: episode {episode_num:06d} {camera_name} -> {file_path}")
    if _try_generate_decodable_video(file_path):
        return

    # Last resort placeholder already handled in generator; ensure file exists
    if not file_path.exists():
        file_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"      [video] create placeholder: {file_path}")
        file_path.touch()

    # After creation/copy, if codec is not h264 (or probing fails), try re-encode
    codec = _probe_codec_with_ffprobe(file_path)
    if codec is None or codec.lower() not in {"h264", "avc1"}:
        print(f"      [video] re-encode to h264: {file_path}")
        _reencode_video_to_h264_inplace(file_path, float(FPS))


def create_jsonl_file(file_path: Path, data: list[dict[str, Any]]) -> None:
    """Create a JSONL file with given data."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w') as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')


def create_json_file(file_path: Path, data: dict[str, Any]) -> None:
    """Create a JSON file with given data."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def print_actual_structure_tree(output_dir: Path) -> None:
    """
    Print the actual generated directory structure by inspecting the filesystem.

    Args:
        output_dir: Root directory of the generated dataset
    """
    print("\n📋 Summary:")
    print(f"   Location: {output_dir}")
    print("   Structure:")

    # 1. Annotations
    if (output_dir / "annotations").exists():
        annotations_dir = output_dir / "annotations"
        jsonl_files = list(annotations_dir.glob("*.jsonl"))
        if jsonl_files:
            # Count lines in subtask_annotations.jsonl
            subtask_file = annotations_dir / "subtask_annotations.jsonl"
            num_subtasks = 0
            if subtask_file.exists():
                with open(subtask_file) as f:
                    num_subtasks = sum(1 for _ in f)
            print("     ├── annotations/")
            print(f"     │   └── subtask_annotations.jsonl ({num_subtasks} subtask definitions)")

    # 2-6. Data folders with chunks
    data_folders = ["data", "eef_sim_data", "merged_data", "state_action_data", "subtask_annotation_data"]
    for folder_name in data_folders:
        folder_path = output_dir / folder_name
        if folder_path.exists():
            chunks = sorted([d for d in folder_path.iterdir() if d.is_dir() and d.name.startswith("chunk-")])
            if chunks:
                # Count episodes in all chunks
                total_episodes = 0
                for chunk_dir in chunks:
                    parquet_files = list(chunk_dir.glob("episode_*.parquet"))
                    total_episodes += len(parquet_files)

                chunk_names = [c.name for c in chunks]
                if len(chunks) <= 3:
                    chunk_display = " ... ".join(chunk_names)
                else:
                    chunk_display = f"{chunk_names[0]} ... {chunk_names[-1]}"

                print(f"     ├── {folder_name}/ (max 1000 episodes per chunk)")
                print(f"     │   └── {chunk_display}/ ({len(chunks)} chunks total, {total_episodes} episodes)")

    # 7. Meta folder
    meta_dir = output_dir / "meta"
    if meta_dir.exists():
        print("     ├── meta/")
        meta_files = sorted([f.name for f in meta_dir.iterdir() if f.is_file()])
        for i, meta_file in enumerate(meta_files):
            is_last = (i == len(meta_files) - 1)
            prefix = "└──" if is_last else "├──"

            # Add counts for specific files
            file_path = meta_dir / meta_file
            extra_info = ""
            if meta_file.endswith(".jsonl"):
                with open(file_path) as f:
                    count = sum(1 for _ in f)
                if "episodes" in meta_file:
                    extra_info = f" ({count} episodes)"
                elif "tasks" in meta_file:
                    extra_info = f" ({count} task{'s' if count != 1 else ''})"
                else:
                    extra_info = f" ({count} entries)"

            print(f"     │   {prefix} {meta_file}{extra_info}")

    # 8. Videos folder
    videos_dir = output_dir / "videos"
    if videos_dir.exists():
        print("     └── videos/")
        video_chunks = sorted([d for d in videos_dir.iterdir() if d.is_dir() and d.name.startswith("chunk-")])

        if video_chunks:
            # Get all camera directories from all chunks
            all_cameras = set()
            total_videos_per_camera = {}

            for chunk_dir in video_chunks:
                camera_dirs = [d for d in chunk_dir.iterdir() if d.is_dir()]
                for camera_dir in camera_dirs:
                    camera_name = camera_dir.name
                    all_cameras.add(camera_name)
                    video_files = list(camera_dir.glob("episode_*.mp4"))
                    total_videos_per_camera[camera_name] = total_videos_per_camera.get(camera_name, 0) + len(video_files)

            # Print chunk structure
            sorted_cameras = sorted(all_cameras)
            if video_chunks:
                print(f"         └── {video_chunks[0].name}/")
                for i, camera_name in enumerate(sorted_cameras):
                    is_last = (i == len(sorted_cameras) - 1)
                    prefix = "└──" if is_last else "├──"
                    video_count = total_videos_per_camera.get(camera_name, 0)
                    print(f"             {prefix} {camera_name}/ ({video_count} videos)")

    print("\n🔗 Next step: Run the symlink script on this directory:")
    print(f"   python scripts/dataloader/make_symlink.py --source {output_dir}")


def generate_fake_pipeline_data(
    output_dir: Path,
    num_episodes: int = 100,
    num_chunks: int = 3,
    num_videos_per_episode: int = 2,
    project_root: Path | None = None,
    reference_root: Path | None = None
) -> None:
    """
    Generate fake data in the pipeline-produced structure.

    Args:
        output_dir: Root directory where fake data will be created
        num_episodes: Total number of episodes to generate
        num_chunks: Number of chunks to create (episodes will be distributed)
        num_videos_per_episode: Number of video files per episode
    """
    print(f"\n🚀 Generating fake pipeline data at: {output_dir}")
    print(f"   Episodes: {num_episodes}, Chunks: {num_chunks}\n")

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create annotations/ folder with subtask_annotations.jsonl
    print("📁 Creating annotations/")
    annotations_dir = output_dir / "annotations"
    annotations_dir.mkdir(exist_ok=True)

    # subtask_annotations.jsonl - global subtask definitions
    subtask_annotations_data = [
        {"subtask_index": 0, "subtask": "Hold the basket with your left arm"},
        {"subtask_index": 1, "subtask": "End"},
        {"subtask_index": 2, "subtask": "Place it in the middle"},
        {"subtask_index": 3, "subtask": "Put it in the basket"},
        {"subtask_index": 4, "subtask": "Hold the peach with your right arm"},
    ]
    create_jsonl_file(annotations_dir / "subtask_annotations.jsonl", subtask_annotations_data)

    # Calculate chunks based on max 1000 episodes per chunk
    max_episodes_per_chunk = 1000
    actual_num_chunks = (num_episodes + max_episodes_per_chunk - 1) // max_episodes_per_chunk

    # 2. Create data/ folder with episode chunks
    print("📁 Creating data/ with episode chunks")
    data_dir = output_dir / "data"
    data_dir.mkdir(exist_ok=True)
    # Track actual row counts per episode for consistency with metadata
    episode_lengths: dict[int, int] = {}

    for chunk_idx in range(actual_num_chunks):
        chunk_dir = data_dir / f"chunk-{chunk_idx:03d}"
        chunk_dir.mkdir(exist_ok=True)

        start_episode = chunk_idx * max_episodes_per_chunk
        end_episode = min((chunk_idx + 1) * max_episodes_per_chunk, num_episodes)

        print(f"   Creating chunk-{chunk_idx:03d}/ (episodes {start_episode} to {end_episode-1})")
        for episode_num in range(start_episode, end_episode):
            parquet_file = chunk_dir / f"episode_{episode_num:06d}.parquet"
            # Prefer generating; do not copy from references
            row_count = create_fake_parquet_file(parquet_file, episode_num, data_type="data", project_root=None, reference_root=None)
            episode_lengths[episode_num] = int(row_count)
            if (episode_num - start_episode + 1) % 100 == 0:
                print(f"      Generated {episode_num - start_episode + 1}/{end_episode - start_episode} episodes in chunk-{chunk_idx:03d}")
    # Reconcile episode lengths by scanning produced parquet files from disk
    # This guarantees strict agreement with what HF will load.
    try:
        for chunk_dir in sorted(data_dir.glob("chunk-*")):
            if not chunk_dir.is_dir():
                continue
            for pfile in sorted(chunk_dir.glob("episode_*.parquet")):
                m = re.search(r"episode_(\d+)\.parquet$", pfile.name)
                if not m:
                    continue
                ep_idx = int(m.group(1))
                episode_lengths[ep_idx] = _get_parquet_num_rows(pfile)

        # Do not normalize here; videos will drive final lengths
    except Exception:
        # Non-fatal: keep earlier counts
        pass



    # 3. Create eef_sim_data/ folder with episode chunks
    print("📁 Creating eef_sim_data/ with episode chunks")
    eef_sim_data_dir = output_dir / "eef_sim_data"
    eef_sim_data_dir.mkdir(exist_ok=True)

    for chunk_idx in range(actual_num_chunks):
        chunk_dir = eef_sim_data_dir / f"chunk-{chunk_idx:03d}"
        chunk_dir.mkdir(exist_ok=True)

        start_episode = chunk_idx * max_episodes_per_chunk
        end_episode = min((chunk_idx + 1) * max_episodes_per_chunk, num_episodes)

        print(f"   Creating chunk-{chunk_idx:03d}/ (episodes {start_episode} to {end_episode-1})")
        for episode_num in range(start_episode, end_episode):
            parquet_file = chunk_dir / f"episode_{episode_num:06d}.parquet"
            create_fake_parquet_file(parquet_file, episode_num, data_type="eef_sim_data", project_root=None, reference_root=None)

            if (episode_num - start_episode + 1) % 100 == 0:
                print(f"      Generated {episode_num - start_episode + 1}/{end_episode - start_episode} episodes in chunk-{chunk_idx:03d}")

    # 4. Create merged_data/ folder with episode chunks
    print("📁 Creating merged_data/ with episode chunks")
    merged_data_dir = output_dir / "merged_data"
    merged_data_dir.mkdir(exist_ok=True)

    for chunk_idx in range(actual_num_chunks):
        chunk_dir = merged_data_dir / f"chunk-{chunk_idx:03d}"
        chunk_dir.mkdir(exist_ok=True)

        start_episode = chunk_idx * max_episodes_per_chunk
        end_episode = min((chunk_idx + 1) * max_episodes_per_chunk, num_episodes)

        print(f"   Creating chunk-{chunk_idx:03d}/ (episodes {start_episode} to {end_episode-1})")
        for episode_num in range(start_episode, end_episode):
            parquet_file = chunk_dir / f"episode_{episode_num:06d}.parquet"
            create_fake_parquet_file(parquet_file, episode_num, data_type="merged_data", project_root=None, reference_root=None)

            if (episode_num - start_episode + 1) % 100 == 0:
                print(f"      Generated {episode_num - start_episode + 1}/{end_episode - start_episode} episodes in chunk-{chunk_idx:03d}")

    # 5. Create state_action_data/ folder with episode chunks
    print("📁 Creating state_action_data/ with episode chunks")
    state_action_data_dir = output_dir / "state_action_data"
    state_action_data_dir.mkdir(exist_ok=True)

    for chunk_idx in range(actual_num_chunks):
        chunk_dir = state_action_data_dir / f"chunk-{chunk_idx:03d}"
        chunk_dir.mkdir(exist_ok=True)

        start_episode = chunk_idx * max_episodes_per_chunk
        end_episode = min((chunk_idx + 1) * max_episodes_per_chunk, num_episodes)

        print(f"   Creating chunk-{chunk_idx:03d}/ (episodes {start_episode} to {end_episode-1})")
        for episode_num in range(start_episode, end_episode):
            parquet_file = chunk_dir / f"episode_{episode_num:06d}.parquet"
            create_fake_parquet_file(parquet_file, episode_num, data_type="state_action_data", project_root=None, reference_root=None)

            if (episode_num - start_episode + 1) % 100 == 0:
                print(f"      Generated {episode_num - start_episode + 1}/{end_episode - start_episode} episodes in chunk-{chunk_idx:03d}")

    # 6. Create subtask_annotation_data/ folder with episode chunks
    print("📁 Creating subtask_annotation_data/ with episode chunks")
    subtask_annotation_data_dir = output_dir / "subtask_annotation_data"
    subtask_annotation_data_dir.mkdir(exist_ok=True)

    for chunk_idx in range(actual_num_chunks):
        chunk_dir = subtask_annotation_data_dir / f"chunk-{chunk_idx:03d}"
        chunk_dir.mkdir(exist_ok=True)

        start_episode = chunk_idx * max_episodes_per_chunk
        end_episode = min((chunk_idx + 1) * max_episodes_per_chunk, num_episodes)

        print(f"   Creating chunk-{chunk_idx:03d}/ (episodes {start_episode} to {end_episode-1})")
        for episode_num in range(start_episode, end_episode):
            parquet_file = chunk_dir / f"episode_{episode_num:06d}.parquet"
            create_fake_parquet_file(parquet_file, episode_num, data_type="subtask_annotation_data", project_root=None, reference_root=None)

            if (episode_num - start_episode + 1) % 100 == 0:
                print(f"      Generated {episode_num - start_episode + 1}/{end_episode - start_episode} episodes in chunk-{chunk_idx:03d}")

    # 7. Create videos/ folder with camera subdirectories
    print("📁 Creating videos/")
    videos_dir = output_dir / "videos"
    videos_dir.mkdir(exist_ok=True)

    # Create camera subdirectories in chunks
    camera_names = [
        "observation.images.cam_high_rgb",
        "observation.images.cam_left_wrist_rgb",
        "observation.images.cam_right_wrist_rgb"
    ]

    # Make videos authoritative for all episodes
    num_video_episodes = num_episodes

    for chunk_idx in range(actual_num_chunks):
        chunk_dir = videos_dir / f"chunk-{chunk_idx:03d}"
        chunk_dir.mkdir(exist_ok=True)

        start_episode = chunk_idx * max_episodes_per_chunk
        end_episode = min((chunk_idx + 1) * max_episodes_per_chunk, num_episodes)

        # Limit video generation to first 100 episodes total to save space
        if start_episode >= num_video_episodes:
            continue

        end_episode = min(end_episode, num_video_episodes)

        print(f"   Creating chunk-{chunk_idx:03d}/ video files (episodes {start_episode} to {end_episode-1})")

        for episode_num in range(start_episode, end_episode):
            per_cam_paths: list[tuple[str, Path]] = []
            # Create videos per camera
            for camera_name in camera_names:
                camera_dir = chunk_dir / camera_name
                camera_dir.mkdir(parents=True, exist_ok=True)
                video_file = camera_dir / f"episode_{episode_num:06d}.mp4"
                create_fake_video_file(video_file, episode_num, camera_name, project_root=project_root, reference_root=reference_root)
                per_cam_paths.append((camera_name, video_file))

            # Probe frames and clip to per-episode minimum
            frame_counts = []
            for _, p in per_cam_paths:
                frames, fps_val = _get_video_num_frames_and_fps(p)
                frame_counts.append(frames)
            # If none readable, synthesize default length
            target_len = max(0, min([fc for fc in frame_counts if fc > 0]) if any(fc > 0 for fc in frame_counts) else FPS)
            for _, p in per_cam_paths:
                frames, _ = _get_video_num_frames_and_fps(p)
                if frames != target_len:
                    _clip_video_to_frames_inplace(p, int(target_len), float(FPS))
            # Record authoritative episode length from videos
            episode_lengths[episode_num] = int(target_len)

    # Enforce all parquet lengths to match video-derived episode lengths
    for folder_name in ["data", "merged_data", "state_action_data", "eef_sim_data", "subtask_annotation_data"]:
        base_dir = output_dir / folder_name
        if not base_dir.exists():
            continue
        for chunk_dir in sorted(base_dir.glob("chunk-*")):
            if not chunk_dir.is_dir():
                continue
            for pfile in sorted(chunk_dir.glob("episode_*.parquet")):
                m = re.search(r"episode_(\d+)\.parquet$", pfile.name)
                if not m:
                    continue
                ep_idx = int(m.group(1))
                tlen = int(episode_lengths.get(ep_idx, 0))
                if tlen <= 0:
                    continue
                if folder_name == "data":
                    _sanitize_or_truncate_data_parquet(pfile, ep_idx, tlen)
                else:
                    _truncate_parquet_to_length(pfile, tlen)

    # Final reconciliation: recompute episode lengths from actual 'data' parquet files on disk
    try:
        data_dir = output_dir / "data"
        if data_dir.exists():
            for chunk_dir in sorted(data_dir.glob("chunk-*")):
                if not chunk_dir.is_dir():
                    continue
                for pfile in sorted(chunk_dir.glob("episode_*.parquet")):
                    m = re.search(r"episode_(\d+)\.parquet$", pfile.name)
                    if not m:
                        continue
                    ep_idx = int(m.group(1))
                    episode_lengths[ep_idx] = _get_parquet_num_rows(pfile)
    except Exception:
        pass

    # 8. Create meta/ folder with all metadata files
    print("📝 Creating meta/ folder with metadata files")
    meta_dir = output_dir / "meta"
    meta_dir.mkdir(exist_ok=True)

    # episodes.jsonl
    print("   Creating meta/episodes.jsonl")
    episodes_data = []
    for episode_num in range(num_episodes):
        # Use actual row count from created/copied parquet
        length = int(episode_lengths.get(episode_num, 0))
        episodes_data.append({
            "episode_index": episode_num,
            "tasks": ["the left gripper pick up the basket to the appropriate position,  the right gripper pick up the peach and place it into the basket."],
            "length": length
        })
    create_jsonl_file(meta_dir / "episodes.jsonl", episodes_data)

    # episodes_stats.jsonl - comprehensive stats
    print("   Creating meta/episodes_stats.jsonl")
    episodes_stats_data = []
    for episode_num in range(num_episodes):
        length = int(episode_lengths.get(episode_num, 0))
        # Numeric defaults
        ts_min = 0.0
        ts_max = length / 30.0
        ts_mean = ts_max / 2.0
        fi_min = 0
        fi_max = length - 1
        fi_mean = (length - 1) / 2.0
        idx_min = episode_num * 1000
        idx_max = episode_num * 1000 + length - 1
        idx_mean = (idx_min + idx_max) / 2.0

        stats_obj = {
            "observation.state": {
                "min": [float(f"{-3.0 + 0.1 * (i % 10):.6f}") for i in range(28)],
                "max": [float(f"{3.0 - 0.1 * (i % 10):.6f}") for i in range(28)],
                "mean": [float(f"{(i % 10) * 0.1:.6f}") for i in range(28)],
                "std": [float(f"{0.5 + (i % 5) * 0.1:.6f}") for i in range(28)],
                "count": [length],
            },
            "action": {
                "min": [float(f"{-3.0 + 0.1 * (i % 10):.6f}") for i in range(28)],
                "max": [float(f"{3.0 - 0.1 * (i % 10):.6f}") for i in range(28)],
                "mean": [float(f"{(i % 10) * 0.1:.6f}") for i in range(28)],
                "std": [float(f"{0.5 + (i % 5) * 0.1:.6f}") for i in range(28)],
                "count": [length],
            },
            # Include default scalar features used by LeRobot
            "timestamp": {
                "min": [float(ts_min)],
                "max": [float(ts_max)],
                "mean": [float(ts_mean)],
                "std": [0.0],
                "count": [length],
            },
            "frame_index": {
                "min": [int(fi_min)],
                "max": [int(fi_max)],
                "mean": [float(fi_mean)],
                "std": [0.0],
                "count": [length],
            },
            "episode_index": {
                "min": [int(episode_num)],
                "max": [int(episode_num)],
                "mean": [float(episode_num)],
                "std": [0.0],
                "count": [length],
            },
            "index": {
                "min": [int(idx_min)],
                "max": [int(idx_max)],
                "mean": [float(idx_mean)],
                "std": [0.0],
                "count": [length],
            },
            "task_index": {
                "min": [0],
                "max": [0],
                "mean": [0.0],
                "std": [0.0],
                "count": [length],
            },
        }

        episodes_stats_data.append({
            "episode_index": episode_num,
            "stats": stats_obj,
        })
    create_jsonl_file(meta_dir / "episodes_stats.jsonl", episodes_stats_data)

    # merged_episodes_stats.jsonl - always generate
    print("   Creating meta/merged_episodes_stats.jsonl")
    merged_episodes_stats_data = []
    for episode_num in range(num_episodes):
        length = int(episode_lengths.get(episode_num, 0))
        # Reuse the same stats structure as episodes_stats for compatibility
        ts_min = 0.0
        ts_max = length / 30.0
        ts_mean = ts_max / 2.0
        fi_min = 0
        fi_max = length - 1
        fi_mean = (length - 1) / 2.0
        idx_min = episode_num * 1000
        idx_max = episode_num * 1000 + length - 1
        idx_mean = (idx_min + idx_max) / 2.0

        stats_obj = {
            "observation.state": {
                "min": [float(f"{-3.0 + 0.1 * (i % 10):.6f}") for i in range(28)],
                "max": [float(f"{3.0 - 0.1 * (i % 10):.6f}") for i in range(28)],
                "mean": [float(f"{(i % 10) * 0.1:.6f}") for i in range(28)],
                "std": [float(f"{0.5 + (i % 5) * 0.1:.6f}") for i in range(28)],
                "count": [length],
            },
            "action": {
                "min": [float(f"{-3.0 + 0.1 * (i % 10):.6f}") for i in range(28)],
                "max": [float(f"{3.0 - 0.1 * (i % 10):.6f}") for i in range(28)],
                "mean": [float(f"{(i % 10) * 0.1:.6f}") for i in range(28)],
                "std": [float(f"{0.5 + (i % 5) * 0.1:.6f}") for i in range(28)],
                "count": [length],
            },
            "timestamp": {
                "min": [float(ts_min)],
                "max": [float(ts_max)],
                "mean": [float(ts_mean)],
                "std": [0.0],
                "count": [length],
            },
            "frame_index": {
                "min": [int(fi_min)],
                "max": [int(fi_max)],
                "mean": [float(fi_mean)],
                "std": [0.0],
                "count": [length],
            },
            "episode_index": {
                "min": [int(episode_num)],
                "max": [int(episode_num)],
                "mean": [float(episode_num)],
                "std": [0.0],
                "count": [length],
            },
            "index": {
                "min": [int(idx_min)],
                "max": [int(idx_max)],
                "mean": [float(idx_mean)],
                "std": [0.0],
                "count": [length],
            },
            "task_index": {
                "min": [0],
                "max": [0],
                "mean": [0.0],
                "std": [0.0],
                "count": [length],
            },
        }

        merged_episodes_stats_data.append({
            "episode_index": episode_num,
            "stats": stats_obj,
            # Additional merged-specific fields (ignored by LeRobot loader)
            "merged_timestamp": f"{episode_num * 100.0:.2f}",
            "merge_status": "COMPLETED",
            "merge_version": "v2.1",
        })
    create_jsonl_file(meta_dir / "merged_episodes_stats.jsonl", merged_episodes_stats_data)

    # tasks.jsonl
    print("   Creating meta/tasks.jsonl")
    tasks_data = [
        {"task_index": 0, "task": "the left gripper pick up the basket to the appropriate position,  the right gripper pick up the peach and place it into the basket."}
    ]
    create_jsonl_file(meta_dir / "tasks.jsonl", tasks_data)

    # info.json
    print("   Creating meta/info.json")

    # Calculate total frames based on actual parquet row counts
    total_frames = sum(int(episode_lengths.get(i, 0)) for i in range(num_episodes))

    # Joint names for the dual-arm robot
    joint_names = [
        "right_arm_joint_1_rad", "right_arm_joint_2_rad", "right_arm_joint_3_rad",
        "right_arm_joint_4_rad", "right_arm_joint_5_rad", "right_arm_joint_6_rad",
        "right_arm_joint_7_rad", "right_gripper_open_rad",
        "right_eef_pos_x_m", "right_eef_pos_y_m", "right_eef_pos_z_m",
        "right_eef_rot_euler_x_rad", "right_eef_rot_euler_y_rad", "right_eef_rot_euler_z_rad",
        "left_arm_joint_1_rad", "left_arm_joint_2_rad", "left_arm_joint_3_rad",
        "left_arm_joint_4_rad", "left_arm_joint_5_rad", "left_arm_joint_6_rad",
        "left_arm_joint_7_rad", "left_gripper_open_rad",
        "left_eef_pos_x_m", "left_eef_pos_y_m", "left_eef_pos_z_m",
        "left_eef_rot_euler_x_rad", "left_eef_rot_euler_y_rad", "left_eef_rot_euler_z_rad"
    ]

    info_data = {
        "codebase_version": "v2.1",
        "robot_type": "realman_rmc_aidal",
        "total_episodes": num_episodes,
        "total_frames": total_frames,
        "total_tasks": 1,
        "total_videos": num_episodes * 3,  # 3 cameras per episode
        "total_chunks": actual_num_chunks,
        "chunks_size": 1000,
        "fps": 30,
        "splits": {
            "train": f"0:{num_episodes}"
        },
        "data_path": "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet",
        "video_path": "videos/chunk-{episode_chunk:03d}/{video_key}/episode_{episode_index:06d}.mp4",
        "features": {
            "observation.images.cam_high_rgb": {
                "dtype": "video",
                "shape": [480, 640, 3],
                "names": ["height", "width", "channels"],
                "info": {
                    "video.height": 480,
                    "video.width": 640,
                    "video.codec": "h264",
                    "video.pix_fmt": "yuv420p",
                    "video.is_depth_map": False,
                    "video.fps": 30,
                    "video.channels": 3,
                    "has_audio": False
                }
            },
            "observation.images.cam_left_wrist_rgb": {
                "dtype": "video",
                "shape": [480, 640, 3],
                "names": ["height", "width", "channels"],
                "info": {
                    "video.height": 480,
                    "video.width": 640,
                    "video.codec": "h264",
                    "video.pix_fmt": "yuv420p",
                    "video.is_depth_map": False,
                    "video.fps": 30,
                    "video.channels": 3,
                    "has_audio": False
                }
            },
            "observation.images.cam_right_wrist_rgb": {
                "dtype": "video",
                "shape": [480, 640, 3],
                "names": ["height", "width", "channels"],
                "info": {
                    "video.height": 480,
                    "video.width": 640,
                    "video.codec": "h264",
                    "video.pix_fmt": "yuv420p",
                    "video.is_depth_map": False,
                    "video.fps": 30,
                    "video.channels": 3,
                    "has_audio": False
                }
            },
            "observation.state": {
                "dtype": "float32",
                "shape": [28],
                "names": joint_names
            },
            "action": {
                "dtype": "float32",
                "shape": [28],
                "names": joint_names
            },
            "timestamp": {
                "dtype": "float32",
                "shape": [1],
                "names": None
            },
            "frame_index": {
                "dtype": "int64",
                "shape": [1],
                "names": None
            },
            "episode_index": {
                "dtype": "int64",
                "shape": [1],
                "names": None
            },
            "index": {
                "dtype": "int64",
                "shape": [1],
                "names": None
            },
            "task_index": {
                "dtype": "int64",
                "shape": [1],
                "names": None
            }
        }
    }
    create_json_file(meta_dir / "info.json", info_data)

    # merged_info.json - always generate from info.json base
    print("   Creating meta/merged_info.json")
    merged_joint_names = [
        "right_arm_joint_1_rad", "right_arm_joint_2_rad", "right_arm_joint_3_rad",
        "right_arm_joint_4_rad", "right_arm_joint_5_rad", "right_arm_joint_6_rad",
        "right_arm_joint_7_rad", "right_gripper_open",
        "right_eef_pos_x_m", "right_eef_pos_y_m", "right_eef_pos_z_m",
        "right_eef_rot_euler_x_rad", "right_eef_rot_euler_y_rad", "right_eef_rot_euler_z_rad",
        "left_arm_joint_1_rad", "left_arm_joint_2_rad", "left_arm_joint_3_rad",
        "left_arm_joint_4_rad", "left_arm_joint_5_rad", "left_arm_joint_6_rad",
        "left_arm_joint_7_rad", "left_gripper_open",
        "left_eef_pos_x_m", "left_eef_pos_y_m", "left_eef_pos_z_m",
        "left_eef_rot_euler_x_rad", "left_eef_rot_euler_y_rad", "left_eef_rot_euler_z_rad"
    ]

    # Make merged_info.json fully compatible with LeRobot 'info.json' schema
    # Start from a deep copy of info.json and only override the joint name lists
    merged_info_data = deepcopy(info_data)
    if "features" in merged_info_data:
        if "observation.state" in merged_info_data["features"]:
            merged_info_data["features"]["observation.state"]["names"] = merged_joint_names
        if "action" in merged_info_data["features"]:
            merged_info_data["features"]["action"]["names"] = merged_joint_names
    create_json_file(meta_dir / "merged_info.json", merged_info_data)

    # eef_sim_info.json
    print("   Creating meta/eef_sim_info.json")
    eef_sim_names = [
        "left_eef_pos_x", "left_eef_pos_y", "left_eef_pos_z",
        "left_eef_ori_x", "left_eef_ori_y", "left_eef_ori_z",
        "right_eef_pos_x", "right_eef_pos_y", "right_eef_pos_z",
        "right_eef_ori_x", "right_eef_ori_y", "right_eef_ori_z",
        "left_gripper_open", "right_gripper_open"
    ]
    eef_sim_info_data = {
        "features": {
            "eef_sim.state": {
                "dtype": "float32",
                "shape": [14],
                "names": eef_sim_names
            },
            "action": {
                "dtype": "float32",
                "shape": [14],
                "names": eef_sim_names
            }
        }
    }
    create_json_file(meta_dir / "eef_sim_info.json", eef_sim_info_data)

    # state_action_info.json
    print("   Creating meta/state_action_info.json")
    state_action_joint_names = [
        "right_arm_joint_1_rad", "right_arm_joint_2_rad", "right_arm_joint_3_rad",
        "right_arm_joint_4_rad", "right_arm_joint_5_rad", "right_arm_joint_6_rad",
        "right_arm_joint_7_rad", "right_gripper_open",
        "right_eef_pos_x_m", "right_eef_pos_y_m", "right_eef_pos_z_m",
        "right_eef_rot_euler_x_rad", "right_eef_rot_euler_y_rad", "right_eef_rot_euler_z_rad",
        "left_arm_joint_1_rad", "left_arm_joint_2_rad", "left_arm_joint_3_rad",
        "left_arm_joint_4_rad", "left_arm_joint_5_rad", "left_arm_joint_6_rad",
        "left_arm_joint_7_rad", "left_gripper_open",
        "left_eef_pos_x_m", "left_eef_pos_y_m", "left_eef_pos_z_m",
        "left_eef_rot_euler_x_rad", "left_eef_rot_euler_y_rad", "left_eef_rot_euler_z_rad"
    ]
    state_action_info_data = {
        "features": {
            "observation.state": {
                "dtype": "float32",
                "shape": [28],
                "names": state_action_joint_names
            },
            "action": {
                "dtype": "float32",
                "shape": [28],
                "names": state_action_joint_names
            }
        }
    }
    create_json_file(meta_dir / "state_action_info.json", state_action_info_data)

    # subtask_annotation_info.json
    print("   Creating meta/subtask_annotation_info.json")
    subtask_annotation_info_data = {
        "features": {
            "subtask_annotation": {
                "dtype": "int32",
                "shape": [5],
                "names": None
            }
        }
    }
    create_json_file(meta_dir / "subtask_annotation_info.json", subtask_annotation_info_data)

    print("\n✅ Fake pipeline data generated successfully!")
    print_actual_structure_tree(output_dir)


def _db_read_meta_info(dataset_root: Path) -> dict:
    meta_file = dataset_root / "meta" / "info.json"
    if not meta_file.exists():
        return {}
    try:
        return json.loads(meta_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _db_count_total_episodes(dataset_root: Path, meta: dict) -> int:
    try:
        total = meta.get("total_episodes")
        if isinstance(total, int) and total >= 0:
            return total
    except Exception:
        pass

    data_dir = dataset_root / "data"
    if data_dir.exists():
        try:
            chunk_dirs = [d for d in data_dir.iterdir() if d.is_dir() and d.name.startswith("chunk-")]
            if chunk_dirs:
                count = 0
                for chunk_dir in chunk_dirs:
                    count += len(list(chunk_dir.glob("episode_*.parquet")))
                if count > 0:
                    return count
            flat = len(list(data_dir.glob("episode_*.parquet")))
            if flat > 0:
                return flat
        except Exception:
            pass

    episodes_jsonl = dataset_root / "meta" / "episodes.jsonl"
    if episodes_jsonl.exists():
        try:
            with open(episodes_jsonl, encoding="utf-8") as f:
                return sum(1 for _ in f)
        except Exception:
            pass

    return 0


def upsert_fake_dataset(
    db_path: Path,
    dataset_root: Path,
    dataset_name: str | None,
    dataset_uuid_str: str | None,
    end_effector_type: str,
) -> str:
    db = DatasetDatabase(db_path)
    meta = _db_read_meta_info(dataset_root)

    ds_name = dataset_name or dataset_root.name
    ds_uuid = dataset_uuid_str or str(uuid.uuid4())

    with db.with_session() as session:
        # Remove existing rows with the same dataset_name
        session.execute(text("DELETE FROM datasets WHERE dataset_name = :ds_name"), {"ds_name": ds_name})
        session.commit()

        # Discover existing columns in the target DB to avoid missing-column errors
        result = session.execute(text("PRAGMA table_info(datasets)"))
        existing_columns = {row[1] for row in result}

        # Prepare values (TaskStatus stored as strings)
        episodes_count = _db_count_total_episodes(dataset_root, meta)
        values = {
            "dataset_name": ds_name,
            "dataset_uuid": ds_uuid,
            "end_effector_type": end_effector_type,

            "data_path": str(dataset_root),
            "convert_path": str(dataset_root),

            "device_model": "robot",
            "device_model_version": "default_version",
            "operation_platform_height": 77.2,
            "yaml_file_path": str(dataset_root),

            "convert_test_status": TaskStatus.COMPLETED.value,
            "convert_test_version": 1,
            "convert_status": TaskStatus.COMPLETED.value,
            "convert_version_ps": 1,
            "convert_version": 1,

            "total_episodes": episodes_count,
            "converted_episodes": episodes_count,
            "skipped_episodes": 0,
            "convert_err_msg": None,

            "sa_dpp_status": TaskStatus.COMPLETED.value,
            "sa_dpp_version_ps": 1,
            "sa_dpp_version": 1,
            "sa_dpp_err_msg": None,

            "sim_replay_status": TaskStatus.COMPLETED.value,
            "sim_replay_version_ps": 1,
            "sim_replay_version": 1,
            "sim_replay_error_msg": None,

            "motion_annotation_status": TaskStatus.COMPLETED.value,
            "motion_annotation_version_ps": 1,
            "motion_annotation_version": 1,
            "motion_annotation_err_msg": None,

            "video_hash_status": None,
            "video_hash_version_ps": 1,
            "video_hash_version": 1,
            "video_hash_err_msg": None,

            "video_match_status": TaskStatus.COMPLETED.value,
            "video_match_version_ps": 1,
            "video_match_version": 1,
            "video_match_err_msg": None,

            "video_ori_subtask_annotation_status": TaskStatus.COMPLETED.value,
            "video_ori_subtask_annotation_version_ps": 1,
            "video_ori_subtask_annotation_version": 1,
            "video_ori_subtask_annotation_err_msg": None,

            "video_opt_subtask_annotation_status": TaskStatus.COMPLETED.value,
            "video_opt_subtask_annotation_version_ps": 1,
            "video_opt_subtask_annotation_version": 1,
            "video_opt_subtask_annotation_err_msg": None,

            "video_embed_subtask_annotation_status": TaskStatus.COMPLETED.value,
            "video_embed_subtask_annotation_version_ps": 1,
            "video_embed_subtask_annotation_version": 1,
            "video_embed_subtask_annotation_err_msg": None,

            "scene_annotation_status": TaskStatus.COMPLETED.value,
            "scene_annotation_version_ps": 1,
            "scene_annotation_version": 1,
            "scene_annotation_err_msg": None,

            "data_merge_status": TaskStatus.COMPLETED.value,
            "data_merge_version_ps_sta": 1,
            "data_merge_version_ps_sa": 1,
            "data_merge_version_ps_ma": 1,
            "data_merge_version": 1,
            "data_merge_err_msg": None,

            "data_loader_detection_status": None,
            "data_loader_detection_version_ps": None,
            "data_loader_detection_version": None,
            "data_loader_detection_err_msg": None,

            "ms_upload_status": None,
            "ms_upload_version_ps": None,
            "ms_upload_version": None,
            "ms_upload_err_msg": None,

            "huggingface_upload_status": None,
            "huggingface_upload_version_ps": None,
            "huggingface_upload_version": None,
            "huggingface_upload_err_msg": None,

            "dataset_info_sync_status": None,
            "dataset_info_sync_version_ps": None,
            "dataset_info_sync_version": None,
            "dataset_info_sync_err_msg": None,
        }

        # Filter to existing columns only
        cols = [c for c in values.keys() if c in existing_columns]
        sql = f"INSERT INTO datasets ({', '.join(cols)}) VALUES ({', '.join(':'+c for c in cols)})"
        session.execute(text(sql), {c: values[c] for c in cols})
        session.commit()

    return ds_uuid


def find_next_available_name(base_dir: Path, dataset_name: str) -> str:
    """
    Find the next available dataset name by auto-incrementing the version number.

    If ori_data_001 exists, returns ori_data_002.
    If ori_data_001 and ori_data_002 exist, returns ori_data_003.

    Args:
        base_dir: The base directory where datasets are stored
        dataset_name: The desired dataset name (e.g., "ori_data_001")

    Returns:
        Next available dataset name with incremented version
    """
    # Check if the requested name already exists
    target_path = base_dir / dataset_name
    if not target_path.exists():
        return dataset_name

    # Extract the base name and version number using regex
    # Matches patterns like: ori_data_001, fake_ori_data_002, dataset_123, etc.
    match = re.match(r'^(.+?)_(\d+)$', dataset_name)

    if not match:
        # No version number found, append _001
        print(f"⚠️  Warning: '{dataset_name}' already exists and has no version number.")
        print("   Appending '_001' to create versioned name.")
        base_name = dataset_name
        version = 1
    else:
        base_name = match.group(1)
        version = int(match.group(2))

    # Find the next available version
    print(f"📝 Dataset '{dataset_name}' already exists. Looking for next available version...")
    while True:
        version += 1
        new_name = f"{base_name}_{version:03d}"
        new_path = base_dir / new_name
        if not new_path.exists():
            print(f"   ✅ Auto-incremented to: {new_name}")
            return new_name


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate fake data in pipeline-produced structure for testing symlink script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create test data in default location (examples/dataloader_test/fake_ori_data_001/):
  %(prog)s

  # Run again - auto-increments to fake_ori_data_002 if fake_ori_data_001 exists:
  %(prog)s

  # Create test data with custom dataset name:
  %(prog)s --dataset-name fake_ori_data_002

  # Create test data in custom location:
  %(prog)s --output /path/to/test/data
  %(prog)s -o /path/to/test/data

  # Create more episodes and chunks:
  %(prog)s --episodes 5000 --chunks 5

Note: Dataset names are auto-incremented if they already exist
      (fake_ori_data_001 -> fake_ori_data_002 -> fake_ori_data_003, etc.)
        """
    )

    parser.add_argument(
        "-o", "--output",
        dest="output_base_dir",
        type=Path,
        default=None,
        help="Base output directory where fake data folder will be created. "
             "If not specified, uses 'examples/dataloader_test/' in project root. "
             "The actual data will be in a subfolder specified by --dataset-name"
    )

    parser.add_argument(
        "--dataset-name",
        type=str,
        default="fake_ori_data_001",
        help="Name of the dataset folder to create inside the output directory (default: fake_ori_data_001)"
    )

    parser.add_argument(
        "--episodes",
        type=int,
        default=1,
        help="Number of episodes to generate (default: 1)"
    )

    parser.add_argument(
        "--chunks",
        type=int,
        default=3,
        help="Number of chunks to create (default: 3)"
    )

    parser.add_argument(
        "--videos-per-episode",
        type=int,
        default=2,
        help="Number of video files per episode (default: 2)"
    )

    parser.add_argument(
        "--reference-data",
        dest="reference_data_dir",
        type=Path,
        default=None,
        help="Path to a reference dataset to copy videos/parquets/meta from when available"
    )

    # Database-related options
    parser.add_argument(
        "--db",
        dest="db_path",
        type=Path,
        default=None,
        help="Path to SQLite database file (default: examples/dataloader_test/datasets_new.db in project root)"
    )
    parser.add_argument(
        "--uuid",
        dest="dataset_uuid",
        type=str,
        default=None,
        help="Dataset UUID to store (defaults to a newly generated UUID4)"
    )

    args = parser.parse_args()

    # Find project root by looking for pyproject.toml
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir
    while project_root.parent != project_root:
        if (project_root / "pyproject.toml").exists():
            break
        project_root = project_root.parent

    # Determine base output directory
    if args.output_base_dir is None:
        # Default: create in examples/dataloader_test/
        output_base_dir = project_root / "examples" / "dataloader_test"
        print(f"No base output directory specified. Using default: {output_base_dir}")
    else:
        output_base_dir = args.output_base_dir.resolve()

    # Determine reference dataset root (default under project_root/examples/...)
    reference_root = None
    if args.reference_data_dir is None:
        candidate = (project_root / "examples" / "dataloader_test" / "reference_data").resolve()
    else:
        candidate = args.reference_data_dir.resolve()
    if candidate.exists():
        reference_root = candidate
        print(f"Using reference dataset at: {reference_root}")
    else:
        print(f"⚠️  Warning: reference dataset not found at {candidate}. Ignoring.")

    # Auto-increment dataset name if it already exists
    final_dataset_name = find_next_available_name(output_base_dir, args.dataset_name)

    # Create full output path with dataset name
    output_dir = output_base_dir / final_dataset_name
    print(f"Dataset will be created at: {output_dir}")

    # Generate fake data
    try:
        generate_fake_pipeline_data(
            output_dir=output_dir,
            num_episodes=args.episodes,
            num_chunks=args.chunks,
            num_videos_per_episode=args.videos_per_episode,
            project_root=project_root,
            reference_root=reference_root,
        )
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Create a LeRobot-compatible symlink structure next to the generated dataset by default
    try:
        symlink_target_dir = output_dir.parent / f"{final_dataset_name}_symlink"
        print(f"\n🔗 Creating default symlink structure beside dataset: {symlink_target_dir}")
        create_lerobot_symlink_structure(
            source_dir=output_dir.resolve(),
            target_dir=symlink_target_dir.resolve(),
            relative=True,
            skip_missing=False,
        )
    except Exception as e:
        print(f"\n⚠️  Failed to create symlink structure: {e}")
        import traceback
        traceback.print_exc()

    # After generating data, upsert fake dataset record into DB
    try:
        default_db = project_root / "examples" / "dataloader_test" / "datasets_new.db"
        db_path: Path = (args.db_path if args.db_path is not None else default_db).resolve()
        ds_uuid = upsert_fake_dataset(
            db_path=db_path,
            dataset_root=output_dir,
            dataset_name=final_dataset_name,
            dataset_uuid_str=args.dataset_uuid,
            end_effector_type="unknown",
        )
        print("OK")
        print(f"db: {db_path}")
        print(f"dataset_root: {output_dir}")
        print(f"dataset_uuid: {ds_uuid}")
    except Exception as e:
        print(f"\n⚠️  Failed to upsert dataset into DB: {e}")
        import traceback
        traceback.print_exc()

    return 0


if __name__ == "__main__":
    sys.exit(main())
