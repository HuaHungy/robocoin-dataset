import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


######## ACTUAL OPERATION ########
#------- VALIDATION -------#

def _validate_exist(yaml_path: str | None, hardlink_path: str | None) -> bool:
  """
  Validate that both yaml_path and hardlink_path exist.

  INPUT:
  yaml_path -> path to YAML file
  hardlink_path -> path to hardlink directory with videos

  OUTPUT:
  bool -> True if BOTH exist, False otherwise
  """

  _logger = logging.getLogger(__name__)

  # Check if both paths are provided
  if not yaml_path or not hardlink_path:
      _logger.debug(f"Missing paths - yaml_path: {yaml_path}, hardlink_path: {hardlink_path}")
      return False

  # Check if yaml_path exists
  yaml_file = Path(yaml_path)
  if not yaml_file.exists():
      _logger.debug(f"YAML file does not exist: {yaml_path}")
      return False

  # Check if hardlink_path exists
  hardlink_dir = Path(hardlink_path)
  if not hardlink_dir.exists():
      _logger.debug(f"Hardlink directory does not exist: {hardlink_path}")
      return False

  _logger.debug("Both paths validated successfully")
  return True


#------- YAML OPERATION -------#

def _copy_yaml_file_from_db(yaml_path: str, dst_path: str) -> None:
  '''Copy yaml file from db defined yaml_file_path to dst path
    Since the yaml file is actually the demanded format.
    I:
    yaml_path, -> the yaml file path in the database.
    dst_path.  -> the dst path to copy the yaml file.(in assets/dataset_info/)
    O: None, excute the copy operation.
  '''

  import shutil

  _logger = logging.getLogger(__name__)
  src_path = Path(yaml_path)
  dest_path = Path(dst_path)

  _logger.debug(f"Source YAML: {yaml_path}")
  _logger.debug(f"Destination: {dst_path}")

  # Check if source file exists
  if not src_path.exists():
      _logger.error(f"Source YAML file does not exist: {yaml_path}")
      raise FileNotFoundError(f"Source YAML file not found: {yaml_path}")

  # Create destination directory if it doesn't exist
  dest_path.parent.mkdir(parents=True, exist_ok=True)

  # Copy the file
  _logger.debug("Copying file...")
  shutil.copy2(src_path, dest_path)
  _logger.debug(f"Successfully copied YAML file from {yaml_path} to {dst_path}")


#------- VIDEO OPERATION -------#


def _sample_one_video_path(hardlink_path: str) -> str | None:
  """
  Sample one video path from the dataset root directory,
  identify the actual video path.

  INPUT:
  hardlink_path, -> the dataset in lerobot foramt, sepecify to sample from where.
  OUTPUT:
  selected_video_path, -> the sampled, actual video path.

  Expects root directory structure:
  hardlink_path/
    videos/
      chunk-*/
        observation.images.cam_high_rgb/*.mp4

  If cam_high_rgb not found, will search in other observation.images.* folders.
  """
  import random

  _logger = logging.getLogger(__name__)
  root_path = Path(hardlink_path)

  _logger.debug(f"Checking if root directory exists: {hardlink_path}")
  if not root_path.exists():
      _logger.warning(f"Root directory does not exist: {hardlink_path}")
      return None

  # Navigate to videos subdirectory
  videos_path = root_path / "videos"
  _logger.debug(f"Looking for videos directory: {videos_path}")

  if not videos_path.exists():
      _logger.warning(f"Videos directory does not exist: {videos_path}")
      return None

  # Find all videos in cam_high_rgb across all chunks
  _logger.debug(f"Searching for videos with pattern: {videos_path}/chunk-*/observation.images.cam_high_rgb/*.mp4")
  video_files = list(videos_path.glob("chunk-*/observation.images.cam_high_rgb/*.mp4"))
  _logger.debug(f"Found {len(video_files)} video files in cam_high_rgb")

  # If no videos found in cam_high_rgb, search in other observation.images.* folders
  if not video_files:
      _logger.info("No videos in cam_high_rgb, searching in other observation.images.* folders...")
      video_files = list(videos_path.glob("chunk-*/observation.images.*/*.mp4"))
      _logger.debug(f"Found {len(video_files)} video files in other camera folders")

  if not video_files:
      _logger.warning(
          f"No videos found in any observation.images.* folders under {videos_path}"
      )
      return None

  # Randomly sample one video
  selected_video_path = random.choice(video_files)
  _logger.info(f"Sampled video: {selected_video_path}")

  return str(selected_video_path)

