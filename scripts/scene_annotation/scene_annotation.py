#!/usr/bin/env python3
"""
场景注释本地处理脚本

该脚本用于本地处理数据集的场景注释，从JSON文件中提取场景描述并生成嵌入向量。
"""

import argparse
import logging
from pathlib import Path

from robocoin_dataset.annotation.scene_annotation.scene_annotation import SceneAnnotation
from robocoin_dataset.utils.logger import setup_logger


def main():
    parser = argparse.ArgumentParser(
        description="场景注释本地处理脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 处理单个数据集文件夹
  python scene_annotation.py --db_file_path ./db/datasets_new.db --data_folder /path/to/dataset

  # 处理包含多个数据集的文件夹
  python scene_annotation.py --db_file_path ./db/datasets_new.db --data_folder /path/to/datasets_root

  # 启用详细日志
  python scene_annotation.py --db_file_path ./db/datasets_new.db --data_folder /path/to/dataset --log_level DEBUG
        """
    )
    
    parser.add_argument(
        "--db_file_path", 
        type=str, 
        required=True,
        help="数据库文件路径"
    )
    
    parser.add_argument(
        "--data_folder",
        type=str,
        required=True,
        help="数据集文件夹路径（可以是单个数据集或包含多个数据集的根目录）"
    )
    
    parser.add_argument(
        "--json_file_path",
        type=str,
        default="episode_*.json",
        help="JSON文件路径模式（默认: episode_*.json）"
    )
    
    parser.add_argument(
        "--log_level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别（默认: INFO）"
    )
    
    parser.add_argument(
        "--log_dir",
        type=str,
        default="",
        help="日志文件保存目录（可选）"
    )

    args = parser.parse_args()
    
    # 设置日志
    log_level = getattr(logging, args.log_level.upper())
    if args.log_dir:
        logger = setup_logger(
            name="scene_annotation",
            log_dir=Path(args.log_dir),
            level=log_level,
        )
    else:
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        logger = logging.getLogger("scene_annotation")

    # 验证输入参数
    db_file_path = Path(args.db_file_path).expanduser().absolute()
    data_folder = Path(args.data_folder).expanduser().absolute()
    
    if not db_file_path.exists():
        logger.error(f"数据库文件不存在: {db_file_path}")
        return 1
        
    if not data_folder.exists():
        logger.error(f"数据文件夹不存在: {data_folder}")
        return 1

    try:
        # 创建场景注释处理器
        scene_annotation = SceneAnnotation(
            db_file_path=db_file_path,
            json_file_path=args.json_file_path,
            logger=logger
        )
        
        logger.info(f"开始处理数据文件夹: {data_folder}")
        scene_annotation.process_folder(data_folder)
        logger.info("场景注释处理完成！")
        
        return 0
        
    except Exception as e:
        logger.error(f"处理过程中发生错误: {e}")
        logger.exception("详细错误信息:")
        return 1


if __name__ == "__main__":
    exit(main())