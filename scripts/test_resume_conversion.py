#!/usr/bin/env python3
"""
测试robocoin converter的断点续转功能

使用方法：
    python scripts/test_resume_conversion.py --dataset_path /path/to/dataset --output_path /path/to/output

测试场景：
1. 第一次转换：转换前3个episodes
2. 第二次转换：应该跳过前3个，继续转换剩余的episodes
"""
import argparse
import logging
from pathlib import Path

from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import (
    LerobotFormatConverterFactory,
)
from robocoin_dataset.utils.logger import setup_logger
import yaml


def test_resume_conversion(
    device_model: str,
    dataset_path: Path,
    output_path: Path,
    factory_config_path: Path,
    repo_id: str,
    max_episodes: int = 3,
) -> None:
    """测试断点续转功能
    
    Args:
        device_model: 设备模型
        dataset_path: 数据集路径
        output_path: 输出路径
        factory_config_path: 工厂配置文件路径
        repo_id: 仓库ID
        max_episodes: 第一次转换的最大episodes数量
    """
    log_dir = Path("./logs/test_resume")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Setup logger
    logger = setup_logger(
        name="test_resume_conversion",
        log_dir=log_dir,
        level=logging.INFO
    )
    
    # Load factory config
    if not factory_config_path.exists():
        raise FileNotFoundError(f"Factory config file {factory_config_path} does not exist.")
    
    with open(factory_config_path) as f:
        factory_config = yaml.safe_load(f)
    
    if device_model not in factory_config:
        raise ValueError(f"Device model {device_model} not found in factory config.")
    
    converter_module_path = factory_config[device_model]["module"]
    converter_class_name = factory_config[device_model]["class"]
    converter_config_file_name = factory_config[device_model]["config"]
    
    # Load converter config
    converter_config_path = dataset_path / converter_config_file_name
    if not converter_config_path.exists():
        raise FileNotFoundError(f"Converter config file {converter_config_path} does not exist.")
    
    with open(converter_config_path) as f:
        converter_config = yaml.safe_load(f)
    
    logger.info("=" * 80)
    logger.info("🧪 测试断点续转功能")
    logger.info("=" * 80)
    
    # ===== 第一次转换：转换前N个episodes =====
    logger.info("\n📝 第一次转换：转换前{} 个episodes".format(max_episodes))
    logger.info("-" * 80)
    
    converter1 = LerobotFormatConverterFactory.create_converter(
        dataset_path=dataset_path,
        device_model=device_model,
        output_path=output_path,
        converter_config=converter_config,
        converter_module_path=converter_module_path,
        converter_class_name=converter_class_name,
        repo_id=repo_id,
        video_backend="pyav",
        image_writer_processes=2,
        image_writer_threads=2,
        logger=logger,
    )
    
    # 转换前N个episodes
    count = 0
    for task, task_ep_idx, global_ep_idx in converter1.convert(is_test=False):
        logger.info(f"  ✅ 转换完成: task={task}, task_ep={task_ep_idx}, global_ep={global_ep_idx}")
        count += 1
        if count >= max_episodes:
            logger.info(f"\n⏸️  停止第一次转换（已转换 {count} 个episodes）")
            break
    
    # ===== 第二次转换：应该跳过已转换的episodes =====
    logger.info("\n🔄 第二次转换：应该自动跳过前{} 个episodes".format(max_episodes))
    logger.info("-" * 80)
    
    converter2 = LerobotFormatConverterFactory.create_converter(
        dataset_path=dataset_path,
        device_model=device_model,
        output_path=output_path,
        converter_config=converter_config,
        converter_module_path=converter_module_path,
        converter_class_name=converter_class_name,
        repo_id=repo_id,
        video_backend="pyav",
        image_writer_processes=2,
        image_writer_threads=2,
        logger=logger,
    )
    
    # 继续转换
    resume_count = 0
    for task, task_ep_idx, global_ep_idx in converter2.convert(is_test=False):
        logger.info(f"  ✅ 转换完成: task={task}, task_ep={task_ep_idx}, global_ep={global_ep_idx}")
        resume_count += 1
        if resume_count >= max_episodes:
            logger.info(f"\n✅ 第二次转换完成（又转换了 {resume_count} 个episodes）")
            break
    
    logger.info("\n" + "=" * 80)
    logger.info("🎉 断点续转测试完成！")
    logger.info("=" * 80)
    logger.info(f"  第一次转换: {count} episodes")
    logger.info(f"  第二次转换: {resume_count} episodes")
    logger.info(f"  总计: {count + resume_count} episodes")
    logger.info(f"\n📂 输出目录: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="测试断点续转功能")
    parser.add_argument("--dataset_path", type=Path, required=True, help="数据集路径")
    parser.add_argument("--output_path", type=Path, required=True, help="输出路径")
    parser.add_argument("--device_model", type=str, required=True, help="设备模型（如：g1）")
    parser.add_argument(
        "--factory_config_path",
        type=Path,
        default=Path("configs/converters/lerobot_format_convertor_factory_config.yaml"),
        help="工厂配置文件路径"
    )
    parser.add_argument(
        "--repo_id",
        type=str,
        default="test/resume-conversion",
        help="仓库ID"
    )
    parser.add_argument(
        "--max_episodes",
        type=int,
        default=3,
        help="每次转换的最大episodes数量"
    )
    
    args = parser.parse_args()
    
    test_resume_conversion(
        device_model=args.device_model,
        dataset_path=args.dataset_path,
        output_path=args.output_path,
        factory_config_path=args.factory_config_path,
        repo_id=args.repo_id,
        max_episodes=args.max_episodes,
    )


if __name__ == "__main__":
    main()