def _compress_video_to_dst(selected_video_path: str, dst_path: str, target_size_kb: int) -> None:
  """
  Compress a single video file from source path to destination path.
  INPUT:
  selected_video_path, -> the sampled, actual video path. point DIRECTLY at the video file.
  dst_path, -> the dst path to compress the video file.(in assets/dataset_info/videos/)
  target_size_kb, -> the target size of the video file in KB.
  OUTPUT:
  None, excute the compress and copying operation.
  """
  import subprocess

  video_file = Path(selected_video_path)
  dst_video_path = Path(dst_path) / video_file.name

  _logger = logging.getLogger(__name__)

  _logger.debug(f"Video file: {video_file}")
  _logger.debug(f"Destination: {dst_video_path}")

  # Check if source video file exists
  if not video_file.exists():
      _logger.error(f"Source video file does not exist: {selected_video_path}")
      raise FileNotFoundError(f"Source video file not found: {selected_video_path}")

  # Create destination directory if it doesn't exist
  dst_video_path.parent.mkdir(parents=True, exist_ok=True)

  # Get video duration using ffprobe
  try:
      _logger.debug("Running ffprobe to get video duration...")
      duration_cmd = [
          "ffprobe", "-v", "error", "-show_entries",
          "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
          str(video_file)
      ]
      _logger.debug(f"ffprobe command: {' '.join(duration_cmd)}")
      result = subprocess.run(duration_cmd, capture_output=True, text=True, check=True, timeout=30)
      duration = float(result.stdout.strip())
      _logger.debug(f"Video duration: {duration:.2f} seconds")

      # Calculate target bitrate: (target_size_kb * 8) / duration (in kbps)
      target_bitrate_kbps = int((target_size_kb * 8) / duration)
      _logger.debug(f"Target bitrate: {target_bitrate_kbps} kbps")

      # Compress video directly from source to destination
      compress_cmd = [
          "ffmpeg", "-i", str(video_file),
          "-b:v", f"{target_bitrate_kbps}k",
          "-maxrate", f"{target_bitrate_kbps}k",
          "-bufsize", f"{target_bitrate_kbps * 2}k",
          "-y",  # Overwrite output file if exists
          str(dst_video_path)
      ]

      _logger.debug(f"ffmpeg command: {' '.join(compress_cmd)}")
      _logger.info("Starting video compression (this may take a while)...")
      result = subprocess.run(compress_cmd, check=True, capture_output=True, timeout=300)
      _logger.info(f"Successfully compressed {video_file.name} to approximately {target_size_kb}KB at {dst_video_path}")

  except subprocess.TimeoutExpired:
      _logger.error(f"Video compression timed out for {video_file.name}")
      # Clean up partial output file if it exists
      if dst_video_path.exists():
          dst_video_path.unlink()
      raise RuntimeError(f"Video compression timed out for {video_file.name}")
  except subprocess.CalledProcessError as e:
      _logger.error(f"Failed to compress {video_file.name}: {e}")
      _logger.error(f"ffmpeg stderr: {e.stderr.decode() if e.stderr else 'N/A'}")
      # Clean up partial output file if it exists
      if dst_video_path.exists():
          dst_video_path.unlink()
      raise RuntimeError(f"Video compression failed for {video_file.name}: {e}")
  except Exception as e:
      _logger.error(f"Error processing {video_file.name}: {e}", exc_info=True)
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
      _logger.debug(f"Renamed YAML from {src_yaml.name} to {dst_yaml.name}")
  else:
      _logger.debug(f"YAML already named correctly: {src_yaml.name}")

  # Step 2: Check and rename video file if necessary
  src_video = Path(video_path)
  if not src_video.exists():
      raise FileNotFoundError(f"Video file not found: {video_path}")

  expected_video_name = f"{dataset_name}{src_video.suffix}"
  if src_video.name != expected_video_name:
      dst_video = src_video.parent / expected_video_name
      src_video.rename(dst_video)
      _logger.debug(f"Renamed video from {src_video.name} to {dst_video.name}")
  else:
      _logger.debug(f"Video already named correctly: {src_video.name}")


