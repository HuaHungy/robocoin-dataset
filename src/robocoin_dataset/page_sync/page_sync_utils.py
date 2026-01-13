"""
脚本旨在提供一些通用的工具函数，用于页面同步和数据集上传的辅助操作
"""

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from robocoin_dataset.prepare_metadata.metadata_service import MetadataSyncService

######## ACTUAL OPERATION ########

# ------- DATASET NAME GETTING -------#

def _get_dataset_name(session: Session, dataset_uuid: str) -> str | None:
    """
    Get dataset name from a dataset record using dataset_uuid.
    This is for the page script compatibility.

    Args:
        session: Database session
        dataset_uuid: UUID of the dataset to query

    Returns:
        Dataset name (basename of convert_path) or None if not found
    """
    from robocoin_dataset.database.models import DatasetDB

    _logger = logging.getLogger(__name__)

    _logger.debug("[page_sync_utils] Querying for dataset name using dataset_uuid: %s...", dataset_uuid)
    query = session.query(DatasetDB).filter(
        DatasetDB.dataset_uuid == dataset_uuid
    )
    item = query.first()

    if not item:
        _logger.warning("[page_sync_utils] No dataset found with dataset_uuid: %s", dataset_uuid)
        return None

    if not hasattr(item, 'convert_path') or not item.convert_path:
        _logger.warning("[page_sync_utils] Dataset %s found but convert_path is missing or empty", dataset_uuid)
        return None

    # Get the basename (ending) of the convert_path as dataset_name
    dataset_name = Path(item.convert_path).name
    _logger.debug("[page_sync_utils] Retrieved dataset name: %s for dataset_uuid: %s", dataset_name, dataset_uuid)
    return dataset_name


# ------- VALIDATION -------#


def _validate_exist(yaml_path: str | None, hardlink_path: str | None) -> bool:
    """
    Validate that both yaml_path and hardlink_path exist.

    Returns:
      bool: True if BOTH exist, False otherwise
    """
    _logger = logging.getLogger(__name__)
    # Check if both paths are provided
    if not yaml_path or not hardlink_path:
        _logger.debug("[page_sync_utils] Missing paths - yaml_path: %s, hardlink_path: %s", yaml_path, hardlink_path)
        return False
    # Check if yaml_path exists
    yaml_file = Path(yaml_path)
    if not yaml_file.exists():
        _logger.debug("[page_sync_utils] YAML file does not exist: %s", yaml_path)
        return False
    # Check if hardlink_path exists
    hardlink_dir = Path(hardlink_path)
    if not hardlink_dir.exists():
        _logger.debug("[page_sync_utils] Hardlink directory does not exist: %s", hardlink_path)
        return False
    _logger.debug("[page_sync_utils] Both paths validated successfully")
    return True


# ------- YAML / METADATA OPERATION -------#


def _write_unified_metadata_yaml(
    metadata_service: MetadataSyncService,
    dst_yaml_path: str,
    hardlink_path: str,
    dataset_uuid: str | None,
) -> None:
    """
    通过共享的 MetadataSyncService 写出 YAML 文件。

    所有页面静态资源依赖的 YAML 均经由该服务生成，以确保与 README 上传
    使用完全一致的元数据收集逻辑。
    """
    try:
        metadata_service.write_unified_metadata_yaml(
            dst_yaml_path=dst_yaml_path,
            hardlink_path=hardlink_path,
            dataset_uuid=dataset_uuid,
        )
    except Exception as e:  # noqa: PERF203
        logging.getLogger(__name__).error(
            "[page_sync_utils] 写入统一元数据 YAML 失败: dataset_uuid=%s, dst=%s, err=%s",
            dataset_uuid,
            dst_yaml_path,
            e,
            exc_info=True,
        )
        raise


# ------- VIDEO OPERATION -------#


