import argparse
import logging
import traceback
from multiprocessing import cpu_count
from pathlib import Path

import yaml
from tqdm import tqdm

from robocoin_dataset.format_converter.tolerobot.constant import (
    DEFAULT_DEVICE_MODEL_VERSION,
    DEVICE_MODEL_VERSION_KEY,
)
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import (
    LerobotFormatConverter,
    LerobotFormatConverterFactory,
)
from robocoin_dataset.utils.logger import setup_logger


import time
import datetime
from typing import List, Dict

def generate_conversion_report(
    output_path: Path,
    device_model: str,
    device_model_version: str | None,
    total_episodes: int,
    success_count: int,
    total_time: float,
    episode_stats: List[Dict],
    dataset_path: Path,
    log_file: Path | None = None
):
    """Generate a Markdown report for the conversion process."""
    report_path = output_path / "CONVERSION_REPORT.md"
    avg_time = total_time / total_episodes if total_episodes > 0 else 0
    fps = sum(s['frames'] for s in episode_stats) / total_time if total_time > 0 else 0
    
    with open(report_path, "w") as f:
        f.write(f"# LeRobot Conversion Report\n\n")
        f.write(f"**Date**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Device Model**: `{device_model}` (Version: `{device_model_version}`)\n")
        f.write(f"**Input Dataset**: `{dataset_path}`\n")
        f.write(f"**Output Directory**: `{output_path}`\n\n")
        
        f.write("## 1. Performance Summary\n")
        f.write(f"- **Total Episodes**: {total_episodes}\n")
        f.write(f"- **Success Rate**: {success_count}/{total_episodes} ({(success_count/total_episodes)*100:.1f}%)\n")
        f.write(f"- **Total Time**: {total_time:.2f} s\n")
        f.write(f"- **Average Time per Episode**: {avg_time:.2f} s\n")
        f.write(f"- **Processing Speed**: {fps:.2f} frames/s\n\n")
        
        f.write("## 2. Episode Details\n")
        f.write("| Episode ID | Frames | Duration (s) | FPS | Status |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- |\n")
        
        for stat in episode_stats:
            status = "✅ Success" if stat['success'] else "❌ Failed"
            f.write(f"| {stat['index']} | {stat['frames']} | {stat['duration']:.2f} | {stat['fps']:.2f} | {status} |\n")
            
        if log_file and log_file.exists():
            f.write("\n## 3. Logs\n")
            f.write(f"Full logs are available at: `{log_file}`\n")

    print(f"Conversion report generated at: {report_path}")