def _gen_video_thumbnail(video_path: str, thumbnail_dir: str) -> None:
    """
    Generate a thumbnail image from a video file.
    Extracts the first frame of the video and saves it as a JPEG image.

    INPUT:
    video_path -> path to the video file
    thumbnail_dir -> directory to save the thumbnail image

    OUTPUT:
    None, saves thumbnail image with the same name as the video (with .jpg extension)
    """
    import subprocess

    _logger = logging.getLogger(__name__)

    video_file = Path(video_path)
    thumbnail_dir_path = Path(thumbnail_dir)
    thumbnail_dir_path.mkdir(parents=True, exist_ok=True)

    thumbnail_path = thumbnail_dir_path / f"{video_file.stem}.jpg"

    subprocess.run(
        ["ffmpeg", "-i", str(video_file), "-vframes", "1", "-q:v", "2", "-y", str(thumbnail_path)],
        check=True,
        capture_output=True,
        timeout=60
    )
    _logger.debug(f"Generated thumbnail: {thumbnail_path}")


#------- CONSOLIDATION -------#

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
      _logger.error(f"Dataset info directory does not exist: {dataset_info_dir}")
      raise FileNotFoundError(f"Dataset info directory not found: {dataset_info_dir}")

  # Find all YAML files
  yaml_files = list(dataset_info_path.glob("*.yaml")) + list(dataset_info_path.glob("*.yml"))
  _logger.info(f"Found {len(yaml_files)} YAML files to consolidate")

  if not yaml_files:
      _logger.warning("No YAML files found to consolidate")
      consolidated_data = {}
  else:
      consolidated_data = {}

      for yaml_file in yaml_files:
          try:
              _logger.debug(f"Reading YAML file: {yaml_file}")
              with open(yaml_file, encoding='utf-8') as f:
                  data = yaml.safe_load(f)

              # Use the filename (without extension) as the key
              dataset_name = yaml_file.stem
              consolidated_data[dataset_name] = data
              _logger.debug(f"Added {dataset_name} to consolidated data")

          except Exception as e:  # noqa: PERF203
              _logger.error(f"Failed to read or parse {yaml_file}: {e}", exc_info=True)
              continue

  # Create output directory if it doesn't exist
  output_file.parent.mkdir(parents=True, exist_ok=True)

  # Write consolidated data to JSON
  _logger.debug(f"Writing consolidated data to {output_file}")
  with open(output_file, 'w', encoding='utf-8') as f:
      json.dump(consolidated_data, f, indent=2, ensure_ascii=False)

  _logger.info(f"Successfully wrote consolidated datasets to {output_file}")


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
      _logger.error(f"Dataset info directory does not exist: {dataset_info_dir}")
      raise FileNotFoundError(f"Dataset info directory not found: {dataset_info_dir}")

  # Find all YAML files
  yaml_files = list(dataset_info_path.glob("*.yaml")) + list(dataset_info_path.glob("*.yml"))
  _logger.info(f"Found {len(yaml_files)} YAML files for indexing")

  # Create list of dataset names (filenames without extension)
  data_index = {
      "datasets": sorted([yaml_file.stem for yaml_file in yaml_files]),
      "count": len(yaml_files)
  }

  # Create output directory if it doesn't exist
  output_file.parent.mkdir(parents=True, exist_ok=True)

  # Write index to JSON
  _logger.debug(f"Writing data index to {output_file}")
  with open(output_file, 'w', encoding='utf-8') as f:
      json.dump(data_index, f, indent=2, ensure_ascii=False)

  _logger.info(f"Successfully wrote data index to {output_file} with {len(yaml_files)} datasets")