def _sample_one_video_path(hardlink_path: str) -> str | None:
    """
    Sample one video path from the dataset root directory,
    identify the actual video path.

    Priority: searches folders containing "high", "top", or "head" first.
    Falls back to all observation.images.* folders if no match found.

    INPUT:
    hardlink_path, -> the dataset in lerobot foramt, sepecify to sample from where.
    OUTPUT:
    selected_video_path, -> the sampled, actual video path.

    Expects root directory structure:
    hardlink_path/
      videos/
        chunk-*/
          observation.images.*/*.mp4
    """
    import random

    _logger = logging.getLogger(__name__)
    root_path = Path(hardlink_path)

    if not root_path.exists():
        _logger.warning("[page_sync_utils] Root directory does not exist: %s", hardlink_path)
        return None

    videos_path = root_path / "videos"
    if not videos_path.exists():
        _logger.warning("[page_sync_utils] Videos directory does not exist: %s", videos_path)
        return None

    # Get all videos first
    all_videos = list(videos_path.glob("chunk-*/observation.images.*/*.mp4"))
    if not all_videos:
        _logger.warning("[page_sync_utils] No videos found in any observation.images.* folders under %s", videos_path)
        return None

    # Filter videos from priority folders (containing "high", "top", or "head")
    priority_keywords = ["high", "top", "head","front"]
    priority_videos = [
        v for v in all_videos if any(kw in str(v).lower() for kw in priority_keywords)
    ]

    # Use priority videos if found, otherwise use all videos
    video_files = priority_videos if priority_videos else all_videos
    selected_video_path = random.choice(video_files)
    _logger.info("[page_sync_utils] Sampled video: %s", selected_video_path)

    return str(selected_video_path)


def _compress_video_to_dst(
    selected_video_path: str,
    dst_path: str,
    crf: int =18,
    force_update: bool = False,
) -> None:
    """
    Compress a single video file from source path to destination path using CRF (Constant Rate Factor).

    CRF (Constant Rate Factor) is a quality-based encoding method that maintains consistent visual
    quality across the video. Lower CRF values mean better quality but larger file sizes.
    - CRF 18: visually lossless (very large files)
    - CRF 23: high quality (default, good balance)
    - CRF 28: acceptable quality (smaller files)

    INPUT:
    selected_video_path, -> the sampled, actual video path. point DIRECTLY at the video file.
    dst_path, -> the dst path to compress the video file.(in assets/dataset_info/videos/)
    crf, -> CRF value for video compression (default: 18, range: 0-51, lower = better quality).
    force_update, -> if True, always regenerate; if False, skip if file exists (default: False).
    OUTPUT:
    None, execute the compress and copying operation.
    """
    import subprocess

    video_file = Path(selected_video_path)
    dst_video_path = Path(dst_path) / video_file.name

    _logger = logging.getLogger(__name__)

    # Skip if file exists and force_update is False
    if not force_update and dst_video_path.exists():
        _logger.info("[page_sync_utils] Video already exists at %s, skipping compression", dst_video_path)
        return

    _logger.debug("[page_sync_utils] Video file: %s", video_file)
    _logger.debug("[page_sync_utils] Destination: %s", dst_video_path)

    # Check if source video file exists
    if not video_file.exists():
        _logger.error("[page_sync_utils] Source video file does not exist: %s", selected_video_path)
        raise FileNotFoundError(f"Source video file not found: {selected_video_path}")

    # Create destination directory if it doesn't exist
    dst_video_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Get original file size for logging
        original_size_kb = video_file.stat().st_size / 1024
        _logger.debug("[page_sync_utils] Original video size: %.2f KB", original_size_kb)

        # Build ffmpeg command with CRF-based encoding
        compress_cmd = [
            "ffmpeg",
            "-i",
            str(video_file),
            "-c:v",
            "libx264",  # Use H.264 codec
            "-crf",
            str(crf),  # Constant Rate Factor for quality control
            "-preset",
            "medium",  # Balanced encoding speed/quality
            "-pix_fmt",
            "yuv420p",  # Ensure compatibility
            "-movflags",
            "+faststart",  # Optimize for web playback
            "-y",  # Overwrite output file if exists
            str(dst_video_path),
        ]

        _logger.debug("[page_sync_utils] ffmpeg command: %s", ' '.join(compress_cmd))
        _logger.info("[page_sync_utils] Starting video compression with CRF=%s (this may take a while)...", crf)
        subprocess.run(compress_cmd, check=True, capture_output=True, timeout=300)

        # Check output size
        if dst_video_path.exists():
            output_size_kb = dst_video_path.stat().st_size / 1024
            _logger.info(
                "[page_sync_utils] Successfully compressed %s: %.2fKB -> %.2fKB (CRF=%s)",
                video_file.name,
                original_size_kb,
                output_size_kb,
                crf
            )
        else:
            _logger.warning("[page_sync_utils] Compressed file created but size check failed")
            _logger.info("[page_sync_utils] Compression completed for %s", video_file.name)

    except subprocess.TimeoutExpired:
        _logger.error("[page_sync_utils] Video compression timed out for %s", video_file.name)
        # Clean up partial output file if it exists
        if dst_video_path.exists():
            dst_video_path.unlink()
        raise RuntimeError(f"Video compression timed out for {video_file.name}")
    except subprocess.CalledProcessError as e:
        _logger.error("[page_sync_utils] Failed to compress %s: %s", video_file.name, e)
        error_output = e.stderr.decode() if e.stderr else "N/A"
        _logger.error("[page_sync_utils] ffmpeg stderr: %s", error_output)
        # Clean up partial output file if it exists
        if dst_video_path.exists():
            dst_video_path.unlink()
        raise RuntimeError(f"Video compression failed for {video_file.name}: {e}")
    except Exception as e:
        _logger.error("[page_sync_utils] Error processing %s: %s", video_file.name, e, exc_info=True)
        # Clean up partial output file if it exists
        if dst_video_path.exists():
            dst_video_path.unlink()
        raise


