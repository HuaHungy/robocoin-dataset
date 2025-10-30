#!/usr/bin/env python3
"""
场景标注单机版本脚本
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

import argparse
import logging

from robocoin_dataset.annotation.scene_annotation.scene_annotation import SceneAnnotation


def main():
    parser = argparse.ArgumentParser(description="场景标注单机版本")
    parser.add_argument(
        "--db_file_path",
        type=str,
        required=True,
        help="数据库文件路径",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default=None,
        help="输出目录，如果不指定则使用数据集路径下的scene_annotations目录",
    )
    parser.add_argument(
        "--log_level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别",
    )

    args = parser.parse_args()

    # 设置日志
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    # 创建场景标注处理器
    scene_annotation = SceneAnnotation(
        db_file_path=args.db_file_path,
        output_dir=args.output_dir,
        logger=logger,
    )

    # 同步状态并处理一个数据集
    logger.info("开始同步场景标注状态...")
    scene_annotation.sync_scene_annotation_status()
    
    logger.info("开始处理场景标注任务...")
    scene_annotation.process_scene_annotation_one_dataset()
    
    logger.info("场景标注处理完成")


if __name__ == "__main__":
    main()