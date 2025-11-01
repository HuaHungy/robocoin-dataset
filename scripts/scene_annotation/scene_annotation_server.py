#!/usr/bin/env python3
"""
场景注释服务器脚本

该脚本用于启动场景注释服务器，管理和分发场景注释任务给连接的客户端。
"""

import argparse
import asyncio
import logging
from pathlib import Path

from robocoin_dataset.annotation.scene_annotation.scene_annotation import SceneAnnotationServer
from robocoin_dataset.utils.logger import setup_logger


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="场景注释服务器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 启动本地服务器
  python scene_annotation_server.py --db_file_path ./db/datasets_new.db

  # 指定端口和主机
  python scene_annotation_server.py --db_file_path ./db/datasets_new.db --host 0.0.0.0 --port 8769

  # 启用日志文件
  python scene_annotation_server.py --db_file_path ./db/datasets_new.db --log_dir ./logs

  # 调试模式
  python scene_annotation_server.py --db_file_path ./db/datasets_new.db --log_level DEBUG
        """
    )
    
    parser.add_argument(
        "--db_file_path",
        type=str,
        required=True,
        help="数据库文件路径"
    )

    parser.add_argument(
        "--log_dir",
        type=str,
        default="",
        help="日志文件保存目录（可选）"
    )

    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="服务器主机地址（默认: 0.0.0.0）"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8769,
        help="服务器端口（默认: 8769）"
    )
    
    parser.add_argument(
        "--log_level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别（默认: INFO）"
    )

    args = parser.parse_args()
    
    # 验证数据库文件
    db_file_path = Path(args.db_file_path).expanduser().absolute()
    if not db_file_path.exists():
        print(f"错误: 数据库文件不存在: {db_file_path}")
        exit(1)

    # 设置日志
    log_level = getattr(logging, args.log_level.upper())
    if args.log_dir:
        logger = setup_logger(
            name="scene_annotation_server",
            log_dir=Path(args.log_dir),
            level=log_level,
        )
    else:
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        logger = logging.getLogger("scene_annotation_server")

    try:
        # 创建服务器实例
        scene_annotation_server = SceneAnnotationServer(
            db_file_path=db_file_path,
            host=args.host,
            port=args.port,
            logger=logger
        )
        
        logger.info(f"场景注释服务器启动成功")
        logger.info(f"服务器地址: ws://{args.host}:{args.port}")
        logger.info(f"任务类别: {scene_annotation_server.get_task_category()}")
        logger.info(f"数据库文件: {db_file_path}")
        logger.info("按 Ctrl+C 停止服务器")
        
        # 启动服务器
        await scene_annotation_server.start()
        
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭服务器...")
    except Exception as e:
        logger.error(f"服务器运行失败: {e}")
        logger.exception("详细错误信息:")
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n服务器已停止")
    except Exception as e:
        print(f"服务器启动失败: {e}")
        exit(1)