def _align_video_name_with_yaml(yaml_path: str, video_path: str, dataset_name: str) -> None:
    """
    Align YAML and video filenames to match dataset name for page script compatibility.
    Step 1: Check if YAML is named dataset_name.yaml, if not, rename it.
    Step 2: Check if video is named dataset_name.mp4, if not, rename it.
    """

    _logger = logging.getLogger(__name__)

    # Step 1: Check and rename YAML file if necessary
    src_yaml = Path(yaml_path)
    if not src_yaml.exists():
        raise FileNotFoundError(f"YAML file not found: {yaml_path}")

    expected_yaml_name = f"{dataset_name}.yaml"
    if src_yaml.name != expected_yaml_name:
        dst_yaml = src_yaml.parent / expected_yaml_name
        src_yaml.rename(dst_yaml)
        _logger.debug("[page_sync_utils] Renamed YAML from %s to %s", src_yaml.name, dst_yaml.name)
    else:
        _logger.debug("[page_sync_utils] YAML already named correctly: %s", src_yaml.name)

    # Step 2: Check and rename video file if necessary
    src_video = Path(video_path)
    if not src_video.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    expected_video_name = f"{dataset_name}{src_video.suffix}"
    if src_video.name != expected_video_name:
        dst_video = src_video.parent / expected_video_name
        src_video.rename(dst_video)
        _logger.debug("[page_sync_utils] Renamed video from %s to %s", src_video.name, dst_video.name)
    else:
        _logger.debug("[page_sync_utils] Video already named correctly: %s", src_video.name)


def _gen_video_thumbnail(
    video_path: str,
    thumbnail_dir: str,
    force_update: bool = False,
) -> None:
    """
    Generate a thumbnail image from a video file.
    Extracts the first frame of the video and saves it as a JPEG image.

    INPUT:
    video_path -> path to the video file
    thumbnail_dir -> directory to save the thumbnail image
    force_update -> if True, always regenerate; if False, skip if file exists (default: False)

    OUTPUT:
    None, saves thumbnail image with the same name as the video (with .jpg extension)
    """
    import subprocess

    _logger = logging.getLogger(__name__)

    video_file = Path(video_path)
    thumbnail_dir_path = Path(thumbnail_dir)
    thumbnail_dir_path.mkdir(parents=True, exist_ok=True)

    thumbnail_path = thumbnail_dir_path / f"{video_file.stem}.jpg"

    # Skip if file exists and force_update is False
    if not force_update and thumbnail_path.exists():
        _logger.info("[page_sync_utils] Thumbnail already exists at %s, skipping generation", thumbnail_path)
        return

    subprocess.run(
        ["ffmpeg", "-i", str(video_file), "-vframes", "1", "-q:v", "2", "-y", str(thumbnail_path)],
        check=True,
        capture_output=True,
        timeout=60,
    )
    _logger.debug("[page_sync_utils] Generated thumbnail: %s", thumbnail_path)


# ------- CONSOLIDATION -------#