def convert2lerobot(
    device_model: str,
    dataset_path: Path,
    output_path: Path,
    factory_config_path: Path,
    repo_id: str,
    log_dir: Path,
    video_backend: str = "pyav",
    image_writer_processes: int = 4,
    image_writer_threads: int = 4,
    converter_log_dir: Path | None = None,
    device_model_version: str | None = None,
    is_test: bool = False,
    auto_reencode: bool = False,
    max_episodes: int | None = None,
) -> LerobotFormatConverter:
    """
    Convert dataset to lerobot format.

    Args:
        dataset_path (str): Path to dataset.
        output_path (str): Path to output directory.
    """
    start_time = time.time()
    episode_stats = []

    if not factory_config_path.exists():
        raise FileNotFoundError(f"Factory config file {factory_config_path} does not exist.")

    with open(factory_config_path) as f:
        factory_config = yaml.safe_load(f)
        device_model_configs_list = factory_config[device_model]
        if device_model_configs_list is None:
            raise ValueError(f"Device model {device_model} not found in factory config.")

        if not isinstance(device_model_configs_list, list):
            raise ValueError(f"Device model {device_model} config must be a list.")

        converter_module_path: str | None = None
        for device_model_config in device_model_configs_list:
            if device_model_version is None:
                if device_model_config[DEVICE_MODEL_VERSION_KEY] == DEFAULT_DEVICE_MODEL_VERSION:
                    converter_module_path = device_model_config["module"]
                    converter_class_name = device_model_config["class"]
                    converter_config_path = (
                        factory_config_path.parent / device_model_config["converter_config_path"]
                    )
                    break
            elif device_model_config[DEVICE_MODEL_VERSION_KEY] == device_model_version:
                converter_module_path = device_model_config["module"]
                converter_class_name = device_model_config["class"]
                converter_config_path = (
                    factory_config_path.parent
                    / device_model_config["converter_config_path"]
                )
                break
        if converter_module_path is None:
            raise ValueError(
                f"Device model {device_model} with version {device_model_version} not found in factory config."
            )

    with open(converter_config_path) as f:
        converter_config = yaml.safe_load(f)

    logger: logging.Logger = setup_logger(
        name="LEROBOT_CONVERTER",
        log_dir=log_dir,
        level=logging.INFO,
    )
    
    # Get the actual log file path from the file handler
    log_file_path = None
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            log_file_path = Path(handler.baseFilename)
            break

    converter: LerobotFormatConverter = LerobotFormatConverterFactory.create_converter(
        dataset_path=dataset_path,
        device_model=device_model,
        output_path=output_path,
        converter_config=converter_config,
        converter_module_path=converter_module_path,
        converter_class_name=converter_class_name,
        repo_id=repo_id,
        video_backend=video_backend,
        image_writer_processes=image_writer_processes,
        image_writer_threads=image_writer_threads,
        logger=logger,
        converter_log_dir=converter_log_dir,
        auto_reencode=auto_reencode,
    )

    total_episodes = converter.get_episodes_num()
    if is_test:
        total_episodes = 1
    elif max_episodes is not None and max_episodes > 0:
        total_episodes = min(total_episodes, max_episodes)

    success_count = 0
    converted_count = 0
    
    # Use convert() generator but stop early if max_episodes is reached
    # Note: converter.convert() handles is_test logic internally, but not max_episodes
    # We need to manually break the loop if not is_test but max_episodes is set
    
    for task, task_ep_idx, ep_idx in tqdm(
        converter.convert(is_test=is_test),
        total=total_episodes,
        desc="Converting Dataset",
        unit="episode",
    ):
        ep_start = time.time()
        logger.info(f"Converted episode {task_ep_idx} of task {task}, total ep_idx is:{ep_idx}")
        ep_duration = time.time() - ep_start
        
        success_count += 1
        converted_count += 1
        
        # Try to retrieve actual stats from converter's mapping if available
        # Note: ep_idx in the loop is the global LeRobot index
        frames = 0
        
        # We need to find the entry in episode_source_mapping that corresponds to this global_ep_idx
        # The keys in episode_source_mapping are original_ep_idx, not global_ep_idx
        if hasattr(converter, 'episode_source_mapping'):
            for orig_idx, info in converter.episode_source_mapping.items():
                if info.get("global_ep_idx") == ep_idx:
                    frames = info.get("converted_frames", 0)
                    break
        
        episode_stats.append({
            "index": ep_idx,
            "frames": frames, 
            "duration": ep_duration,
            "fps": frames / ep_duration if ep_duration > 0 else 0,
            "success": True
        })
        
        if max_episodes is not None and converted_count >= max_episodes:
            break
    
    # Save episode source mapping after conversion completes
    if not is_test:
        converter.save_episode_source_mapping()
        converter.save_original_data_paths()
    
    total_time = time.time() - start_time
    
    # Generate the markdown report
    generate_conversion_report(
        output_path=output_path,
        device_model=device_model,
        device_model_version=device_model_version,
        total_episodes=total_episodes,
        success_count=success_count,
        total_time=total_time,
        episode_stats=episode_stats,
        dataset_path=dataset_path,
        log_file=log_file_path
    )
    
    # Automatically run evaluation script if conversion was successful and not empty
    if success_count > 0 and output_path.exists():
        try:
            print("\nRunning evaluation script...")
            # Import and run the evaluator
            import sys
            # Add src to path to import evaluator
            src_path = Path(__file__).resolve().parents[3] / "src"
            if str(src_path) not in sys.path:
                sys.path.append(str(src_path))
            
            # Run the evaluator as a subprocess to avoid import issues or conflicts
            import subprocess
            eval_script = src_path / "robocoin_dataset/convert_test/evaluate_lerobot.py"
            subprocess.run([sys.executable, str(eval_script), str(output_path)], check=True)
            
            # Append evaluation summary to conversion report?
            # Or just leave them side-by-side. User requested "evaluation report should also be there".
            # They are in the same folder now.
            
        except Exception as e:
            logger.error(f"Failed to run evaluation script: {e}")
            print(f"Failed to run evaluation script: {e}")

    return converter


