#!/usr/bin/env python3
"""
场景注释客户端脚本

该脚本用于连接到场景注释服务器，接收并处理场景注释任务。
"""

import argparse
import asyncio
import logging
from pathlib import Path

from robocoin_dataset.annotation.scene_annotation.scene_annotation import SceneAnnotationClient
from robocoin_dataset.utils.logger import setup_logger


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="场景注释客户端",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 连接到本地服务器
  python scene_annotation_client.py --host 127.0.0.1 --port 8769

  # 连接到远程服务器并设置心跳间隔
  python scene_annotation_client.py --host 192.168.1.100 --port 8769 --heartbeat-interval 30

  # 启用日志文件
  python scene_annotation_client.py --host 127.0.0.1 --port 8769 --log_dir ./logs
        """
    )

    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="服务器主机地址（默认: 127.0.0.1）"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8769,
        help="服务器端口（默认: 8769）"
    )
    
    parser.add_argument(
        "--log_dir",
        type=str,
        default="",
        help="日志文件保存目录（可选）"
    )

    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=10.0,
        help="客户端心跳间隔（秒，默认: 10.0）"
    )
    
    parser.add_argument(
        "--log_level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别（默认: INFO）"
    )

    args = parser.parse_args()
    
    # 设置日志
    log_level = getattr(logging, args.log_level.upper())
    if args.log_dir:
        logger = setup_logger(
            name="scene_annotation_client",
            log_dir=Path(args.log_dir),
            level=log_level,
        )
    else:
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        logger = logging.getLogger("scene_annotation_client")

    # 构建服务器URI
    server_uri = f"ws://{args.host}:{args.port}"
    logger.info(f"准备连接到场景注释服务器: {server_uri}")
    
    try:
        # 创建客户端实例
        scene_annotation_client = SceneAnnotationClient(
            server_uri=server_uri, 
            logger=logger, 
            heartbeat_interval=args.heartbeat_interval
        )
        
        logger.info("场景注释客户端启动成功")
        logger.info(f"任务类别: {scene_annotation_client.get_task_category()}")
        logger.info("按 Ctrl+C 停止客户端")
        
        # 运行客户端
        await scene_annotation_client.run()
        
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭客户端...")
    except Exception as e:
        logger.error(f"客户端运行失败: {e}")
        logger.exception("详细错误信息:")
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n客户端已停止")
    except Exception as e:
        print(f"客户端启动失败: {e}")
        exit(1)