def _gen_consolidation(dataset_info_dir: str, output_path: str) -> None:
    """
    Generate consolidated_datasets.json by reading all YAML files from dataset_info directory
    and combining their metadata into a single JSON file.

    INPUT:
    dataset_info_dir -> path to the directory containing YAML files
    output_path -> path to write the consolidated JSON file

    OUTPUT:
    None, writes consolidated_datasets.json with all metadata
    """
    import json

    import yaml

    _logger = logging.getLogger(__name__)

    dataset_info_path = Path(dataset_info_dir)
    output_file = Path(output_path)

    if not dataset_info_path.exists():
        _logger.error("[page_sync_utils] Dataset info directory does not exist: %s", dataset_info_dir)
        raise FileNotFoundError(f"Dataset info directory not found: {dataset_info_dir}")

    # Find all YAML files
    yaml_files = list(dataset_info_path.glob("*.yaml")) + list(dataset_info_path.glob("*.yml"))
    _logger.info("[page_sync_utils] Found %s YAML files to consolidate", len(yaml_files))

    if not yaml_files:
        _logger.warning("[page_sync_utils] No YAML files found to consolidate")
        consolidated_data = {}
    else:
        consolidated_data = {}

        for yaml_file in yaml_files:
            try:
                _logger.debug("[page_sync_utils] Reading YAML file: %s", yaml_file)
                with open(yaml_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                # Use the filename (without extension) as the key
                dataset_name = yaml_file.stem
                consolidated_data[dataset_name] = data
                _logger.debug("[page_sync_utils] Added %s to consolidated data", dataset_name)

            except Exception as e:  # noqa: PERF203
                _logger.error("[page_sync_utils] Failed to read or parse %s: %s", yaml_file, e, exc_info=True)
                continue

    # Create output directory if it doesn't exist
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Write consolidated data to JSON
    _logger.debug("[page_sync_utils] Writing consolidated data to %s", output_file)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(consolidated_data, f, indent=2, ensure_ascii=False)

    _logger.info("[page_sync_utils] Successfully wrote consolidated datasets to %s", output_file)


def _gen_data_index(dataset_info_dir: str, output_path: str) -> None:
    """
    Generate data_index.json by listing all YAML files from dataset_info directory.

    INPUT:
    dataset_info_dir -> path to the directory containing YAML files
    output_path -> path to write the data index JSON file

    OUTPUT:
    None, writes data_index.json with list of all YAML files
    """
    import json

    _logger = logging.getLogger(__name__)

    dataset_info_path = Path(dataset_info_dir)
    output_file = Path(output_path)

    if not dataset_info_path.exists():
        _logger.error("[page_sync_utils] Dataset info directory does not exist: %s", dataset_info_dir)
        raise FileNotFoundError(f"Dataset info directory not found: {dataset_info_dir}")

    # Find all YAML files
    yaml_files = list(dataset_info_path.glob("*.yaml")) + list(dataset_info_path.glob("*.yml"))
    _logger.info("[page_sync_utils] Found %s YAML files for indexing", len(yaml_files))

    # Create list of dataset names (filenames without extension)
    data_index = {
        "datasets": sorted([yaml_file.stem for yaml_file in yaml_files]),
        "count": len(yaml_files),
    }

    # Create output directory if it doesn't exist
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Write index to JSON
    _logger.debug("[page_sync_utils] Writing data index to %s", output_file)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data_index, f, indent=2, ensure_ascii=False)

    _logger.info("[page_sync_utils] Successfully wrote data index to %s with %s datasets", output_file, len(yaml_files))


def _copy_robot_aliases_and_exclude(info_dir: str) -> None:
    """
    Copy the repository's robot_aliases.json and exclude.json into the page info directory.
    """
    import shutil

    _logger = logging.getLogger(__name__)
    assets_dir = Path(__file__).parent / "assets"

    # Copy robot_aliases.json
    robot_aliases_src = assets_dir / "robot_aliases.json"
    if not robot_aliases_src.exists():
        _logger.error("[page_sync_utils] robot_aliases.json resource missing at %s", robot_aliases_src)
        raise FileNotFoundError(f"Failed to locate robot_aliases.json at {robot_aliases_src}")

    dst_dir = Path(info_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    robot_aliases_dst = dst_dir / "robot_aliases.json"
    shutil.copy2(robot_aliases_src, robot_aliases_dst)
    _logger.info("[page_sync_utils] Copied %s to %s", robot_aliases_src, robot_aliases_dst)

    # Copy exclude.json
    exclude_src = assets_dir / "exclude.json"
    if not exclude_src.exists():
        _logger.error("[page_sync_utils] exclude.json resource missing at %s", exclude_src)
        raise FileNotFoundError(f"Failed to locate exclude.json at {exclude_src}")

    exclude_dst = dst_dir / "exclude.json"
    shutil.copy2(exclude_src, exclude_dst)
    _logger.info("[page_sync_utils] Copied %s to %s", exclude_src, exclude_dst)