def main() -> None:
    argparser = argparse.ArgumentParser(description="Convert dataset to lerobot format.")
    # ... 保留原有参数设置 ...
    argparser.add_argument(
        "--num_processes",
        type=int,
        default=int(cpu_count() / 4),  # 默认情况下，使用所有可用的CPU核心/4
        help="Number of processes to use for the conversion (default: all available cores)",
    )
    argparser.add_argument(
        "--dataset_path",
        type=Path,
    )
    argparser.add_argument(
        "--output_path",
        type=Path,
    )
    argparser.add_argument(
        "--device_model",
        type=str,
    )
    argparser.add_argument(
        "--factory_config_path",
        type=Path,
        default=Path("configs/converters/lerobot_format_convertor_factory_config.yaml"),
    )
    argparser.add_argument(
        "--repo_id",
        type=str,
        default="",
    )
    argparser.add_argument(
        "--log_dir",
        type=Path,
        default=Path("outputs/lerobot_converter/logs/"),
    )
    argparser.add_argument(
        "--image_writer_processes",
        type=int,
        default=4,
        help="Number of processes for image writing (default: 4)",
    )
    argparser.add_argument(
        "--image_writer_threads",
        type=int,
        default=4,
        help="Number of threads per process for image writing (default: 2)",
    )
    argparser.add_argument(
        "--video_backend",
        type=str,
        choices=["pyav", "opencv"],
        default="pyav",
        help="Backend for video processing (default: pyav)",
    )

    argparser.add_argument(
        "--device_model_version",
        type=str,
        default="none",
        help="Device model version (default: none)",
    )

    argparser.add_argument(
        "--is-test",
        action="store_true",
        default=False,
        help="Enable test mode (default: disabled)",
    )
    
    argparser.add_argument(
        "--auto-reencode",
        action="store_true",
        default=False,
        help="Enable automatic video re-encoding for incompatible codecs (e.g., AV1). Requires ffmpeg. (default: disabled)",
    )
    
    argparser.add_argument(
        "--max-episodes",
        type=int,
        default=None,
        help="Maximum number of episodes to convert (default: all)",
    )

    args = argparser.parse_args()
    device_model_version = None
    if args.device_model_version != "none":
        device_model_version = args.device_model_version

    try:
        convert2lerobot(
            device_model=args.device_model,
            dataset_path=args.dataset_path,
            output_path=args.output_path,
            factory_config_path=args.factory_config_path,
            repo_id=args.repo_id,
            log_dir=args.log_dir,
            video_backend=args.video_backend,
            image_writer_processes=args.image_writer_processes,
            image_writer_threads=args.image_writer_threads,
            converter_log_dir=args.log_dir,
            device_model_version=device_model_version,
            is_test=args.is_test,
            auto_reencode=args.auto_reencode,
            max_episodes=args.max_episodes,
        )
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    import time

    st = time.time()
    main()
    print(f"Total time: {time.time() - st}")

"""_summary_

python scripts/format_converters/tolerobot/convert2lerobot.py \
--dataset_path /home/lxc/Downloads/stir_coffee/stir_coffee_1 \
--output_path ./outputs/lerobot_converter_test/stir_coffee_1 \
--device_model realman_rmc_aidal \
--factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config_test.yaml \
--repo_id robocoin/realman_rmc_aidal_stir_coffee \
--log_dir ./outputs/robocoin/logs \
--image_writer_processes 10 \
--image_writer_threads 4 \
--video_backend pyav

python scripts/format_converters/tolerobot/convert2lerobot.py \
--dataset_path /mnt/nas/synnas/docker/11realman_rmc_aidal/basket_storage_banana \
--output_path ./outputs/lerobot_converter_test/basket_storage_banana \
--device_model realman_rmc_aidal \
--factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
--repo_id robocoin/basket_storage \
--log_dir ./outputs/lerobot_converter_test/basket_storage_banana/logs \
--image_writer_processes 10 \
--image_writer_threads 4 \
--video_backend pyav \
--is-test


python scripts/format_converters/tolerobot/convert2lerobot.py \
--dataset_path ~/Desktop/action44 \
--output_path ~/Desktop/output \
--device_model discover_robotics_aitbot_mmk2 \
--factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
--repo_id robocoin/test \
--log_dir ./outputs/lerobot_converter_test/test/logs \
--image_writer_processes 10 \
--image_writer_threads 4 \
--video_backend pyav 

"""
