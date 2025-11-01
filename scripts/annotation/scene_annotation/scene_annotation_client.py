#!/usr/bin/env python3
"""
场景标注客户端脚本
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

import argparse
import logging

from robocoin_dataset.annotation.scene_annotation.scene_annotation import SceneAnnotationClient


async def main():
    parser = argparse.ArgumentParser(description="场景标注客户端")
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="服务器主机地址",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8770,
        help="服务器端口",
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=10.0,
        help="心跳间隔（秒）",
    )
    parser.add_argument(
        "--log_dir",
        type=str,
        default="./logs/scene_annotation_client",
        help="日志目录",
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
            logging.FileHandler(log_dir / "scene_annotation_client.log"),
            logging.StreamHandler(),
        ],
    )
    logger = logging.getLogger(__name__)

    # 构建服务器URI
    server_uri = f"ws://{args.host}:{args.port}"

    # 创建场景标注客户端
    client = SceneAnnotationClient(
        server_uri=server_uri,
        heartbeat_interval=getattr(args, 'heartbeat-interval'),
        logger=logger,
    )

    # 启动客户端
    logger.info(f"连接到场景标注服务器: {server_uri}")
    await client.start()


if __name__ == "__main__":
    asyncio.run(main())