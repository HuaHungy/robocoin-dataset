#!/usr/bin/env python3
"""
场景标注服务器脚本
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

import argparse
import logging

from robocoin_dataset.annotation.scene_annotation.scene_annotation import SceneAnnotationServer


async def main():
    parser = argparse.ArgumentParser(description="场景标注服务器")
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
        "--host",
        type=str,
        default="0.0.0.0",
        help="服务器主机地址",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8770,
        help="服务器端口",
    )
    parser.add_argument(
        "--log_dir",
        type=str,
        default="./logs/scene_annotation_server",
        help="日志目录",
    )
    parser.add_argument(
        "--heartbeat_interval",
        type=float,
        default=30.0,
        help="心跳间隔（秒）",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="超时时间（秒）",
    )

    args = parser.parse_args()

    # 创建日志目录
    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "scene_annotation_server.log"),
            logging.StreamHandler(),
        ],
    )
    logger = logging.getLogger(__name__)

    # 创建场景标注服务器
    server = SceneAnnotationServer(
        db_file_path=args.db_file_path,
        output_dir=args.output_dir,
        host=args.host,
        port=args.port,
        heartbeat_interval=args.heartbeat_interval,
        timeout=args.timeout,
        logger=logger,
    )

    # 启动服务器
    logger.info(f"启动场景标注服务器: {args.host}:{args.port}")
    await server.start()


if __name__ == "__main__":
    asyncio.run(main())